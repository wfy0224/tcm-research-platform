import { useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { readingText } from "./knowledgeSelection";

type Evidence = { evidence_id: string; evidence_revision_no: number; citation_number?: number; source_title: string; quote_text: string };
type Finding = { assertion_text: string; claim_type: string; agent_role: string; audit_verdict: string; audit_rationale: string; reason_type: string; evidence: Evidence[] };
type Report = { question: string; schema_version: string; content_hash: string; review_status?: string; revision_no?: number; sections: Record<string, Finding[]>; answer?: { paragraphs: { text: string; kind: string; evidence: Evidence[] }[]; review_summary: string; review_issues?: string[] } | null; open_disputes: { rationale_summary: string }[]; unresolved_gaps: { rationale_summary: string }[]; excluded_claim_count: number };
const titles: Record<string, string> = { HIGH_CONFIDENCE: "研究结论", CONDITIONAL: "有条件的解释", DISPUTED: "仍有争议", UNSUPPORTED: "证据不足", UNRESOLVED: "尚未解决" };
const key = (e: Evidence) => `${e.evidence_id}:${e.evidence_revision_no}`;

// Group similar statements for reading, while retaining every audited statement.
function related(a: Finding, b: Finding) {
  if (a.claim_type !== b.claim_type) return false;
  const normalize = (s: string) => s.replace(/[\s，。；：、（）()“”‘’]/g, "");
  const [long, short] = [normalize(a.assertion_text), normalize(b.assertion_text)].sort((x, y) => y.length - x.length);
  if (short.length < 40) return long === short;
  const pairs = new Set(Array.from({ length: short.length - 1 }, (_, i) => short.slice(i, i + 2)));
  return [...pairs].filter(pair => long.includes(pair)).length / pairs.size > 0.8
    && b.evidence.every(e => a.evidence.some(item => key(item) === key(e)));
}

export default function ResearchReport({ report, onEvidence }: { report: Report; onEvidence?: (ref: { evidence_id: string; revision_no: number }) => void }) {
  const root = useRef<HTMLDivElement>(null);
  const returnLink = useRef<HTMLAnchorElement | null>(null);
  const [focusedEvidence, setFocusedEvidence] = useState<string | null>(null);
  const [returnAvailable, setReturnAvailable] = useState(false);
  function revealEvidence(id: string) {
    const target = root.current?.querySelector<HTMLDetailsElement>(`#${id}`);
    if (!target) return;
    target.open = true;
    setFocusedEvidence(id);
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "start", behavior: "instant" });
  }
  function followEvidence(event: MouseEvent<HTMLAnchorElement>, id: string) {
    event.preventDefault();
    returnLink.current = event.currentTarget;
    setReturnAvailable(true);
    const url = new URL(location.href);
    url.hash = id;
    // Native fragment navigation fires the app's popstate handler, which restores
    // the source-view scroll position. Keep this jump inside the rendered report.
    history.replaceState(history.state, "", url);
    revealEvidence(id);
  }
  useEffect(() => {
    setFocusedEvidence(null);
    returnLink.current = null;
    setReturnAvailable(false);
    if (/^#report-evidence-\d+$/.test(location.hash)) revealEvidence(location.hash.slice(1));
  }, [report.content_hash]);
  const evidence = new Map<string, Evidence>();
  Object.values(report.sections).flat().forEach(f => f.evidence.forEach(e => evidence.set(key(e), e)));
  report.answer?.paragraphs.forEach(p => p.evidence.forEach(e => evidence.set(key(e), e)));
  const numbers = new Map([...evidence].map(([id, e], i) => [id, e.citation_number || i + 1]));
  const ordered = (items: Evidence[]) => [...items].sort((a, b) => numbers.get(key(a))! - numbers.get(key(b))!);
  const pending = report.review_status === "NEEDS_REVISION";
  const answer = report.answer && <section className="reportAnswer"><h4>{pending ? "综合回答草稿（未通过复核）" : "研究回答"}</h4>{report.answer.paragraphs.map((p, i) => <article className="reportConclusion" key={i}><p className="conclusionText">{p.text}</p><div className="reportCitationLinks">依据：{ordered(p.evidence).map(e => <a key={key(e)} href={`#report-evidence-${numbers.get(key(e))}`} onClick={event => followEvidence(event, `report-evidence-${numbers.get(key(e))}`)}>[{numbers.get(key(e))}]</a>)}</div></article>)}<details className="reportAudit"><summary>查看回答复核</summary><p>{report.answer.review_summary}</p></details></section>;
  return <div className="readableReport" ref={root}>
    {pending && <><p className="workspaceAlert" role="status">研究报告已保存。下方为已审计观点与材料限制；综合回答草稿尚未通过复核，不作为已审核结论。</p><details><summary>查看综合回答需要修订的问题</summary>{report.answer?.review_issues?.map((issue, i) => <p key={i}>{issue}</p>)}</details></>}
    {pending ? <details><summary>查看待修订的综合回答草稿</summary>{answer}</details> : answer}
    {!report.answer && <p className="muted">这是旧版报告，尚未生成综合回答。下列为已审计观点。</p>}
    <details className="reportDetailedClaims" open={pending}><summary>展开详细论证与审计</summary>
    {Object.entries(titles).map(([section, title]) => {
      const groups: Finding[][] = [];
      const causalQuestion = /为何|为什么|何以|原因/.test(report.question);
      const priority = (f: Finding) => causalQuestion && /原因|之所以|因为|解释为|为了/.test(f.assertion_text) ? 1 : 0;
      [...(report.sections[section] || [])].sort((a, b) => priority(b) - priority(a) || b.assertion_text.length - a.assertion_text.length).forEach(f => {
        const group = groups.find(items => related(items[0], f));
        if (group) group.push(f); else groups.push([f]);
      });
      const render = (items: Finding[], i: number) => <article className="reportConclusion" key={i}>
        <p className="conclusionText">{items[0].assertion_text}</p><div className="reportCitationLinks">依据：{ordered(items[0].evidence).map(e => <a key={key(e)} href={`#report-evidence-${numbers.get(key(e))}`} onClick={event => followEvidence(event, `report-evidence-${numbers.get(key(e))}`)}>[{numbers.get(key(e))}]</a>)}</div>
        <details className="reportAudit"><summary>查看论证与审计{items.length > 1 ? ` · 合并 ${items.length} 条相关表述` : ""}</summary><p>{items[0].audit_rationale}</p>{items.slice(1).map((item, j) => <p key={j}>{item.assertion_text}</p>)}</details>
      </article>;
      const focus = section === "HIGH_CONFIDENCE" && causalQuestion && groups.length > 2 && priority(groups[0][0]) > 0;
      return groups.length > 0 && <section className="reportConclusions" key={section}><h4>{title}</h4>{focus ? <>{render(groups[0], 0)}<details><summary>展开组成、证候及其他结论 · {groups.length - 1} 组</summary>{groups.slice(1).map((items, i) => render(items, i + 1))}</details></> : groups.map(render)}</section>;
    })}
    </details>
    {(report.open_disputes.length > 0 || report.unresolved_gaps.length > 0) && <section><h4>争议与材料限制</h4>{[...report.open_disputes, ...report.unresolved_gaps].map((item, i) => <p key={i}>{item.rationale_summary}</p>)}</section>}
    <section className="reportEvidence"><h4>原文依据 · {evidence.size} 条（已去重）</h4><p className="muted">点击回答中的依据编号，会展开并定位到对应原文。</p>{ordered([...evidence.values()]).map(e => <details id={`report-evidence-${numbers.get(key(e))}`} tabIndex={-1} className={focusedEvidence === `report-evidence-${numbers.get(key(e))}` ? "reportEvidenceFocused" : undefined} key={key(e)}><summary>[{numbers.get(key(e))}] {e.source_title} · 证据修订 {e.evidence_revision_no}</summary><blockquote>{readingText(e.quote_text)}</blockquote><button type="button" disabled={!onEvidence} onClick={() => onEvidence?.({ evidence_id: e.evidence_id, revision_no: e.evidence_revision_no })}>定位原文</button>{focusedEvidence === `report-evidence-${numbers.get(key(e))}` && returnAvailable && returnLink.current && <button type="button" className="textButton" onClick={() => { returnLink.current?.focus({ preventScroll: true }); returnLink.current?.scrollIntoView({ block: "center", behavior: "instant" }); }}>返回引用段落</button>}</details>)}</section>
    <details className="reportAudit"><summary>报告记录与版本</summary><p>研究问题：{report.question}</p><p>修订 {report.revision_no || 1} · 结构 {report.schema_version} · 内容摘要 {report.content_hash}</p><p>未纳入观点：{report.excluded_claim_count} · 开放争议：{report.open_disputes.length} · 未解决缺口：{report.unresolved_gaps.length}</p></details>
  </div>;
}
