"""Render immutable research reports as independently retried file artifacts."""

import hashlib
import html
import io
import json
import re
import zipfile
from dataclasses import dataclass
from uuid import UUID
from xml.etree import ElementTree as ET

from sqlalchemy import select, text

from tcm_platform.audit import append_event
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.enums import JobStatus, ResourceClass
from tcm_platform.ids import new_id
from tcm_platform.jobs import (
    LeaseLostError,
    acquire_job,
    assert_job_lease,
    complete_job,
    enqueue_job,
    fail_job,
)
from tcm_platform.models import (
    AgentRun,
    Artifact,
    AuditResult,
    Critique,
    HumanReviewRequest,
    Rebuttal,
    ReportExport,
    ResearchTask,
    StopEvaluation,
    StructuredReport,
    TaskJob,
    utc_now,
)
from tcm_platform.storage import ContentAddressedStore

RENDERER_VERSION = "report-export/v6"
FORMATS = frozenset({"markdown", "docx"})
CATEGORY_TITLES = {
    "HIGH_CONFIDENCE": "高可信结论",
    "CONDITIONAL": "条件性结论",
    "DISPUTED": "争议结论",
    "UNSUPPORTED": "未支持结论",
    "UNRESOLVED": "未解决问题",
}
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W)


@dataclass(frozen=True)
class Block:
    style: str
    text: str
    anchor: str | None = None
    link: str | None = None


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _anchor(prefix: str, value: str) -> str:
    return prefix + re.sub(r"[^a-zA-Z0-9]", "", value)


def _locator(value: object) -> str:
    if isinstance(value, dict):
        labels = {"path": "路径", "chapter_no": "章", "section_no": "节",
                  "page_no": "页", "paragraph_no": "段", "sentence_no": "句"}
        parts = [f"{labels[key]} {item}" for key, item in value.items()
                 if key in labels and item is not None]
        return "、".join(parts) if parts else json.dumps(value, ensure_ascii=False)
    return str(value)


def _citation(item: dict) -> str:
    locator = item["citation_locator"]
    start = _locator(locator.get("start", ""))
    end = _locator(locator.get("end", ""))
    span = start if start == end else f"{start} 至 {end}"
    edition = f"，{item['source_edition']}" if item.get("source_edition") else ""
    return (f"《{item['source_title']}》{edition}，来源修订 {item['source_revision_no']}，"
            f"定位 {span}")


def _process_snapshot(session, task_id: UUID) -> dict:
    """Freeze the recorded execution timeline when the derived export is requested."""
    runs = list(session.scalars(select(AgentRun).where(AgentRun.task_id == task_id)
                                .order_by(AgentRun.created_at, AgentRun.id)))
    audits = list(session.scalars(select(AuditResult).where(AuditResult.task_id == task_id)
                                  .order_by(AuditResult.created_at, AuditResult.id)))
    critiques = list(session.scalars(select(Critique).where(Critique.task_id == task_id)
                                     .order_by(Critique.created_at, Critique.id)))
    rebuttals = list(session.scalars(select(Rebuttal).where(Rebuttal.task_id == task_id)
                                     .order_by(Rebuttal.created_at, Rebuttal.id)))
    stops = list(session.scalars(select(StopEvaluation).where(
        StopEvaluation.task_id == task_id).order_by(StopEvaluation.created_at,
                                                   StopEvaluation.id)))
    reviews = list(session.scalars(select(HumanReviewRequest).where(
        HumanReviewRequest.task_id == task_id).order_by(HumanReviewRequest.created_at,
                                                       HumanReviewRequest.id)))
    return {
        "agent_runs": [{"id": str(r.id), "role": r.role, "round_no": r.round_no,
                        "status": r.status, "model_version": r.model_version} for r in runs],
        "audits": [{"id": str(r.id), "claim_id": str(r.claim_id),
                    "sequence_no": r.sequence_no, "stage": r.stage,
                    "verdict": r.verdict, "rationale_summary": r.rationale_summary}
                   for r in audits],
        "critiques": [{"id": str(r.id), "target_claim_id": str(r.target_claim_id),
                       "issue_type": r.issue_type, "rationale_summary": r.rationale_summary}
                      for r in critiques],
        "rebuttals": [{"id": str(r.id), "critique_id": str(r.critique_id),
                       "round_no": r.round_no, "action": r.action,
                       "rationale_summary": r.rationale_summary,
                       "revised_claim_id": str(r.revised_claim_id) if r.revised_claim_id else None}
                      for r in rebuttals],
        "stop_evaluations": [{"id": str(r.id), "round_no": r.round_no,
                              "decision": r.decision, "reason_code": r.reason_code,
                              "input_hash": r.input_hash} for r in stops],
        "human_reviews": [{"id": str(r.id), "status": r.status,
                           "reason_code": r.reason_code, "resolution_note": r.resolution_note}
                          for r in reviews],
    }


def report_blocks(content: dict, process: dict) -> list[Block]:
    """One factual outline drives both formats; all assertions come from the saved report."""
    claims = {c["claim_id"]: c for category in CATEGORY_TITLES
              for c in content["sections"].get(category, [])}
    claim_numbers = {key: i for i, key in enumerate(claims, start=1)}
    evidence = {e["evidence_revision_id"]: e for c in claims.values() for e in c["evidence"]}
    for dispute in content["open_disputes"]:
        for field in ("supporting_evidence", "opposing_evidence"):
            evidence.update({e["evidence_revision_id"]: e for e in dispute[field]})
    numbers = {key: i for i, key in enumerate(sorted(evidence), start=1)}
    dispute_numbers = {row["dispute_id"]: i for i, row in
                       enumerate(content["open_disputes"], start=1)}
    gap_numbers = {row["gap_id"]: i for i, row in
                   enumerate(content["unresolved_gaps"], start=1)}
    critique_numbers = {row["id"]: i for i, row in enumerate(process["critiques"], start=1)}
    labels = {
        "Classicist": "经典研究", "HistoricalScholar": "历史考证", "Theorist": "理论分析",
        "Planner": "研究规划", "Critic": "质疑审查", "Rebuttal": "回应质疑",
        "Judge": "综合裁判", "ReportWriter": "综合写作", "ReportReviewer": "回答复核",
        "COMPLETED": "已完成", "PENDING": "待执行", "FAILED": "执行失败",
        "RUNNING": "执行中", "SUPPORTED": "证据支持", "PARTIALLY_SUPPORTED": "部分支持",
        "UNSUPPORTED": "证据不足", "UNCERTAIN": "尚不确定", "CONTRADICTED": "存在矛盾",
        "PASS": "通过", "FAIL": "未通过", "MECHANICAL": "引用完整性检查",
        "SEMANTIC": "语义支持审计", "ACCEPT": "接受质疑", "PARTIAL_ACCEPT": "部分接受",
        "REJECT": "驳回质疑", "REVISE": "修订观点", "WITHDRAW": "撤回观点",
        "OVERCLAIM": "过度推断", "TEXTUAL_MISREAD": "原文误读", "HISTORICAL_SCOPE": "时代边界",
        "EVIDENCE_GAP": "证据缺口", "CRITIQUE_EVIDENCE_GAP": "质疑指出证据缺口",
        "CONTRADICTION": "结论矛盾", "STOP": "结束研究", "CONTINUE": "继续研究",
        "ROUND_LIMIT": "达到最大研究轮次", "NO_CRITIQUES": "本轮无新增质疑",
        "FOLLOWUP_REVIEW": "继续审查上一轮回应", "STABLE_EVIDENCE": "证据与观点已稳定",
        "RESOLVED": "已处理", "OPEN": "待解决",
    }

    def label(value: str) -> str:
        return labels.get(value, value)

    def claim_label(value: str) -> str:
        return f"观点 {claim_numbers[value]}" if value in claim_numbers else "未纳入报告的观点"

    def claim_link(value: str) -> Block:
        return Block("Link", "对应" + claim_label(value),
                     link=_anchor("claim", value) if value in claim_numbers else None)

    def audit_text(value: str) -> str:
        # The auditor's prose uses local input positions, not report citation
        # numbers. Keep the reasoning, without presenting those as global links.
        return re.sub(r"证据\s*\d+", "引用材料", value)

    blocks = [
        Block("Title", "中医理论研究报告"),
        Block("Normal", f"研究问题：{content['question']}"),
    ]
    if content.get("answer"):
        pending = content.get("review_status") == "NEEDS_REVISION"
        if pending:
            blocks.append(Block("Normal", "报告已保存：下方综合回答草稿未通过复核，不作为已审核结论。"
                                "已审计观点、争议、证据缺口及辩论记录完整保留。"))
        blocks.append(Block("Heading1", "综合回答草稿（待修订）" if pending else "研究回答"))
        for paragraph in content["answer"]["paragraphs"]:
            blocks.append(Block("Normal", paragraph["text"]))
            cited = sorted({e["evidence_revision_id"] for key in paragraph["claim_ids"]
                            for e in claims[key]["evidence"]})
            for evidence_id in cited:
                blocks.append(Block("Link", f"依据 [{numbers[evidence_id]}]",
                                    link=_anchor("evidence", evidence_id)))
        if pending:
            blocks.append(Block("Heading2", "综合回答需要修订的事项"))
            blocks.extend(Block("Normal", issue) for issue in content["answer"]["review_issues"])
    blocks.append(Block("Heading1", "附录：已审计观点"))
    for category, title in CATEGORY_TITLES.items():
        blocks.append(Block("Normal", f"{title}：{content['counts'][category]} 条"))
    blocks.append(Block("Normal", "分类沿用已审计的断言。争议与未验证内容不作为确定事实。"))
    for category, title in CATEGORY_TITLES.items():
        blocks.append(Block("Heading1", title))
        rows = content["sections"][category]
        if not rows:
            blocks.append(Block("Normal", "本类无断言。"))
        for row in rows:
            claim_id = row["claim_id"]
            blocks.append(Block("Heading2", f"{claim_label(claim_id)}：{row['assertion_text']}",
                                anchor=_anchor("claim", claim_id)))
            blocks.append(Block("Normal", f"研究角度：{label(row['agent_role'])}；"
                         f"审计结论：{label(row['audit_verdict'])}"))
            blocks.append(Block("Normal", f"审计说明：{audit_text(row['audit_rationale'])}"))
            for item in row["evidence"]:
                blocks.append(Block("Link", f"证据 [{numbers[item['evidence_revision_id']]}]："
                                    + _citation(item),
                                    link=_anchor("evidence", item["evidence_revision_id"])))
            for value in row["dispute_ids"]:
                if value in dispute_numbers:
                    blocks.append(Block("Link", f"关联争议 {dispute_numbers[value]}",
                                        link=_anchor("dispute", value)))
            for value in row["gap_ids"]:
                if value in gap_numbers:
                    blocks.append(Block("Link", f"证据缺口 {gap_numbers[value]}",
                                        link=_anchor("gap", value)))
    blocks.append(Block("Heading1", "争议与限制"))
    for dispute in content["open_disputes"]:
        blocks.append(Block("Heading2", f"争议 {dispute_numbers[dispute['dispute_id']]}",
                            anchor=_anchor("dispute", dispute["dispute_id"])))
        blocks.append(Block("Normal", f"{label(dispute['reason_code'])}："
                     f"{dispute['rationale_summary']}"))
        for support_label, key in (("支持", "supporting_evidence"), ("反对", "opposing_evidence")):
            for item in dispute[key]:
                blocks.append(Block("Link", f"{support_label}证据 [{numbers[item['evidence_revision_id']]}]："
                                    + _citation(item),
                                    link=_anchor("evidence", item["evidence_revision_id"])))
    for gap in content["unresolved_gaps"]:
        blocks.append(Block("Heading2", f"证据缺口 {gap_numbers[gap['gap_id']]}",
                            anchor=_anchor("gap", gap["gap_id"])))
        blocks.append(claim_link(gap["claim_id"]))
        blocks.append(Block("Normal", f"{label(gap['reason_code'])}：{gap['rationale_summary']}"))
    blocks.append(Block("Normal", f"另有 {content['excluded_claim_count']} 条未审定断言未进入综合。"))
    blocks.append(Block("Heading1", "原文证据与定位"))
    if not evidence:
        blocks.append(Block("Normal", "本报告无已验证的原文证据。"))
    for number, (evidence_id, item) in enumerate(sorted(evidence.items()), start=1):
        blocks.append(Block("Heading2", f"证据 {number} 《{item['source_title']}》",
                            anchor=_anchor("evidence", evidence_id)))
        blocks.append(Block("Normal", _citation(item)))
        blocks.append(Block("Quote", item["quote_text"]))
    blocks.append(Block("Heading1", "研究过程"))
    for run in process["agent_runs"]:
        round_label = (f"第 {run['round_no'] + 1} 稿"
                       if run["role"] in {"ReportWriter", "ReportReviewer"}
                       else f"第 {run['round_no']} 轮" if run["round_no"] else "")
        blocks.append(Block("Normal", f"{label(run['role'])} {round_label}："
                     f"{label(run['status'])}；模型 {run['model_version']}"))
    for number, audit in enumerate(process["audits"], start=1):
        blocks.append(Block("Heading2", f"审计 {number} · {claim_label(audit['claim_id'])}"))
        blocks.append(claim_link(audit["claim_id"]))
        blocks.append(Block("Normal", f"第 {audit['sequence_no']} 次，"
                     f"{label(audit['stage'])} / {label(audit['verdict'])}；"
                     f"{audit_text(audit['rationale_summary'])}"))
    for critique in process["critiques"]:
        blocks.append(Block("Heading2", f"质疑 {critique_numbers[critique['id']]}",
                            anchor=_anchor("critique", critique["id"])))
        blocks.append(claim_link(critique["target_claim_id"]))
        blocks.append(Block("Normal", f"{label(critique['issue_type'])}："
                     f"{critique['rationale_summary']}"))
    for number, rebuttal in enumerate(process["rebuttals"], start=1):
        blocks.append(Block("Heading2", f"回应 {number}"))
        number = critique_numbers.get(rebuttal["critique_id"])
        blocks.append(Block("Link", f"对应质疑 {number}" if number else "对应先前质疑",
                            link=_anchor("critique", rebuttal["critique_id"]) if number else None))
        blocks.append(Block("Normal", f"第 {rebuttal['round_no']} 轮，"
                     f"{label(rebuttal['action'])}："
                     f"{rebuttal['rationale_summary']}"))
    for number, stop in enumerate(process["stop_evaluations"], start=1):
        blocks.append(Block("Normal", f"停止判断 {number}：第 {stop['round_no']} 轮，"
                     f"{label(stop['decision'])}；{label(stop['reason_code'])}"))
    for number, review in enumerate(process["human_reviews"], start=1):
        blocks.append(Block("Normal", f"人工复核 {number}：{label(review['status'])}；"
                     f"{label(review['reason_code'])}；{review['resolution_note'] or ''}"))
    blocks.append(Block("Heading1", "报告版本"))
    metadata = process.get("report_metadata", {})
    if metadata.get("revision_no"):
        blocks.append(Block("Normal", f"报告修订：第 {metadata['revision_no']} 版"))
    blocks.append(Block("Normal", "综合回答复核："
                        + ("待修订" if content.get("review_status") == "NEEDS_REVISION"
                           else "已通过" if content.get("answer") else "旧版报告无综合回答复核")))
    if content.get("answer"):
        blocks.append(Block("Normal", "回答复核：" + content["answer"]["review_summary"]))
    # Review explanations can themselves contain internal references. Translate
    # known references for display without rewriting saved reviews or quotations.
    references = {key: claim_label(key) for key in claims}
    references.update({key: f"证据 {number}" for key, number in numbers.items()})
    references.update({key: f"质疑 {number}" for key, number in critique_numbers.items()})

    def readable(value: str) -> str:
        for key, name in references.items():
            value = value.replace(f"claim {key}", name).replace(key, name)
        return value

    return [Block(block.style, readable(block.text) if block.style != "Quote" else block.text,
                  anchor=block.anchor, link=block.link) for block in blocks]


def _markdown_escape(value: str) -> str:
    return (html.escape(value, quote=False).replace("\\", "\\\\")
            .replace("[", "\\[").replace("]", "\\]")
            .replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
            .replace("#", "\\#"))


def render_markdown(content: dict, process: dict) -> bytes:
    lines = []
    for block in report_blocks(content, process):
        if block.anchor:
            lines.append(f'<a id="{block.anchor}"></a>')
        value = _markdown_escape(block.text if block.style == "Quote"
                                 else " ".join(block.text.splitlines()))
        if block.style == "Title":
            lines.append("# " + value)
        elif block.style == "Heading1":
            lines.append("## " + value)
        elif block.style == "Heading2":
            lines.append("### " + value)
        elif block.style == "Quote":
            lines.extend("> " + line for line in value.splitlines())
        elif block.link:
            lines.append(f"[{value}](#{block.link})")
        else:
            lines.append(value)
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _w(parent: ET.Element, tag: str, **attributes: str) -> ET.Element:
    return ET.SubElement(parent, f"{{{W}}}{tag}",
                         {f"{{{W}}}{key}": value for key, value in attributes.items()})


def render_docx(content: dict, process: dict) -> bytes:
    root = ET.Element(f"{{{W}}}document")
    body = _w(root, "body")
    for number, block in enumerate(report_blocks(content, process), start=1):
        para = _w(body, "p")
        props = _w(para, "pPr")
        _w(props, "pStyle", val=block.style)
        if block.style in {"Title", "Heading1", "Heading2"}:
            _w(props, "keepNext")
        if content.get("answer") and block.text == "附录：已审计观点":
            _w(props, "pageBreakBefore")
        if block.anchor:
            _w(para, "bookmarkStart", id=str(number), name=block.anchor)
        run_parent = _w(para, "hyperlink", anchor=block.link) if block.link else para
        for line_no, line in enumerate(block.text.split("\n")):
            run = _w(run_parent, "r")
            if block.link:
                rpr = _w(run, "rPr")
                _w(rpr, "color", val="0563C1")
                _w(rpr, "u", val="single")
            if line_no:
                _w(run, "br")
            value = _w(run, "t")
            value.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            value.text = line
        if block.anchor:
            _w(para, "bookmarkEnd", id=str(number))
    section = _w(body, "sectPr")
    _w(section, "pgSz", w="12240", h="15840")  # Letter portrait.
    _w(section, "pgMar", top="1260", right="1260", bottom="1260", left="1260",
       header="720", footer="720", gutter="0")
    styles = ET.Element(f"{{{W}}}styles")
    for name, size, before, after in (("Normal", "22", "0", "120"),
                                      ("Title", "32", "0", "300"),
                                      ("Heading1", "27", "300", "140"),
                                      ("Heading2", "23", "220", "100"),
                                      ("Quote", "21", "40", "140"),
                                      ("Link", "21", "0", "100")):
        style = _w(styles, "style", type="paragraph", styleId=name)
        _w(style, "name", val=name)
        ppr = _w(style, "pPr")
        _w(ppr, "spacing", before=before, after=after, line="320", lineRule="auto")
        _w(ppr, "widowControl")
        if name in {"Heading1", "Heading2"}:
            _w(ppr, "outlineLvl", val="0" if name == "Heading1" else "1")
        if name == "Quote":
            _w(ppr, "ind", left="420", right="260")
        rpr = _w(style, "rPr")
        _w(rpr, "rFonts", ascii="Arial", hAnsi="Arial", eastAsia="Microsoft YaHei")
        _w(rpr, "sz", val=size)
        _w(rpr, "color", val="000000")
        if name in {"Title", "Heading1", "Heading2"}:
            _w(rpr, "b")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>""")
        archive.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""")
        archive.writestr("word/_rels/document.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""")
        archive.writestr("word/document.xml", ET.tostring(root, encoding="utf-8",
                                                            xml_declaration=True))
        archive.writestr("word/styles.xml", ET.tostring(styles, encoding="utf-8",
                                                          xml_declaration=True))
    return stream.getvalue()


def queue_report_export(task_id: UUID, file_format: str, *,
                        actor_id: str = "local-user") -> UUID:
    if file_format not in FORMATS:
        raise ValueError("report export format must be markdown or docx")
    with SessionLocal.begin() as session:
        report = session.scalar(select(StructuredReport).where(
            StructuredReport.task_id == task_id).order_by(
            StructuredReport.revision_no.desc()).limit(1))
        task = session.get(ResearchTask, task_id)
        if report is None or task is None:
            raise ValueError("a saved research report is required for export")
        key = f"research.report_export:{report.id}:{file_format}:{RENDERER_VERSION}"
        session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                        {"key": key})
        existing = session.scalar(select(ReportExport).where(
            ReportExport.report_id == report.id, ReportExport.file_format == file_format,
            ReportExport.renderer_version == RENDERER_VERSION).with_for_update())
        if existing is not None:
            job = session.get(TaskJob, existing.job_id)
            if job.status == JobStatus.FAILED.value:
                job.max_attempts += 3
                job.status = JobStatus.PENDING.value
                job.available_at = utc_now()
                job.last_error = None
                append_event(session, event_type="research.report_export.requeued",
                             actor_id=actor_id, aggregate_id=existing.id,
                             payload={"job_id": str(job.id), "attempts": job.attempts})
            elif job.status == JobStatus.RETRY_WAIT.value:
                job.available_at = utc_now()
            return existing.id
        job = enqueue_job(session, idempotency_key=key, job_type="research.report_export",
                          payload={"report_id": str(report.id), "file_format": file_format,
                                   "renderer_version": RENDERER_VERSION},
                          resource_class=ResourceClass.EXPORT, actor_id=actor_id)
        export = ReportExport(id=new_id(), report_id=report.id, task_id=task_id,
                              file_format=file_format, renderer_version=RENDERER_VERSION,
                              process_snapshot={**_process_snapshot(session, task_id),
                                                "report_metadata": {
                                                    "revision_no": report.revision_no}},
                              job_id=job.id)
        session.add(export)
        session.flush()
        append_event(session, event_type="research.report_export.queued",
                     actor_id=actor_id, aggregate_id=export.id,
                     payload={"report_id": str(report.id), "file_format": file_format,
                              "renderer_version": RENDERER_VERSION})
        return export.id


def process_next_report_export(*, worker_id: str = "local-export-worker",
                               store: ContentAddressedStore | None = None,
                               export_id: UUID | None = None) -> UUID | None:
    store = store or ContentAddressedStore(settings.data_root)
    with SessionLocal.begin() as session:
        key = None
        if export_id is not None:
            wanted = session.get(ReportExport, export_id)
            if wanted is None:
                raise ValueError("report export does not exist")
            key = f"research.report_export:{wanted.report_id}:{wanted.file_format}:"
            key += wanted.renderer_version
        job = acquire_job(session, worker_id=worker_id, lease_seconds=900,
                          job_types=("research.report_export",), idempotency_key=key)
        if job is None:
            return None
        export = session.scalar(select(ReportExport).where(ReportExport.job_id == job.id))
        if export is None:
            raise RuntimeError("report export job has no export record")
        report = session.get(StructuredReport, export.report_id)
        job_id, generation = job.id, job.execution_generation
        report_content = report.content if report else None
        report_hash = report.content_hash if report else None
        process = export.process_snapshot
        format_name, renderer_version = export.file_format, export.renderer_version
        export_record_id = export.id

    blob = None
    error = None
    try:
        if renderer_version != RENDERER_VERSION or format_name not in FORMATS:
            raise ValueError("report export renderer version or format is unavailable")
        if report_content is None or _digest(report_content) != report_hash:
            raise ValueError("stored report content hash differs from export input")
        rendered = (render_markdown(report_content, process) if format_name == "markdown"
                    else render_docx(report_content, process))
        blob = store.put(io.BytesIO(rendered))
    except Exception as exc:  # noqa: BLE001 - failed exports remain retryable.
        error = exc

    if error is not None:
        with SessionLocal.begin() as session:
            fail_job(session, job_id=job_id, worker_id=worker_id,
                     generation=generation, error=f"{type(error).__name__}: {error}")
        return export_record_id
    try:
        with SessionLocal.begin() as session:
            assert_job_lease(session, job_id=job_id, worker_id=worker_id,
                             generation=generation)
            export = session.scalar(select(ReportExport).where(
                ReportExport.id == export_record_id).with_for_update())
            report = session.get(StructuredReport, export.report_id)
            if report is None or _digest(report.content) != report.content_hash:
                raise ValueError("stored report changed before export commit")
            artifact: Artifact = store.register(
                session, blob, artifact_type="RESEARCH_REPORT_EXPORT",
                retention_class="PERMANENT",
                original_name=f"research-{export.task_id}."
                              f"{'md' if format_name == 'markdown' else 'docx'}",
            )
            export.artifact_id = artifact.id
            export.completed_at = utc_now()
            complete_job(session, job_id=job_id, worker_id=worker_id, generation=generation,
                         result={"export_id": str(export.id), "artifact_id": str(artifact.id),
                                 "blob_sha256": blob.sha256, "file_format": format_name,
                                 "renderer_version": export.renderer_version})
            append_event(session, event_type="research.report_export.completed",
                         actor_id=worker_id, aggregate_id=export.id,
                         payload={"artifact_id": str(artifact.id), "blob_sha256": blob.sha256})
    except LeaseLostError:
        raise
    except Exception as exc:  # noqa: BLE001 - persistence failure is an export job failure.
        with SessionLocal.begin() as session:
            fail_job(session, job_id=job_id, worker_id=worker_id, generation=generation,
                     error=f"{type(exc).__name__}: {exc}")
    return export_record_id
