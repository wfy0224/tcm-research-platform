import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { requestJson, postJson, apiErrorText } from "./api";
import "./knowledge.css";

type Props = { sessionActive: boolean; csrf: string; initialSourceId?: string; onPublished?: () => void; onResearch?: (sourceId: string) => void; onEvidence?: (ref: { evidence_id: string; revision_no: number }) => void };
type Source = { source_id: string; title: string; source_type: string; status: string; data_level: string };
type SourceDetail = Source & { author: string | null; era: string | null; edition: string | null; copyright_status: string; revisions: { revision_no: number; status: string; file_format: string; file_size_bytes: number; error_code: string | null }[] };
type Segment = { segment_id: string; sequence_no: number; segment_type: string; original_text: string; normalized_text: string; context_before: string; context_after: string; locator: Record<string, unknown>; parent_segment_id: string | null; page_no: number | null; chapter_no: number | null; paragraph_no: number | null };
type Evidence = { evidence_id: string; revision_no: number; status: string; evidence_strength: string; source_title: string; source_id: string; source_revision_no: number; quote_text: string; context_before: string; context_after: string; citation_locator: Record<string, unknown>; segment_ids: string[] };
type DraftKind = "concept" | "herb";
type ReviewKind = DraftKind | "relation" | "formula_revision";
type Draft = { ref: string; status: string; kind: ReviewKind; canonical_name?: string; original_name?: string; assertion_text?: string; concept_type?: string; relation_type?: string; terms?: string[]; ingredients?: { original_name: string; amount_original: string | null; unit: string | null }[]; method?: string | null; evidence: Evidence[] };
type Candidates = { extractor_version: string; segment_count: number; mention_count: number; relation_count: number; concept_count: number; formula_count: number; segments: { segment_ref: string; mentions: { surface_text: string; start_offset: number; end_offset: number; ambiguous: boolean }[] }[] };
type Issue = { issue_id: string; issue_type: string; severity: string; target_kind: string; target_ref: string; description: string; status: string; resolution_note: string | null };
type Quality = { open_issues: Record<string, number>; publication_blocked: boolean; active_version_id: string | null };
type Version = { version_id: string; version_no: number; status: string; active: boolean; manifest_hash: string };
type VersionDetail = Version & { item_counts: Record<string, number>; index_builds: { index_build_id: string; status: string; fts_status: string; vector_status: string }[] };
type Job = { job_id: string; status: string; attempts?: number; max_attempts?: number; error_code?: string | null };
type PublishConfiguration = { strategy: string; embedding_model: string | null; rerank_model: string | null; embedding_endpoint: string | null; rerank_endpoint: string | null };
type PublicationConfig = { configuration?: PublishConfiguration; mode?: string; channels?: string[]; available?: boolean; detail?: string };
const base = "/api/v1/knowledge";
const statusNames: Record<string, string> = { DRAFT: "待审核", REVIEWED: "已人工审核", REJECTED: "已拒绝", SEGMENTED: "已解析分段", REGISTERED: "待解析", PARSING: "解析中", FAILED: "失败", PENDING: "等待执行", RUNNING: "执行中", SUCCEEDED: "完成", COMPLETED: "完成", PRE_PUBLISH_SNAPSHOT: "待发布快照", INDEXING: "索引构建中", VALIDATING: "验证中", PUBLISHED: "已发布", ACTIVE: "已激活", READY: "可用", LOCAL_ONLY: "仅本地", NOT_APPLICABLE: "不适用", OCR_REQUIRED: "需要 OCR" };
const displayStatus = (value: string) => statusNames[value] ?? value;
const terminal = (status: string) => ["SUCCEEDED", "COMPLETED", "FAILED", "CANCELLED"].includes(status);
const evidenceRef = (row: Evidence) => `${row.evidence_id}@${row.revision_no}`;
const enc = encodeURIComponent;
const sourceTypes = [["CLASSIC", "经典古籍"], ["PHYSICIAN_WORK", "医家著作"], ["COMMENTARY", "注释评述"], ["FORMULA_BOOK", "方书"], ["MATERIA_MEDICA", "本草"], ["MEDICAL_CASE_COLLECTION", "医案集"], ["TEXTBOOK", "教材"], ["GUIDELINE", "指南"], ["MODERN_RESEARCH", "现代研究"], ["OTHER", "其他"]];

function Locator({ value }: { value: Record<string, unknown> }) {
  return <dl className="kwLocator">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{({ page_no: "页", chapter_no: "章", paragraph_no: "段", start: "起点", end: "终点" } as Record<string, string>)[key] ?? key}</dt><dd>{typeof item === "object" ? JSON.stringify(item) : String(item ?? "—")}</dd></div>)}</dl>;
}

function draftTitle(row: Draft) { return row.canonical_name || row.original_name || row.assertion_text || "知识候选"; }

function DraftDetails({ draft }: { draft: Draft }) {
  const names: Record<ReviewKind, string> = { concept: "概念", herb: "药物", relation: "关系", formula_revision: "方剂" };
  return <><p>{names[draft.kind]}{draft.concept_type && ` · ${draft.concept_type}`}{draft.relation_type && ` · ${draft.relation_type}`}{(draft.terms?.length ?? 0) > 0 && ` · 术语：${draft.terms!.join("、")}`}</p>{draft.ingredients && <dl className="kwIngredients">{draft.ingredients.map((item, index) => <div key={index}><dt>{item.original_name}</dt><dd>{[item.amount_original, item.unit].filter(Boolean).join(" ") || "原文未标剂量"}</dd></div>)}</dl>}{draft.method && <p>原文方法：{draft.method}</p>}</>;
}

async function fileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("无法读取来源文件"));
    reader.readAsDataURL(file);
  });
}

export default function KnowledgeWorkspace({ sessionActive, csrf, initialSourceId, onPublished, onResearch, onEvidence }: Props) {
  const [tab, setTab] = useState<"sources" | "review" | "publish">("sources");
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [revision, setRevision] = useState(0);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [after, setAfter] = useState(-1);
  const [hasMore, setHasMore] = useState(false);
  const [selectedSegments, setSelectedSegments] = useState<string[]>([]);
  const [focusedSegment, setFocusedSegment] = useState("");
  const [candidates, setCandidates] = useState<Candidates | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState("");
  const [reviewTarget, setReviewTarget] = useState<{ kind: string; ref: string; label: string } | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [versionId, setVersionId] = useState("");
  const [version, setVersion] = useState<VersionDetail | null>(null);
  const [publishedSources, setPublishedSources] = useState<{ source_id: string; title: string }[]>([]);
  const [configuration, setConfiguration] = useState<PublicationConfig | null>(null);
  const [job, setJob] = useState<(Job & { purpose: "import" | "publish"; source_id?: string }) | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [era, setEra] = useState("");
  const [edition, setEdition] = useState("");
  const [sourceType, setSourceType] = useState("CLASSIC");
  const [copyright, setCopyright] = useState("UNKNOWN");
  const [dataLevel, setDataLevel] = useState("RESTRICTED");
  const [outboundAuthorized, setOutboundAuthorized] = useState(false);
  const [outboundReason, setOutboundReason] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [newRevision, setNewRevision] = useState(false);
  const [strength, setStrength] = useState("DIRECT");
  const [draftKind, setDraftKind] = useState<DraftKind>("concept");
  const [draftName, setDraftName] = useState("");
  const [conceptType, setConceptType] = useState("THEORY");
  const [terms, setTerms] = useState("");
  const [issueNote, setIssueNote] = useState("");
  const [selectedIssue, setSelectedIssue] = useState("");
  const sourceGeneration = useRef(0);

  const refreshOverview = useCallback(async () => {
    const [nextSources, nextQuality, nextIssues, nextVersions] = await Promise.all([
      requestJson<Source[]>(`${base}/sources?limit=100`), requestJson<Quality>(`${base}/quality-report`),
      requestJson<Issue[]>(`${base}/quality-issues?status=OPEN`), requestJson<Version[]>(`${base}/versions`),
    ]);
    setSources(nextSources); setQuality(nextQuality); setIssues(nextIssues); setVersions(nextVersions);
  }, []);

  const refreshReview = useCallback(async (id: string) => {
    const generation = sourceGeneration.current;
    const [nextEvidence, concepts, herbs, relations, formulas] = await Promise.all([
      requestJson<Evidence[]>(`${base}/evidence?limit=100${id ? `&source_id=${enc(id)}` : ""}`),
      requestJson<{ ref: string; status: string }[]>(`${base}/drafts/concept`),
      requestJson<{ ref: string; status: string }[]>(`${base}/drafts/herb`),
      requestJson<{ ref: string; status: string }[]>(`${base}/drafts/relation`),
      requestJson<{ ref: string; status: string }[]>(`${base}/drafts/formula_revision`),
    ]);
    const detail = await Promise.all(([...concepts.map(row => ({ ...row, kind: "concept" as const })), ...herbs.map(row => ({ ...row, kind: "herb" as const })), ...relations.map(row => ({ ...row, kind: "relation" as const })), ...formulas.map(row => ({ ...row, kind: "formula_revision" as const }))]).map(async row => ({ ...await requestJson<Draft>(`${base}/drafts/${row.kind}/${enc(row.ref)}`), kind: row.kind })));
    if (generation === sourceGeneration.current) { setEvidence(nextEvidence); setDrafts(id ? detail.filter(row => row.evidence.some(item => item.source_id === id)) : detail); }
  }, []);

  const refreshSource = useCallback(async (id: string) => {
    const detail = await requestJson<SourceDetail>(`${base}/sources/${enc(id)}`);
    setSource(detail);
    return detail;
  }, []);

  const refreshVersion = useCallback(async (id: string) => {
    const detail = await requestJson<VersionDetail>(`${base}/versions/${enc(id)}`);
    setVersion(detail); return detail;
  }, []);

  async function action(work: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await work(); } catch (cause) { setError(apiErrorText(cause)); } finally { setBusy(false); }
  }

  useEffect(() => {
    if (initialSourceId) { setSourceId(initialSourceId); setTab("sources"); }
  }, [initialSourceId]);

  useEffect(() => {
    if (!sessionActive) { setSources([]); setSource(null); setEvidence([]); setDrafts([]); setSegments([]); setJob(null); return; }
    let current = true;
    void refreshOverview().catch(cause => { if (current) setError(apiErrorText(cause)); });
    void requestJson<PublicationConfig>(`${base}/publication-config`).then(value => { if (current) setConfiguration(value); }).catch(() => { if (current) setConfiguration(null); });
    return () => { current = false; };
  }, [sessionActive, refreshOverview]);

  useEffect(() => {
    if (!sessionActive || !sourceId) return;
    let current = true;
    const generation = ++sourceGeneration.current;
    setSegments([]); setSelectedSegments([]); setFocusedSegment(""); setSelectedEvidence(""); setReviewTarget(null); setSource(null); setCandidates(null);
    void requestJson<SourceDetail>(`${base}/sources/${enc(sourceId)}`).then(detail => {
      if (!current || sourceGeneration.current !== generation) return;
      setSource(detail); setRevision(detail.revisions.at(-1)?.revision_no ?? 0); setAfter(-1);
    }).catch(cause => { if (current) setError(apiErrorText(cause)); });
    void refreshReview(sourceId).catch(cause => { if (current) setError(apiErrorText(cause)); });
    return () => { current = false; };
  }, [sourceId, sessionActive, refreshReview]);

  useEffect(() => {
    if (!sessionActive || !sourceId || !revision) return;
    let current = true;
    setSegments([]); setSelectedSegments([]); setFocusedSegment(""); setAfter(-1); setCandidates(null);
    void requestJson<Segment[]>(`${base}/sources/${enc(sourceId)}/revisions/${revision}/segments?limit=50`).then(rows => {
      if (current) { setSegments(rows); setHasMore(rows.length === 50); setFocusedSegment(rows[0]?.segment_id ?? ""); }
    }).catch(cause => { if (current) setError(apiErrorText(cause)); });
    return () => { current = false; };
  }, [sourceId, revision, sessionActive]);

  useEffect(() => {
    if (!sessionActive || !versionId) return;
    let current = true;
    void requestJson<VersionDetail>(`${base}/versions/${enc(versionId)}`).then(value => { if (current) setVersion(value); }).catch(cause => { if (current) setError(apiErrorText(cause)); });
    return () => { current = false; };
  }, [versionId, sessionActive]);

  useEffect(() => {
    setPublishedSources([]);
    if (!sessionActive || !version?.active) return;
    let current = true;
    void requestJson<Evidence[]>(`${base}/evidence?version_id=${enc(version.version_id)}&limit=100`).then(rows => {
      if (current) setPublishedSources([...new Map(rows.map(row => [row.source_id, { source_id: row.source_id, title: row.source_title }])).values()]);
    }).catch(cause => { if (current) setError(apiErrorText(cause)); });
    return () => { current = false; };
  }, [version?.version_id, version?.active, sessionActive]);

  useEffect(() => {
    if (!sessionActive || !job || terminal(job.status)) return;
    let current = true;
    const timer = window.setInterval(() => {
      void requestJson<Job>(`/api/v1/jobs/${enc(job.job_id)}`).then(async next => {
        if (!current) return;
        setJob(previous => previous ? { ...previous, ...next } : null);
        if (terminal(next.status)) {
          await refreshOverview();
          if (job.purpose === "import" && job.source_id) {
            const detail = await refreshSource(job.source_id);
            setRevision(detail.revisions.at(-1)?.revision_no ?? 0);
            const rows = await requestJson<Segment[]>(`${base}/sources/${enc(job.source_id)}/revisions/${detail.revisions.at(-1)?.revision_no}/segments?limit=50`);
            setSegments(rows); setHasMore(rows.length === 50); setFocusedSegment(rows[0]?.segment_id ?? "");
          }
          if (job.purpose === "publish" && versionId) await refreshVersion(versionId);
        }
      }).catch(cause => { if (current) setError(apiErrorText(cause)); });
    }, 2000);
    return () => { current = false; window.clearInterval(timer); };
  }, [sessionActive, job, versionId, refreshOverview, refreshSource, refreshVersion]);

  async function importSource(event: FormEvent) {
    event.preventDefault();
    if (!file || !title.trim()) return;
    await action(async () => {
      const format = file.name.split(".").at(-1)?.toLowerCase();
      if (!["txt", "pdf", "docx"].includes(format ?? "")) throw new Error("请选择 TXT、PDF 或 DOCX 文件。");
      const result = await postJson<{ source_id: string; revision_no: number; job_id: string | null; status: string }>(`${base}/sources/import`, {
        metadata: { title: title.trim(), source_type: sourceType, author: author.trim() || null, era: era.trim() || null, edition: edition.trim() || null, copyright_status: copyright, data_level: dataLevel, outbound_authorized: dataLevel === "PUBLIC" && outboundAuthorized, outbound_reason: dataLevel === "PUBLIC" && outboundAuthorized ? outboundReason.trim() : null },
        file_format: format, content_base64: await fileBase64(file), ...(newRevision && sourceId ? { source_id: sourceId } : {}),
      }, csrf);
      await refreshOverview(); setSourceId(result.source_id); setRevision(result.revision_no);
      if (result.job_id) setJob({ job_id: result.job_id, status: result.status, purpose: "import", source_id: result.source_id });
      else { await refreshSource(result.source_id); setNotice(`来源登记完成：${displayStatus(result.status)}。`); }
    });
  }

  async function createEvidence() {
    await action(async () => {
      const result = await postJson<Evidence>(`${base}/drafts/evidence`, { segment_ids: segments.filter(row => selectedSegments.includes(row.segment_id)).map(row => `${row.segment_id}@${revision}`), strength }, csrf);
      await refreshReview(sourceId); setSelectedEvidence(evidenceRef(result)); setTab("review"); setReviewTarget({ kind: "evidence_revision", ref: evidenceRef(result), label: "原文证据" }); setReviewNote(""); setNotice("精确证据草稿已创建，请核对原文、上下文与引用位置后审核。");
    });
  }

  async function createDraft(event: FormEvent) {
    event.preventDefault(); const item = evidence.find(row => evidenceRef(row) === selectedEvidence);
    if (!item) return;
    await action(async () => {
      await postJson(`${base}/drafts/${draftKind === "concept" ? "concepts" : "herbs"}`, { canonical_name: draftName.trim(), evidence_id: item.evidence_id, evidence_revision_no: item.revision_no, terms: [...new Set(terms.split(/[、,，\n]/).map(value => value.trim()).filter(Boolean))], ...(draftKind === "concept" ? { concept_type: conceptType } : {}), era: source?.era ?? null }, csrf);
      await refreshReview(sourceId); setDraftName(""); setTerms(""); setNotice("知识草稿已创建，需人工审核后才能进入版本快照。");
    });
  }

  async function review(decision: "APPROVE" | "REJECT") {
    if (!reviewTarget || !reviewNote.trim()) return;
    await action(async () => {
      await postJson(`${base}/reviews/${reviewTarget.kind}/${enc(reviewTarget.ref)}`, { decision, note: reviewNote.trim() }, csrf);
      await Promise.all([refreshReview(sourceId), refreshOverview()]); setReviewTarget(null); setReviewNote(""); setNotice(decision === "APPROVE" ? "人工审核记录已保存。" : "已拒绝并保存说明。");
    });
  }

  async function publish() {
    await action(async () => {
      const configured = await requestJson<PublicationConfig>(`${base}/publication-config`);
      setConfiguration(configured);
      if (configured.available === false || !configured.configuration) throw new Error(configured.detail || "发布配置尚未就绪，请由管理员配置后重试。");
      const result = await postJson<Job>(`${base}/versions/${enc(versionId)}/publish`, configured.configuration, csrf);
      setJob({ ...result, purpose: "publish" }); await refreshVersion(versionId); setNotice("发布任务已提交，索引构建完成后可激活检索版本。");
    });
  }

  const focused = segments.find(row => row.segment_id === focusedSegment);
  const chosenEvidence = evidence.find(row => evidenceRef(row) === selectedEvidence);
  const currentRevision = source?.revisions.find(row => row.revision_no === revision);
  const selectable = (row: Segment) => ["CLAUSE", "PARAGRAPH", "SENTENCE", "COMMENTARY", "NOTE", "CASE_NOTE", "FORMULA_TEXT"].includes(row.segment_type);
  const reviewedEvidence = evidence.filter(row => row.status === "REVIEWED");
  const readyBuild = version?.index_builds.find(row => row.status === "READY");

  return <section className="kwWorkspace panel" aria-labelledby="kw-title">
    <header className="kwHeader"><div><span className="sectionLabel">知识底座</span><h2 id="kw-title">导入原文，审核证据，发布知识</h2><p>每一条知识都保留来源修订和精确引用。人工审核记录与发布版本可追溯。</p></div><button type="button" disabled={!sessionActive || busy} onClick={() => void action(async () => { await refreshOverview(); if (sourceId) { await refreshSource(sourceId); await refreshReview(sourceId); } if (versionId) await refreshVersion(versionId); })}>刷新状态</button></header>
    {!sessionActive ? <p className="kwEmpty">请在页头连接本机工作区，随后可导入来源、审核证据与发布版本。</p> : <>
      <nav className="kwTabs" aria-label="知识工作区"><button className={tab === "sources" ? "active" : ""} onClick={() => setTab("sources")}>1 · 来源与原文</button><button className={tab === "review" ? "active" : ""} onClick={() => setTab("review")}>2 · 证据与人工审核</button><button className={tab === "publish" ? "active" : ""} onClick={() => setTab("publish")}>3 · 质量与版本发布</button></nav>
      {error && <p className="kwError" role="alert">{error}</p>}{notice && <p className="kwNotice" role="status">{notice}</p>}
      {job && <aside className={`kwJob ${job.status === "FAILED" ? "failed" : ""}`} role="status"><strong>{job.purpose === "import" ? "来源解析" : "版本发布"}：{displayStatus(job.status)}</strong>{job.attempts != null && <span>尝试 {job.attempts} / {job.max_attempts}</span>}{job.error_code && <span>{job.error_code}</span>}<small>任务 {job.job_id}</small></aside>}
      {tab === "sources" && <>
        <details className="kwImport" open={!sources.length}><summary>导入新的来源文件</summary><form onSubmit={event => void importSource(event)} className="kwForm"><label>来源文件<input type="file" accept=".txt,.pdf,.docx" onChange={event => { const next = event.target.files?.[0] ?? null; setFile(next); if (next && !title) setTitle(next.name.replace(/\.[^.]+$/, "")); }} required /></label><label>书名 / 文献标题<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={500} /></label><label>来源类型<select value={sourceType} onChange={event => setSourceType(event.target.value)}>{sourceTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>作者<input value={author} onChange={event => setAuthor(event.target.value)} maxLength={300} /></label><label>时代<input value={era} onChange={event => setEra(event.target.value)} maxLength={120} /></label><label>版本 / 版次<input value={edition} onChange={event => setEdition(event.target.value)} maxLength={300} /></label><label>版权状态<select value={copyright} onChange={event => setCopyright(event.target.value)}><option value="UNKNOWN">待核实</option><option value="PUBLIC_DOMAIN">公版</option><option value="AUTHORIZED">已授权</option><option value="COPYRIGHTED">受版权保护</option></select></label><label>资料分级<select value={dataLevel} onChange={event => { setDataLevel(event.target.value); if (event.target.value !== "PUBLIC") { setOutboundAuthorized(false); setOutboundReason(""); } }}><option value="RESTRICTED">受限资料</option><option value="PUBLIC">公开资料</option><option value="SENSITIVE">敏感资料</option></select></label><label className="kwInline"><input type="checkbox" checked={outboundAuthorized} disabled={dataLevel !== "PUBLIC"} onChange={event => setOutboundAuthorized(event.target.checked)} />允许此公开来源的原文用于云端研究生成</label>{outboundAuthorized && dataLevel === "PUBLIC" && <label>外发授权理由<input value={outboundReason} onChange={event => setOutboundReason(event.target.value)} required maxLength={500} placeholder="例如：公版资料，授权本次研究引用与模型分析" /></label>}<label className="kwInline"><input type="checkbox" checked={newRevision} disabled={!sourceId} onChange={event => setNewRevision(event.target.checked)} />作为所选来源的新修订{source && `（${source.title}）`}</label><p className="kwHint">文件保存在本地；公开来源可单独授权云端研究使用原文。受限和敏感资料保持本地。扫描 PDF 需要 OCR 时会显示阻断状态。</p><button disabled={busy || !file || !title.trim() || (outboundAuthorized && dataLevel === "PUBLIC" && !outboundReason.trim())}>{busy ? "处理中…" : "导入并解析"}</button></form></details>
        <div className="kwSourceGrid"><aside className="kwSourceList"><h3>来源目录</h3>{!sources.length && <p className="kwEmpty">导入第一份真实来源开始建立知识库。</p>}{sources.map(row => <button key={row.source_id} className={sourceId === row.source_id ? "selected" : ""} onClick={() => { setSourceId(row.source_id); setNewRevision(false); }}><strong>{row.title}</strong><small>{displayStatus(row.status)} · {row.data_level === "PUBLIC" ? "公开" : row.data_level === "SENSITIVE" ? "敏感" : "受限"}</small></button>)}</aside><div className="kwSourceContent">{!source ? <p className="kwEmpty">选择来源查看修订和原文。</p> : <>
          <header className="kwSourceTitle"><div><h3>{source.title}</h3><p>{[source.author, source.era, source.edition].filter(Boolean).join(" · ") || "尚未填写作者与版次"}</p></div><label>来源修订<select value={revision} onChange={event => setRevision(Number(event.target.value))}>{source.revisions.map(row => <option key={row.revision_no} value={row.revision_no}>修订 {row.revision_no} · {row.file_format.toUpperCase()} · {displayStatus(row.status)}</option>)}</select></label></header>
          {currentRevision?.error_code && <p className="kwError" role="alert">解析未完成：{currentRevision.error_code}。此修订暂不能创建精确证据。</p>}
          <div className="kwSegmentGrid"><div className="kwSegments"><h4>章节与段落</h4>{segments.map(row => <div key={row.segment_id} className={`kwSegmentRow ${row.segment_id === focusedSegment ? "selected" : ""} ${row.parent_segment_id ? "child" : ""}`}><input aria-label={`选中段落 ${row.sequence_no + 1}`} type="checkbox" disabled={!selectable(row) || busy} checked={selectedSegments.includes(row.segment_id)} onChange={event => setSelectedSegments(values => event.target.checked ? [...values, row.segment_id] : values.filter(id => id !== row.segment_id))} /><button onClick={() => setFocusedSegment(row.segment_id)}><small>{row.page_no != null ? `第 ${row.page_no} 页 · ` : ""}{row.chapter_no != null ? `第 ${row.chapter_no} 章 · ` : ""}{row.paragraph_no != null ? `第 ${row.paragraph_no} 段` : `段落 ${row.sequence_no + 1}`}</small><span>{row.original_text.slice(0, 90)}</span></button></div>)}{!segments.length && <p className="kwEmpty">尚无可用段落，等待来源解析完成后刷新。</p>}{hasMore && <button disabled={busy} onClick={() => void action(async () => { const cursor = segments.at(-1)?.sequence_no ?? after; const rows = await requestJson<Segment[]>(`${base}/sources/${enc(sourceId)}/revisions/${revision}/segments?limit=50&after=${cursor}`); setSegments(values => [...values, ...rows]); setAfter(cursor); setHasMore(rows.length === 50); })}>加载后续段落</button>}</div><article className="kwOriginal">{focused ? <><h4>原文</h4><blockquote>{focused.original_text}</blockquote><h4>规范文本</h4><p>{focused.normalized_text || "未生成规范文本"}</p><details><summary>查看上下文</summary><h5>上文</h5><p>{focused.context_before || "无上文"}</p><h5>下文</h5><p>{focused.context_after || "无下文"}</p></details><h4>精确引用位置</h4><Locator value={focused.locator} /></> : <p className="kwEmpty">选择段落查看原文、规范文本与上下文。</p>}</article></div>
          <div className="kwEvidenceBar"><span>已选 {selectedSegments.length} 个原文段落</span><label>证据强度<select value={strength} onChange={event => setStrength(event.target.value)}>{[["DIRECT", "直接证据"], ["INDIRECT", "间接证据"], ["INTERPRETIVE", "解释性证据"], ["EMPIRICAL", "经验性证据"], ["BACKGROUND", "背景证据"], ["UNVERIFIED", "待核实"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button disabled={busy || !selectedSegments.length || currentRevision?.status !== "SEGMENTED"} onClick={() => void createEvidence()}>创建精确证据草稿</button><small>仅引用所选连续段落；上下文保留为上下文。</small></div>
          <div className="kwExtraction"><div className="kwActions"><button disabled={busy || currentRevision?.status !== "SEGMENTED"} onClick={() => void action(async () => { const result = await postJson<Candidates>(`${base}/sources/${enc(sourceId)}/revisions/${revision}/extract`, {}, csrf); setCandidates(result); await Promise.all([refreshReview(sourceId), refreshOverview()]); setNotice("原文候选提取完成。证据、概念、关系和方剂均为草稿，请逐项人工核对。"); })}>从此修订提取知识候选</button><button disabled={busy || currentRevision?.status !== "SEGMENTED"} onClick={() => void action(async () => { setCandidates(await requestJson<Candidates>(`${base}/sources/${enc(sourceId)}/revisions/${revision}/candidates`)); await refreshReview(sourceId); })}>查看已有候选</button><button onClick={() => setTab("review")}>前往审核</button></div><p className="kwHint">按原文规则生成候选，保留提及位置；可能存在歧义，不会自动审核。</p>{candidates && <div className="kwCandidateSummary"><p>原文段落 {candidates.segment_count} · 提及 {candidates.mention_count} · 概念 {candidates.concept_count} · 关系 {candidates.relation_count} · 方剂 {candidates.formula_count}</p><details><summary>查看原文提及位置与歧义</summary>{candidates.segments.filter(row => row.mentions.length > 0).map(row => <article key={row.segment_ref}><small>{row.segment_ref}</small>{row.mentions.map((mention, index) => <p key={index}><strong>{mention.surface_text}</strong> · 字符 {mention.start_offset}–{mention.end_offset}{mention.ambiguous && <span className="kwBadge">需消歧</span>}</p>)}</article>)}<small>提取器 {candidates.extractor_version}</small></details></div>}</div>
        </>}</div></div>
      </>}
      {tab === "review" && <>
        <div className="kwReviewHead"><label>审核范围<select value={sourceId} onChange={event => { setSourceId(event.target.value); if (!event.target.value) void action(() => refreshReview("")); }}><option value="">全部来源</option>{sources.map(row => <option key={row.source_id} value={row.source_id}>{row.title}</option>)}</select></label><span>审核通过后才会纳入知识版本。审核说明为必填。</span></div>
        <div className="kwReviewGrid"><div><h3>原文证据</h3>{!evidence.length && <p className="kwEmpty">先在来源中选取段落创建证据草稿。</p>}{evidence.map(row => <article className={`kwCard ${selectedEvidence === evidenceRef(row) ? "selected" : ""}`} key={evidenceRef(row)}><div className="kwCardHead"><strong>{row.source_title} · 修订 {row.source_revision_no}</strong><span className="kwBadge">{displayStatus(row.status)}</span></div><blockquote>{row.quote_text}</blockquote><details><summary>原文上下文与引用位置</summary><h5>上文</h5><p>{row.context_before || "无上文"}</p><h5>下文</h5><p>{row.context_after || "无下文"}</p><Locator value={row.citation_locator} /></details><div className="kwActions"><button disabled={busy} onClick={() => { setSelectedEvidence(evidenceRef(row)); setReviewTarget(row.status === "DRAFT" ? { kind: "evidence_revision", ref: evidenceRef(row), label: "原文证据" } : null); setReviewNote(""); }}>{row.status === "DRAFT" ? "核对并审核" : "选择此证据"}</button>{onEvidence && <button onClick={() => onEvidence({ evidence_id: row.evidence_id, revision_no: row.revision_no })}>查看完整证据</button>}</div></article>)}</div><div><h3>建立知识草稿</h3><form className="kwForm kwDraftForm" onSubmit={event => void createDraft(event)}><label>已审核的原文证据<select value={selectedEvidence} onChange={event => setSelectedEvidence(event.target.value)} required><option value="">请选择证据</option>{reviewedEvidence.map(row => <option value={evidenceRef(row)} key={evidenceRef(row)}>{row.source_title}：{row.quote_text.slice(0, 55)}</option>)}</select></label><label>知识类型<select value={draftKind} onChange={event => setDraftKind(event.target.value as DraftKind)}><option value="concept">概念</option><option value="herb">药物</option></select></label><label>规范名称<input value={draftName} onChange={event => setDraftName(event.target.value)} required maxLength={300} placeholder="依据选定原文填写" /></label>{draftKind === "concept" && <label>概念类别<select value={conceptType} onChange={event => setConceptType(event.target.value)}><option value="THEORY">理论</option><option value="DISEASE">病证</option><option value="SYMPTOM">症状</option><option value="TREATMENT">治法</option><option value="OTHER">其他</option></select></label>}<label>原文术语 / 别名<input value={terms} onChange={event => setTerms(event.target.value)} placeholder="以逗号分隔；无别名可留空" /></label><button disabled={busy || !draftName.trim() || chosenEvidence?.status !== "REVIEWED"}>建立待审核草稿</button></form><h3>知识草稿与审核记录</h3>{!drafts.length && <p className="kwEmpty">创建的概念或药物草稿会显示在这里。</p>}{drafts.map(row => <article className="kwCard" key={row.ref}><div className="kwCardHead"><strong>{draftTitle(row)}</strong><span className="kwBadge">{displayStatus(row.status)}</span></div><DraftDetails draft={row} />{row.evidence.map(item => <blockquote key={evidenceRef(item)}>{item.quote_text}<cite>{item.source_title} · 来源修订 {item.source_revision_no}</cite></blockquote>)}{row.status === "DRAFT" && <button disabled={busy} onClick={() => { setReviewTarget({ kind: row.kind, ref: row.ref, label: draftTitle(row) }); setReviewNote(""); }}>审核此草稿</button>}</article>)}</div></div>
        {reviewTarget && <section className="kwReviewAction" aria-label="人工审核"><h3>人工审核：{reviewTarget.label}</h3><label>审核 / 拒绝说明<textarea value={reviewNote} onChange={event => setReviewNote(event.target.value)} placeholder="记录核对原文、解释边界或拒绝原因" maxLength={4000} required /></label><div className="kwActions"><button disabled={busy || !reviewNote.trim()} onClick={() => void review("APPROVE")}>确认审核通过</button><button className="kwReject" disabled={busy || !reviewNote.trim()} onClick={() => void review("REJECT")}>拒绝并记录原因</button><button onClick={() => setReviewTarget(null)}>取消</button></div><p className="kwHint">由当前会话操作者提交人工审核；不会自动标记医学专家审核。</p></section>}
      </>}
      {tab === "publish" && <>
        <div className={`kwQuality ${quality?.publication_blocked ? "blocked" : ""}`}><div><h3>{quality?.publication_blocked ? "质量阻断：暂不能发布" : "发布质量概况"}</h3><p>阻断 {quality?.open_issues.BLOCKER ?? "—"} · 警告 {quality?.open_issues.WARNING ?? "—"} · 提示 {quality?.open_issues.INFO ?? "—"}</p></div><button disabled={busy || !quality || quality.publication_blocked} onClick={() => void action(async () => { const result = await postJson<Version>(`${base}/versions`, {}, csrf); await refreshOverview(); setVersionId(result.version_id); setNotice("已生成不可变知识快照，仅包含已审核对象。"); })}>创建已审核知识快照</button></div>
        {issues.map(row => <article className="kwCard" key={row.issue_id}><div className="kwCardHead"><strong>{row.issue_type}</strong><span className="kwBadge">{row.severity === "BLOCKER" ? "阻断发布" : row.severity === "WARNING" ? "警告" : "提示"}</span></div><p>{row.description}</p><small>{row.target_kind} · {row.target_ref}</small><button disabled={busy} onClick={() => { setSelectedIssue(row.issue_id); setIssueNote(""); }}>处理此问题</button>{selectedIssue === row.issue_id && <div className="kwIssueAction"><label>处理说明<textarea value={issueNote} onChange={event => setIssueNote(event.target.value)} maxLength={4000} /></label><button disabled={busy || !issueNote.trim()} onClick={() => void action(async () => { await postJson(`${base}/quality-issues/${enc(row.issue_id)}/resolve`, { note: issueNote.trim(), waive: false }, csrf); await refreshOverview(); setSelectedIssue(""); setNotice("质量问题处理记录已保存。"); })}>记录已解决</button></div>}</article>)}
        <div className="kwVersionGrid"><aside className="kwVersions"><h3>知识版本</h3>{versions.map(row => <button key={row.version_id} className={versionId === row.version_id ? "selected" : ""} onClick={() => { setVersionId(row.version_id); setVersion(null); }}><strong>版本 {row.version_no}{row.active && " · 当前检索版本"}</strong><small>{displayStatus(row.status)}</small></button>)}{!versions.length && <p className="kwEmpty">审核完成后创建第一个版本快照。</p>}</aside><div>{version ? <><h3>版本 {version.version_no} · {displayStatus(version.status)}</h3><p>已审核对象：{Object.entries(version.item_counts).map(([kind, count]) => `${({ concept: "概念", herb: "药物", evidence_revision: "证据", formula_revision: "方剂", relation: "关系" } as Record<string, string>)[kind] ?? kind} ${count}`).join(" · ")}</p><details><summary>快照校验摘要</summary><code>{version.manifest_hash}</code></details><p className="kwHint">发布方式：{configuration?.configuration?.strategy === "local-fts-exact-v1" ? "本地全文、精确与结构索引，无模型调用" : configuration?.configuration?.strategy === "hybrid-rrf-v1" ? "混合索引，含向量与重排模型调用" : "以管理员提供的发布配置为准"}</p>{version.index_builds.map(row => <div className="kwBuild" key={row.index_build_id}><strong>索引：{displayStatus(row.status)}</strong><span>全文 {displayStatus(row.fts_status)} · 向量 {displayStatus(row.vector_status)}</span></div>)}<div className="kwActions"><button disabled={busy || quality?.publication_blocked || configuration?.available === false || !configuration || !["PRE_PUBLISH_SNAPSHOT", "INDEXING", "VALIDATING"].includes(version.status)} onClick={() => void publish()}>发布并构建索引</button><button disabled={busy || !readyBuild || version.active || quality?.publication_blocked} onClick={() => void action(async () => { await postJson(`${base}/versions/${enc(versionId)}/activate`, { index_build_id: readyBuild!.index_build_id }, csrf); await Promise.all([refreshOverview(), refreshVersion(versionId)]); onPublished?.(); setNotice("版本已激活，可在检索工作区查询此版本中的证据。"); })}>激活为当前检索版本</button></div>{configuration?.available === false && <p className="kwError">{configuration.detail || "发布配置未就绪。"}</p>}{version.active && <div className="kwPublished"><strong>此版本已在检索中生效</strong><div className="kwActions"><button onClick={() => onPublished?.()}>前往知识检索</button>{onResearch && publishedSources.map(row => <button key={row.source_id} onClick={() => onResearch(row.source_id)}>研究：{row.title}</button>)}</div></div>}</> : <p className="kwEmpty">选择快照查看索引构建与发布状态。</p>}</div></div>
      </>}
    </>}
  </section>;
}
