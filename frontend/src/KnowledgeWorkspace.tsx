import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { requestJson, postJson, apiErrorText } from "./api";
import { invalidEvidenceRange, readingText } from "./knowledgeSelection";
import { citationLocation } from "./citation";
import type { SourceCitation } from "./citation";
import type { EvidenceDetail } from "./EvidenceDrawer";
import FormulaEditor from "./FormulaEditor";
import type { FormulaInput } from "./FormulaEditor";
import "./knowledge.css";
import { JobsPanel } from "./JobsPanel";

type Props = { sessionActive: boolean; csrf: string; initialSourceId?: string; initialCitation?: SourceCitation; onReturnCitation?: () => void; onPublished?: () => void; onResearch?: (sourceId: string) => void; onEvidence?: (ref: { evidence_id: string; revision_no: number }) => void };
type Source = { source_id: string; title: string; source_type: string; status: string; data_level: string };
type SourceDetail = Source & { author: string | null; era: string | null; edition: string | null; copyright_status: string; outbound_authorized: boolean; outbound_reason?: string | null; revisions: { revision_no: number; status: string; file_format: string; file_size_bytes: number; error_code: string | null }[] };
type Segment = { segment_id: string; sequence_no: number; segment_type: string; original_text: string; normalized_text: string; context_before: string; context_after: string; locator: Record<string, unknown>; parent_segment_id: string | null; page_no: number | null; chapter_no: number | null; paragraph_no: number | null };
type Evidence = { evidence_id: string; revision_no: number; status: string; evidence_strength: string; source_title: string; source_id: string; source_revision_no: number; quote_text: string; context_before: string; context_after: string; citation_locator: Record<string, unknown>; segment_ids: string[] };
type DraftKind = "concept" | "herb" | "formula";
type ReviewKind = "concept" | "herb" | "relation" | "formula_revision";
type FieldSource = { field_key: string; segment_ref: string; evidence_ref?: string; start_offset?: number; end_offset?: number; start?: number; end?: number; quote_text?: string; basis: string | null };
type Draft = { ref: string; status: string; kind: ReviewKind; canonical_name?: string; original_name?: string; assertion_text?: string; concept_type?: string; relation_type?: string; terms?: string[]; ingredients?: { original_name: string; amount_original: string | null; amount_normalized?: string | number | null; unit: string | null; processing?: string | null }[]; method?: string | null; indications?: string | null; effects?: string | null; preparation?: string | null; cautions?: string | null; evidence: Evidence[]; field_sources?: FieldSource[] };
type Candidates = { extraction_id: string; extractor_version: string; segment_count: number; mention_count: number; relation_count: number; concept_count: number; formula_count: number; evidence: Evidence[]; concepts: { concept_id: string }[]; relations: { relation_id: string }[]; formulas: { formula_id: string; revision_no: number }[]; segments: { segment_ref: string; mentions: { surface_text: string; start_offset: number; end_offset: number; ambiguous: boolean }[] }[] };
type Issue = { issue_id: string; issue_type: string; severity: string; target_kind: string; target_ref: string; description: string; status: string; resolution_note: string | null };
type Quality = { open_issues: Record<string, number>; publication_blocked: boolean; active_version_id: string | null };
type Version = { version_id: string; version_no: number; status: string; active: boolean; manifest_hash: string };
type VersionDetail = Version & { item_counts: Record<string, number>; publication_job?: Job | null; index_builds: { index_build_id: string; status: string; fts_status: string; vector_status: string }[] };
type PublicationPreview = { item_counts: Record<string, number>; excluded: { kind: string; status: string; count: number; reason: string }[]; sources: { source_id: string; title: string; revision_no: number; evidence_count: number }[] };
const kindNames: Record<string, string> = { concept: "概念", herb: "药物", evidence_revision: "证据", formula_revision: "方剂", relation: "关系" };
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

type WorkspacePosition = { sourceId?: string; revision?: number; tab?: "sources" | "review" | "publish"; focusedSegment?: string; through?: number; structureView?: boolean };
function savedPosition(): WorkspacePosition {
  try {
    const value = JSON.parse(sessionStorage.getItem("tcm.knowledge.position") || "{}");
    return value && typeof value === "object" && (value.sourceId === undefined || typeof value.sourceId === "string") ? value : {};
  }
  catch { return {}; }
}

function DisabledReason({ id, reason }: { id: string; reason: string }) {
  return reason ? <p id={id} className="kwHint kwDisabledReason" role="status">{reason}</p> : null;
}

function Locator({ value }: { value: Record<string, unknown> }) {
  return <dl className="kwLocator">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{({ page_no: "页", chapter_no: "章", paragraph_no: "段", start: "起点", end: "终点" } as Record<string, string>)[key] ?? key}</dt><dd>{typeof item === "object" ? JSON.stringify(item) : String(item ?? "—")}</dd></div>)}</dl>;
}

function CitationReading({ detail, rows, error, physicalPages }: { detail: EvidenceDetail | null; rows: Segment[]; error: string; physicalPages: boolean }) {
  if (error) return <p className="kwError" role="alert">引用原文读取失败：{error}</p>;
  if (!detail || rows.length !== detail.segment_ids.length) return <p className="kwEmpty" role="status">正在加载引用范围与上下文…</p>;
  return <><div className="kwReadingHead"><h4>引用原文</h4><span>{citationLocation(detail.citation_locator.start, physicalPages)} — {citationLocation(detail.citation_locator.end, physicalPages)}</span></div>
    <section className="kwCitationContext" aria-label="引用上文"><h5>上文{!detail.context_complete && "摘要"}</h5><p>{readingText(detail.full_context_before ?? detail.context_before) || "已读取，此范围没有上文"}</p></section>
    <blockquote className="kwCitedQuote">{rows.map(row => <p key={row.segment_id} data-cited-segment={row.segment_id}><mark>{readingText(row.original_text)}</mark></p>)}</blockquote>
    <section className="kwCitationContext" aria-label="引用下文"><h5>下文{!detail.context_complete && "摘要"}</h5><p>{readingText(detail.full_context_after ?? detail.context_after) || "已读取，此范围没有下文"}</p></section>
    <details className="kwCitation"><summary>查看保留物理换行的原始引用</summary><pre className="kwPhysicalText">{detail.quote_text}</pre></details>
  </>;
}

function draftTitle(row: Draft) { return row.canonical_name || row.original_name || row.assertion_text || "知识候选"; }

function originalDose(item: NonNullable<Draft["ingredients"]>[number]) {
  if (!item.amount_original) return "原文未标剂量";
  return item.unit && !item.amount_original.includes(item.unit) ? `${item.amount_original} ${item.unit}` : item.amount_original;
}

function DraftDetails({ draft }: { draft: Draft }) {
  const names: Record<ReviewKind, string> = { concept: "概念", herb: "药物", relation: "关系", formula_revision: "方剂" };
  return <><p>{names[draft.kind]}{draft.concept_type && ` · ${draft.concept_type}`}{draft.relation_type && ` · ${draft.relation_type}`}{(draft.terms?.length ?? 0) > 0 && ` · 术语：${draft.terms!.join("、")}`}</p>{draft.ingredients && <dl className="kwIngredients">{draft.ingredients.map((item, index) => <div key={index}><dt>{item.original_name}</dt><dd>原剂量：{originalDose(item)}{item.processing && ` · 炮制：${item.processing}`}<small>规范量：{item.amount_normalized ?? "未知，未换算"}</small></dd></div>)}</dl>}{draft.method && <p className="kwMethod">原文方法：{draft.method}</p>}{(draft.field_sources?.length ?? 0) > 0 && <details className="kwFieldSources"><summary>逐字段原文依据</summary>{draft.field_sources!.map((item, index) => <div key={index}><strong>{item.field_key}</strong><small>{item.segment_ref} · 字符 {item.start_offset ?? item.start}–{item.end_offset ?? item.end}</small>{item.quote_text && <blockquote>{readingText(item.quote_text)}</blockquote>}{item.basis && <p>{item.basis}</p>}</div>)}</details>}</>;
}

async function fileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("无法读取来源文件"));
    reader.readAsDataURL(file);
  });
}

export default function KnowledgeWorkspace({ sessionActive, csrf, initialSourceId, initialCitation, onReturnCitation, onPublished, onResearch, onEvidence }: Props) {
  const restored = useRef(savedPosition());
  const [tab, setTab] = useState<"sources" | "review" | "publish">(() => initialCitation || initialSourceId && initialSourceId !== restored.current.sourceId ? "sources" : ["sources", "review", "publish"].includes(restored.current.tab ?? "") ? restored.current.tab! : "sources");
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceSearch, setSourceSearch] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [sourceId, setSourceId] = useState(initialSourceId || restored.current.sourceId || "");
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [revision, setRevision] = useState(0);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [structureView, setStructureView] = useState(!initialCitation && restored.current.structureView === true);
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
  const [batchSelection, setBatchSelection] = useState<string[]>([]);
  const [batchNote, setBatchNote] = useState("");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [versionId, setVersionId] = useState("");
  const [version, setVersion] = useState<VersionDetail | null>(null);
  const [publishedSources, setPublishedSources] = useState<{ source_id: string; title: string }[]>([]);
  const [configuration, setConfiguration] = useState<PublicationConfig | null>(null);
  const [publicationPreview, setPublicationPreview] = useState<PublicationPreview | null>(null);
  const [formulaInitial, setFormulaInitial] = useState<FormulaInput>();
  const [formulaKey, setFormulaKey] = useState(0);
  const [job, setJob] = useState<(Job & { purpose: "import" | "publish"; source_id?: string }) | null>(null);
  const [busy, setBusy] = useState(false);
  const [operation, setOperation] = useState<{ label: string; started: number } | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [errorStep, setErrorStep] = useState("");
  const [reload, setReload] = useState(0);
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
  const reviewGeneration = useRef(0);
  const actionRunning = useRef(false);
  const loadedSegmentScope = useRef("");
  const [citationDetail, setCitationDetail] = useState<EvidenceDetail | null>(null);
  const [citationError, setCitationError] = useState("");
  const activeCitation = initialCitation?.source_id === sourceId && initialCitation.source_revision_no === revision ? initialCitation : undefined;
  const citedIds = activeCitation && citationDetail ? citationDetail.segment_ids : [];
  const citedRows = segments.filter(row => citedIds.includes(row.segment_id));

  useEffect(() => {
    setCitationDetail(null); setCitationError("");
    if (!sessionActive || !initialCitation) return;
    const controller = new AbortController();
    const target = initialCitation;
    void requestJson<EvidenceDetail>(`${base}/evidence/${enc(target.evidence.evidence_id)}?revision_no=${target.evidence.revision_no}`, { signal: controller.signal }).then(detail => {
      if (controller.signal.aborted) return;
      if (detail.source_id !== target.source_id || detail.source_revision_no !== target.source_revision_no || !detail.segment_ids.length) throw new Error("引用与来源修订不一致，无法定位；请返回证据核对。");
      setCitationDetail(detail);
    }).catch(cause => { if (!controller.signal.aborted) setCitationError(apiErrorText(cause)); });
    return () => controller.abort();
  }, [initialCitation, sessionActive, reload]);

  const refreshOverview = useCallback(async () => {
    const [nextSources, nextQuality, nextIssues, nextVersions, preview] = await Promise.all([
      requestJson<Source[]>(`${base}/sources?limit=100`), requestJson<Quality>(`${base}/quality-report`),
      requestJson<Issue[]>(`${base}/quality-issues?status=OPEN`), requestJson<Version[]>(`${base}/versions`),
      requestJson<PublicationPreview>(`${base}/publication-preview`),
    ]);
    setSources(nextSources); setQuality(nextQuality); setIssues(nextIssues); setVersions(nextVersions);
    setPublicationPreview(preview);
    setVersionId(previous => previous || nextVersions[0]?.version_id || "");
  }, []);

  const refreshReview = useCallback(async (id: string, revisionNo = 0) => {
    const generation = reviewGeneration.current;
    const scope = `?limit=100${id ? `&source_id=${enc(id)}${revisionNo ? `&source_revision_no=${revisionNo}` : ""}` : ""}`;
    async function allPages<T>(path: string): Promise<T[]> {
      const collected: T[] = [];
      for (let offset = 0; ; offset += 100) {
        if (generation !== reviewGeneration.current) return [];
        const rows = await requestJson<T[]>(`${path}&offset=${offset}`);
        collected.push(...rows);
        if (rows.length < 100) return collected;
      }
    }
    const [nextEvidence, concepts, herbs, relations, formulas] = await Promise.all([
      allPages<Evidence>(`${base}/evidence${scope}`),
      allPages<{ ref: string; status: string }>(`${base}/drafts/concept${scope}`),
      allPages<{ ref: string; status: string }>(`${base}/drafts/herb${scope}`),
      allPages<{ ref: string; status: string }>(`${base}/drafts/relation${scope}`),
      allPages<{ ref: string; status: string }>(`${base}/drafts/formula_revision${scope}`),
    ]);
    const references = [...concepts.map(row => ({ ...row, kind: "concept" as const })), ...herbs.map(row => ({ ...row, kind: "herb" as const })), ...relations.map(row => ({ ...row, kind: "relation" as const })), ...formulas.map(row => ({ ...row, kind: "formula_revision" as const }))];
    const detail: Draft[] = [];
    for (let offset = 0; offset < references.length; offset += 12) {
      if (generation !== reviewGeneration.current) return;
      detail.push(...await Promise.all(references.slice(offset, offset + 12).map(async row => ({ ...await requestJson<Draft>(`${base}/drafts/${row.kind}/${enc(row.ref)}`), kind: row.kind }))));
    }
    if (generation === reviewGeneration.current) {
      const scoped = nextEvidence.filter(row => !revisionNo || row.source_revision_no === revisionNo);
      setEvidence(scoped); setDrafts(detail);
      setSelectedEvidence(previous => scoped.some(row => evidenceRef(row) === previous && row.status === "REVIEWED") ? previous : scoped.find(row => row.status === "REVIEWED") ? evidenceRef(scoped.find(row => row.status === "REVIEWED")!) : "");
    }
  }, []);

  async function readCandidates(id: string, revisionNo: number) {
    try { return await requestJson<Candidates>(`${base}/sources/${enc(id)}/revisions/${revisionNo}/candidates`); }
    catch (cause) { if ((cause as { status?: number }).status === 404) return null; throw cause; }
  }

  async function extract() {
    await action(async () => {
      const result = await postJson<Candidates>(`${base}/sources/${enc(sourceId)}/revisions/${revision}/extract`, {}, csrf);
      setCandidates(result);
      setOperation(previous => previous ? { ...previous, label: "候选已生成，正在加载证据与知识草稿" } : null);
      await Promise.all([refreshReview(sourceId, revision), refreshOverview()]);
      setSelectedEvidence(result.evidence.find(row => row.status === "DRAFT") ? evidenceRef(result.evidence.find(row => row.status === "DRAFT")!) : "");
      setTab("review"); setNotice("候选已提取并标出本批。先核对并审核左侧原文证据，再审核右侧知识草稿。");
    }, "extract");
  }

  const refreshSource = useCallback(async (id: string) => {
    const generation = sourceGeneration.current;
    const detail = await requestJson<SourceDetail>(`${base}/sources/${enc(id)}`);
    if (generation === sourceGeneration.current) setSource(detail);
    return detail;
  }, []);

  const refreshVersion = useCallback(async (id: string) => {
    const detail = await requestJson<VersionDetail>(`${base}/versions/${enc(id)}`);
    setVersion(detail);
    if (detail.publication_job) setJob({ ...detail.publication_job, purpose: "publish" });
    return detail;
  }, []);

  async function action(work: () => Promise<void>, step = "overview") {
    if (actionRunning.current) return;
    actionRunning.current = true;
    setBusy(true); setError(""); setErrorStep(step); setNotice("");
    setElapsed(0); setOperation({ label: ({ extract: "正在提取知识候选", import: "正在上传文献", evidence: "正在创建精确证据", review: "正在保存审核记录", draft: "正在建立知识草稿" } as Record<string, string>)[step] || "正在读取和保存工作区", started: Date.now() });
    try { await work(); } catch (cause) { setError(apiErrorText(cause)); }
    finally { actionRunning.current = false; setBusy(false); setOperation(null); }
  }

  useEffect(() => {
    if (!operation) return;
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - operation.started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [operation]);

  useEffect(() => { setBatchSelection([]); setBatchNote(""); }, [sourceId, revision]);

  useEffect(() => {
    loadedSegmentScope.current = "";
    if (initialSourceId && initialSourceId !== sourceId) { setSourceId(initialSourceId); setTab("sources"); }
    if (initialCitation) { setSourceId(initialCitation.source_id); setTab("sources"); setStructureView(false); }
    else {
      restored.current = savedPosition();
      if (restored.current.sourceId === initialSourceId) {
        setTab(restored.current.tab ?? "sources"); setStructureView(restored.current.structureView === true);
      }
    }
  }, [initialSourceId, initialCitation]);

  useEffect(() => {
    if (!sessionActive || initialCitation || (sourceId && (source?.source_id !== sourceId || !revision || !segments.length || !loadedSegmentScope.current))) return;
    try { sessionStorage.setItem("tcm.knowledge.position", JSON.stringify({ sourceId, revision, tab, focusedSegment, through: segments.at(-1)?.sequence_no, structureView })); }
    catch { /* Reading and drafting remain available when browser storage is unavailable. */ }
  }, [sourceId, revision, tab, sessionActive, source?.source_id, initialCitation, focusedSegment, segments, structureView]);

  useEffect(() => {
    if (reviewTarget) document.querySelector(".kwReviewAction")?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [reviewTarget]);

  useEffect(() => {
    if (tab === "sources" && !sourceId && sources.length) setSourceId(sources[0].source_id);
  }, [tab, sourceId, sources]);

  useEffect(() => {
    if (!importOpen) return;
    const panel = document.querySelector<HTMLDetailsElement>(".kwImport");
    const trigger = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel?.querySelector<HTMLButtonElement>(".kwImportClose")?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !actionRunning.current) setImportOpen(false);
      if (event.key !== "Tab") return;
      const controls = [...(panel?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary") ?? [])].filter(el => el.getClientRects().length);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", keyboard);
    return () => { document.removeEventListener("keydown", keyboard); document.body.style.overflow = previousOverflow; trigger?.focus(); };
  }, [importOpen]);

  useEffect(() => {
    if (!sessionActive) { setSources([]); setSource(null); setEvidence([]); setDrafts([]); setSegments([]); setJob(null); return; }
    let current = true;
    void refreshOverview().catch(cause => { if (current) setError(apiErrorText(cause)); });
    void requestJson<PublicationConfig>(`${base}/publication-config`).then(value => { if (current) setConfiguration(value); }).catch(() => { if (current) setConfiguration(null); });
    return () => { current = false; };
  }, [sessionActive, refreshOverview]);

  useEffect(() => {
    if (!sessionActive) return;
    if (!sourceId) {
      ++sourceGeneration.current; setSource(null); setRevision(0); setCandidates(null); setReviewTarget(null);
      setSegments([]); setSelectedSegments([]); setSelectedEvidence(""); setEvidence([]); setDrafts([]);
      void refreshReview("").catch(cause => setError(apiErrorText(cause)));
      return;
    }
    let current = true;
    const generation = ++sourceGeneration.current;
    setSegments([]); setSelectedSegments([]); setFocusedSegment(""); setSelectedEvidence(""); setReviewTarget(null); setSource(null); setRevision(0); setCandidates(null); setEvidence([]); setDrafts([]); setError(""); setNotice(""); setDraftName(""); setTerms("");
    void requestJson<SourceDetail>(`${base}/sources/${enc(sourceId)}`).then(detail => {
      if (!current || sourceGeneration.current !== generation) return;
      const saved = restored.current;
      const requested = initialCitation?.source_id === sourceId ? initialCitation.source_revision_no : saved.sourceId === sourceId ? saved.revision : undefined;
      const revisionNo = requested && detail.revisions.some(row => row.revision_no === requested) ? requested : initialCitation?.source_id === sourceId ? 0 : detail.revisions.at(-1)?.revision_no ?? 0;
      if (!revisionNo && initialCitation) setCitationError("引用的来源修订不存在，请返回证据核对。");
      setSource(detail); setRevision(revisionNo); setAfter(-1);
    }).catch(cause => { if (current) setError(apiErrorText(cause)); });
    return () => { current = false; };
  }, [sourceId, sessionActive, refreshReview, initialCitation]);

  useEffect(() => {
    ++reviewGeneration.current;
    loadedSegmentScope.current = "";
    setSegments([]); setSelectedSegments([]); setFocusedSegment(""); setAfter(-1);
    setCandidates(null); setReviewTarget(null); setSelectedEvidence(""); setEvidence([]); setDrafts([]); setDraftName(""); setTerms("");
  }, [sourceId, revision, structureView, reload, sessionActive]);

  useEffect(() => {
    if (!sessionActive || !sourceId || !revision || source?.source_id !== sourceId) return;
    if (activeCitation && (!citationDetail || citationError)) return;
    if (source.revisions.find(row => row.revision_no === revision)?.status !== "SEGMENTED") return;
    const scope = `${sourceId}@${revision}/${structureView}/${reload}`;
    if (loadedSegmentScope.current === scope) return;
    let current = true;
    ++reviewGeneration.current;
    const controller = new AbortController();
    void (async () => {
      const targetIds = activeCitation ? citationDetail!.segment_ids : [];
      const saved = restored.current;
      const restoring = !activeCitation && saved.sourceId === sourceId && saved.revision === revision && saved.structureView === structureView;
      const limit = activeCitation || restoring && (saved.through ?? 0) > 50 ? 500 : 50;
      const view = activeCitation || structureView ? "all" : "reading";
      const collected: Segment[] = [];
      let cursor = -1, more = true;
      while (more && current) {
        const rows = await requestJson<Segment[]>(`${base}/sources/${enc(sourceId)}/revisions/${revision}/segments?limit=${limit}&after=${cursor}&view=${view}`, { signal: controller.signal });
        if (!current) return;
        collected.push(...rows); more = rows.length === limit;
        cursor = rows.at(-1)?.sequence_no ?? cursor;
        if (targetIds.length ? targetIds.every(id => collected.some(row => row.segment_id === id)) : !restoring || cursor >= (saved.through ?? -1)) break;
      }
      if (!current) return;
      if (targetIds.some(id => !collected.some(row => row.segment_id === id))) throw new Error("未在此来源修订中找到完整引用范围，请重试或返回证据核对。");
      if (targetIds.length && targetIds.map(id => collected.find(row => row.segment_id === id)!.original_text).join("\n") !== citationDetail!.quote_text) throw new Error("引用文本与此修订不一致，请返回证据核对。");
      const rows = view === "all" && !structureView ? collected.filter(row => row.segment_type !== "SENTENCE" || targetIds.includes(row.segment_id)) : collected;
      loadedSegmentScope.current = scope; setSegments(rows); setHasMore(more); setAfter(cursor);
      setFocusedSegment(targetIds[0] ?? (restoring && rows.some(row => row.segment_id === saved.focusedSegment) ? saved.focusedSegment! : rows.find(row => ["PARAGRAPH", "CLAUSE", "SENTENCE", "COMMENTARY", "NOTE", "CASE_NOTE", "FORMULA_TEXT"].includes(row.segment_type))?.segment_id ?? rows[0]?.segment_id ?? ""));
      if (!activeCitation) restored.current = {};
    })().catch(cause => { if (current) activeCitation ? setCitationError(apiErrorText(cause)) : setError(apiErrorText(cause)); });
    void refreshReview(sourceId, revision).catch(cause => { if (current) setError(apiErrorText(cause)); });
    void readCandidates(sourceId, revision).then(value => { if (current) setCandidates(value); }).catch(cause => { if (current) setError(apiErrorText(cause)); });
    return () => { current = false; controller.abort(); };
  }, [sourceId, revision, source?.source_id, source?.revisions.find(row => row.revision_no === revision)?.status, reload, structureView, sessionActive, refreshReview, activeCitation, citationDetail, citationError]);

  useEffect(() => {
    if (tab === "sources" && focusedSegment) document.querySelector(".kwSegmentRow.selected")?.scrollIntoView({ block: "nearest" });
  }, [focusedSegment, tab]);

  // Import progress belongs to the source revision, so it also resumes after a reload.
  useEffect(() => {
    const status = source?.revisions.find(row => row.revision_no === revision)?.status;
    if (!sessionActive || !sourceId || !["REGISTERED", "PENDING", "PARSING", "PARSED", "SEGMENTING"].includes(status ?? "")) return;
    let current = true;
    const timer = window.setInterval(() => {
      void requestJson<SourceDetail>(`${base}/sources/${enc(sourceId)}`).then(detail => {
        if (current) { setSource(detail); void refreshOverview().catch(cause => { if (current) setError(apiErrorText(cause)); }); }
      }).catch(cause => { if (current) setError(apiErrorText(cause)); });
    }, 2000);
    return () => { current = false; window.clearInterval(timer); };
  }, [sourceId, revision, source?.revisions.find(row => row.revision_no === revision)?.status, sessionActive, refreshOverview]);

  useEffect(() => {
    if (!sessionActive || !versionId) return;
    let current = true;
    void requestJson<VersionDetail>(`${base}/versions/${enc(versionId)}`).then(value => { if (current) { setVersion(value); if (value.publication_job) setJob({ ...value.publication_job, purpose: "publish" }); } }).catch(cause => { if (current) setError(apiErrorText(cause)); });
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
          if (job.purpose === "import" && job.source_id && job.source_id === sourceId) {
            await refreshSource(job.source_id);
          }
          if (job.purpose === "publish" && versionId) await refreshVersion(versionId);
        }
      }).catch(cause => { if (current) setError(apiErrorText(cause)); });
    }, 2000);
    return () => { current = false; window.clearInterval(timer); };
  }, [sessionActive, job, sourceId, versionId, refreshOverview, refreshSource, refreshVersion]);

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
      await refreshOverview(); setSourceId(result.source_id); setRevision(result.revision_no); setTab("sources");
      setImportOpen(false);
      if (result.job_id) setJob({ job_id: result.job_id, status: result.status, purpose: "import", source_id: result.source_id });
      else { await refreshSource(result.source_id); setNotice(`来源登记完成：${displayStatus(result.status)}。`); }
    }, "import");
  }

  async function createEvidence() {
    await action(async () => {
      const result = await postJson<Evidence>(`${base}/drafts/evidence`, { segment_ids: segments.filter(row => selectedSegments.includes(row.segment_id)).map(row => `${row.segment_id}@${revision}`), strength }, csrf);
      await refreshReview(sourceId, revision); setSelectedEvidence(evidenceRef(result)); setTab("review"); setReviewTarget({ kind: "evidence_revision", ref: evidenceRef(result), label: "原文证据" }); setReviewNote(""); setNotice("精确证据草稿已创建，请核对原文、上下文与引用位置后审核。");
    }, "evidence");
  }

  async function createDraft(event: FormEvent) {
    event.preventDefault(); const item = evidence.find(row => evidenceRef(row) === selectedEvidence);
    if (!item || item.status !== "REVIEWED" || !draftName.trim()) return;
    await action(async () => {
      await postJson(`${base}/drafts/${draftKind === "concept" ? "concepts" : "herbs"}`, { canonical_name: draftName.trim(), evidence_id: item.evidence_id, evidence_revision_no: item.revision_no, terms: [...new Set(terms.split(/[、,，\n]/).map(value => value.trim()).filter(Boolean))], ...(draftKind === "concept" ? { concept_type: conceptType } : {}), era: source?.era ?? null }, csrf);
      await refreshReview(sourceId, revision); setDraftName(""); setTerms(""); setNotice("知识草稿已创建，需人工审核后才能进入版本快照。");
    }, "draft");
  }

  async function review(decision: "APPROVE" | "REJECT") {
    if (!reviewTarget || (decision === "REJECT" && !reviewNote.trim())) return;
    await action(async () => {
      await postJson(`${base}/reviews/${reviewTarget.kind}/${enc(reviewTarget.ref)}`, { decision, note: reviewNote.trim() || "操作者确认已核对原文与引用边界，审核通过。" }, csrf);
      await Promise.all([refreshReview(sourceId, revision), refreshOverview()]); setReviewTarget(null); setReviewNote(""); setNotice(decision === "APPROVE" ? "人工审核记录已保存。继续核对剩余草稿，完成后前往发布。" : "已拒绝并保存说明。");
    }, "review");
  }

  const reviewKey = (kind: string, ref: string) => `${kind}:${ref}`;
  function toggleBatch(key: string, checked: boolean) {
    setBatchSelection(values => checked ? [...new Set([...values, key])] : values.filter(value => value !== key));
  }
  async function reviewBatch(decision: "APPROVE" | "REJECT") {
    if (!batchSelection.length || (decision === "REJECT" && !batchNote.trim())) return;
    const targets = [
      ...evidence.filter(row => row.status === "DRAFT").map(row => ({ kind: "evidence_revision", ref: evidenceRef(row), ready: true })),
      ...drafts.filter(row => row.status === "DRAFT").map(row => ({ kind: row.kind, ref: row.ref, ready: evidenceReady(row) })),
    ].filter(row => batchSelection.includes(reviewKey(row.kind, row.ref)));
    if (decision === "APPROVE" && targets.some(row => !row.ready)) return;
    await action(async () => {
      const completed = new Set<string>();
      let failed = "";
      for (const [index, target] of targets.entries()) {
        setOperation(previous => previous ? { ...previous, label: `正在保存批量审核 ${index + 1} / ${targets.length}` } : null);
        try {
          await postJson(`${base}/reviews/${target.kind}/${enc(target.ref)}`, { decision, note: batchNote.trim() || "操作者逐项核对所选原文与引用边界，批量审核通过。" }, csrf);
          completed.add(reviewKey(target.kind, target.ref));
        } catch (cause) { failed = apiErrorText(cause); break; }
      }
      setBatchSelection(values => values.filter(key => !completed.has(key)));
      await Promise.all([refreshReview(sourceId, revision), refreshOverview()]);
      setNotice(`已保存 ${completed.size} / ${targets.length} 条审核记录。${failed ? "未保存的选择已保留，可核对后重试。" : "每条对象均保留操作者及审核说明。"}`);
      if (failed) throw new Error(failed);
      setBatchNote("");
    }, "review");
  }

  async function approveSource() {
    if (!sourceId || !revision) return;
    await action(async () => {
      const result = await postJson<{ total: number; completed: { ref: string }[]; failed: { ref: string; reason: string }[] }>(`${base}/reviews/batch`, {
        source_id: sourceId, source_revision_no: revision, decision: "APPROVE",
        kinds: ["evidence_revision", "formula_revision", "concept", "herb", "relation"],
      }, csrf);
      await Promise.all([refreshReview(sourceId, revision), refreshOverview()]);
      setBatchSelection([]);
      setNotice(`整份修订审核：通过 ${result.completed.length} / ${result.total} 条，待修复 ${result.failed.length} 条。`);
      if (result.failed.length) setError(result.failed.map(row => `${row.ref}：${row.reason}`).join("；"));
    }, "review");
  }

  async function publish(prepare = false) {
    await action(async () => {
      const configured = await requestJson<PublicationConfig>(`${base}/publication-config`);
      setConfiguration(configured);
      if (configured.available === false || !configured.configuration) throw new Error(configured.detail || "发布配置尚未就绪，请由管理员配置后重试。");
      const target = prepare ? await postJson<VersionDetail>(`${base}/versions/prepare`, configured.configuration, csrf) : version;
      if (!target) throw new Error("请先选择知识版本。");
      setVersionId(target.version_id); setVersion(target);
      await refreshOverview();
      if (target.index_builds.some(row => row.status === "READY")) { setNotice(target.active ? "这些已审核对象已在当前版本中生效。" : "索引已就绪，请确认启用此检索版本。"); return; }
      const result = await postJson<Job>(`${base}/versions/${enc(target.version_id)}/publish`, { ...configured.configuration, activate_on_success: false }, csrf);
      setJob({ ...result, purpose: "publish" }); await refreshVersion(target.version_id); setNotice("正在加入知识库：索引构建完成后，请确认启用检索版本。旧版本继续可用。");
    }, "publish");
  }

  const focused = segments.find(row => row.segment_id === focusedSegment);
  const chosenEvidence = evidence.find(row => evidenceRef(row) === selectedEvidence);
  const currentRevision = source?.revisions.find(row => row.revision_no === revision);
  const selectable = (row: Segment) => ["CLAUSE", "PARAGRAPH", "SENTENCE", "COMMENTARY", "NOTE", "CASE_NOTE", "FORMULA_TEXT"].includes(row.segment_type);
  const reviewedEvidence = evidence.filter(row => row.status === "REVIEWED");
  const readyBuild = version?.index_builds.find(row => row.status === "READY");
  const batchEvidence = new Set(candidates?.evidence.map(evidenceRef) ?? []);
  const batchDrafts = new Set([...(candidates?.concepts.map(row => row.concept_id) ?? []), ...(candidates?.relations.map(row => row.relation_id) ?? []), ...(candidates?.formulas.map(row => `${row.formula_id}@${row.revision_no}`) ?? [])]);
  const pendingEvidence = evidence.filter(row => row.status === "DRAFT");
  const pendingDrafts = drafts.filter(row => row.status === "DRAFT");
  const evidenceReady = (row: Draft) => row.evidence.length > 0 && row.evidence.every(item => item.status === "REVIEWED");
  const nextDraft = pendingDrafts.find(evidenceReady);
  const reviewDone = !pendingEvidence.length && !pendingDrafts.length && drafts.some(row => row.status === "REVIEWED");
  const canApproveTarget = reviewTarget?.kind === "evidence_revision" || drafts.some(row => row.ref === reviewTarget?.ref && evidenceReady(row));
  const importReason = busy ? "正在处理，请等待完成后继续。" : !file ? "请选择 TXT、PDF 或 DOCX 来源文件。" : !title.trim() ? "请填写书名 / 文献标题。" : !["txt", "pdf", "docx"].includes(file.name.split(".").at(-1)?.toLowerCase() ?? "") ? "文件格式不支持，请选择 TXT、PDF 或 DOCX 文件。" : outboundAuthorized && dataLevel === "PUBLIC" && !outboundReason.trim() ? "请填写外发授权理由，或取消云端使用授权。" : "";
  const parseReason = !sourceId ? "请先选择或导入一份来源。" : !currentRevision ? "正在读取来源状态，请稍候。" : currentRevision.status === "OCR_REQUIRED" ? "此文件需要 OCR，请导入完成文字识别的 TXT、DOCX 或文本 PDF 作为新修订。" : currentRevision.status === "FAILED" ? "解析失败，请查看错误后重新导入文件作为新修订。" : currentRevision.status !== "SEGMENTED" ? "来源正在解析，完成后即可选择原文建立证据。" : "";
  const selectedRows = segments.filter(row => selectedSegments.includes(row.segment_id));
  const rangeInvalid = invalidEvidenceRange(segments, selectedRows);
  const evidenceReason = busy ? "正在处理，请等待完成后继续。" : parseReason || (!selectedRows.length ? "请在左侧勾选要引用的原文段落。" : selectedRows.length > 100 ? "一次最多引用 100 个段落，请缩小范围。" : rangeInvalid ? "请选择同一层级的连续原文段落，避免重复或跨段引用。" : "");
  const batchBlocked = drafts.some(row => batchSelection.includes(reviewKey(row.kind, row.ref)) && !evidenceReady(row));
  const draftReason = busy ? "正在处理，请等待完成后继续。" : !evidence.length ? "当前范围没有原文证据，请返回原文建立证据。" : !reviewedEvidence.length ? pendingEvidence.length ? "请先核对并审核原文证据，通过后才能建立知识草稿。" : "当前证据已被拒绝，请返回原文重新选择并建立证据。" : chosenEvidence?.status !== "REVIEWED" ? "请选择一条已核对通过的原文证据。" : !draftName.trim() ? "请填写规范名称。" : "";
  function beginEvidenceReview(row: Evidence) {
    setSelectedEvidence(evidenceRef(row)); setReviewTarget({ kind: "evidence_revision", ref: evidenceRef(row), label: "原文证据" }); setReviewNote("");
  }
  function openReplacementImport() {
    setNewRevision(true); setTitle(source?.title ?? "");
    if (source) {
      setSourceType(source.source_type); setAuthor(source.author ?? "");
      setEra(source.era ?? ""); setEdition(source.edition ?? "");
      setCopyright(source.copyright_status); setDataLevel(source.data_level);
      setOutboundAuthorized(source.outbound_authorized); setOutboundReason(source.outbound_reason ?? "");
    }
    setFile(null);
    const input = document.querySelector<HTMLInputElement>(".kwImport input[type=file]");
    if (input) input.value = "";
    setImportOpen(true);
  }

  return <section className="kwWorkspace panel" aria-labelledby="kw-title">
    <header className="kwHeader"><div><h2 id="kw-title">文献资料<span className="kwCount">{sources.length}</span></h2><p>原文阅读、证据核对与知识整理</p></div><div className="kwToolbarActions"><button className="kwPrimary" type="button" disabled={!sessionActive || busy} onClick={() => { setNewRevision(false); setTab("sources"); setImportOpen(true); }}>＋ 导入文献</button><button type="button" disabled={!sessionActive || busy} onClick={() => void action(async () => { await refreshOverview(); if (sourceId) { await refreshSource(sourceId); await refreshReview(sourceId, revision); if (revision) setCandidates(await readCandidates(sourceId, revision)); setReload(value => value + 1); } else await refreshReview(""); if (versionId) await refreshVersion(versionId); })}>刷新状态</button></div></header>
    {!sessionActive ? <p className="kwEmpty">请在页头连接本机工作区，随后可导入来源、审核证据与发布版本。</p> : <>
      <nav className="kwTabs" aria-label="知识工作区"><button className={tab === "sources" ? "active" : ""} onClick={() => setTab("sources")}>1 · 来源与原文</button><button className={tab === "review" ? "active" : ""} onClick={() => setTab("review")}>2 · 证据与人工审核</button><button className={tab === "publish" ? "active" : ""} onClick={() => setTab("publish")}>3 · 质量与版本发布</button></nav>
      {initialCitation && <aside className="kwCitationNavigation" aria-label="引用定位"><div><strong>正在核对引用 · 来源修订 {initialCitation.source_revision_no}</strong><p>{citationError || (citedRows.length ? `已定位并高亮 ${citedRows.length} 个引用段落，原始阅读位置已保留。` : "正在读取精确引用范围…")}</p></div>{citationError && <button onClick={() => setReload(value => value + 1)}>重试定位引用</button>}{onReturnCitation && <button onClick={onReturnCitation}>返回引用处</button>}</aside>}
      {error && <p className="kwError" role="alert">{error}</p>}{notice && <p className="kwNotice" role="status">{notice}</p>}
      {operation && <aside className="kwJob kwOperation" role="status" aria-live="polite"><strong>{operation.label}</strong><span>已耗时 {elapsed} 秒</span><small>{errorStep === "extract" ? "整本文献可能需要较长时间；服务仍在处理，完成后进入审核。" : "请等待当前操作完成。"}</small></aside>}
      {job && <aside className={`kwJob ${job.status === "FAILED" ? "failed" : ""}`} role="status"><strong>{job.purpose === "import" ? "来源解析" : "版本发布"}：{displayStatus(job.status)}</strong>{job.attempts != null && <span>尝试 {job.attempts} / {job.max_attempts}</span>}{job.error_code && <span>{job.error_code}</span>}<small>任务 {job.job_id}</small></aside>}
      <aside className="kwNextStep" aria-label="当前流程下一步">
        {tab === "sources" && (!source ? <p>第一步：导入来源文件，或选择已有来源继续。</p> : currentRevision?.status !== "SEGMENTED" ? <div><p>{parseReason}</p>{["FAILED", "OCR_REQUIRED"].includes(currentRevision?.status ?? "") && <button disabled={busy} onClick={openReplacementImport}>重新导入此来源</button>}</div> : <><div><strong>{candidates ? "已提取候选，可以继续核对" : "选取原文，建立有据可查的知识"}</strong><p>{candidates ? "提取记录已恢复。先审原文证据，再审概念、关系和方剂。" : "在目录中勾选原文段落，再建立证据；也可以自动提取知识候选。"}</p></div><button disabled={busy} onClick={() => candidates ? setTab("review") : void extract()}>{candidates ? "继续审核本批" : "提取并进入审核"}</button></>)}
        {tab === "review" && <><div><strong>{!evidence.length ? "下一步：返回原文建立证据" : reviewDone ? "下一步：将已审核知识发布为版本" : pendingEvidence.length ? "先审核原文证据，再审核知识草稿" : reviewedEvidence.length && !pendingDrafts.length ? "下一步：填写名称，建立知识草稿" : "下一步：审核知识草稿"}</strong><p>{source ? `${source.title} · 来源修订 ${revision} · ` : "全部来源 · "}待审证据 {pendingEvidence.length} · 待审知识 {pendingDrafts.length}{candidates && " · 本批候选已标出"}。拒绝对象不会进入快照。</p></div>{pendingEvidence.length > 0 ? <button disabled={busy} onClick={() => { const row = pendingEvidence[0]; setSelectedEvidence(evidenceRef(row)); setReviewTarget({ kind: "evidence_revision", ref: evidenceRef(row), label: "原文证据" }); setReviewNote(""); }}>先审核原文证据</button> : nextDraft ? <button disabled={busy} onClick={() => { setReviewTarget({ kind: nextDraft.kind, ref: nextDraft.ref, label: draftTitle(nextDraft) }); setReviewNote(""); }}>审核知识草稿</button> : reviewDone ? <button disabled={busy} onClick={() => setTab("publish")}>前往发布</button> : reviewedEvidence.length ? <button disabled={busy} onClick={() => document.querySelector(".kwDraftForm")?.scrollIntoView({ behavior: "smooth", block: "center" })}>填写知识草稿</button> : <button disabled={busy} onClick={() => setTab("sources")}>返回原文建立证据</button>}</>}
        {tab === "publish" && <div><strong>{version?.active ? "版本已激活，下一步：知识检索" : readyBuild ? "发布完成，下一步：激活为当前检索版本" : version && ["INDEXING", "VALIDATING"].includes(version.status) ? "发布任务执行中，完成后激活检索版本" : version ? "下一步：发布快照并构建索引" : "下一步：创建已审核知识快照"}</strong><p>{quality?.publication_blocked ? "先处理下方质量阻断，再继续发布。" : "使用“加入知识库并构建索引”连续完成准备；构建通过后确认启用。"}</p></div>}
      </aside>
      {tab === "sources" && <>
        {importOpen && <div className="kwImportBackdrop" onClick={() => { if (!busy) setImportOpen(false); }} aria-hidden="true" />}<details className="kwImport" open={importOpen} onToggle={event => setImportOpen(event.currentTarget.open)} role={importOpen ? "dialog" : undefined} aria-modal={importOpen || undefined} aria-label="导入文献"><summary>导入新的来源文件</summary><button className="kwImportClose" type="button" aria-label="关闭导入面板" disabled={busy} onClick={() => setImportOpen(false)}>×</button><form onSubmit={event => void importSource(event)} className="kwForm"><label>来源文件（必填）<input type="file" accept=".txt,.pdf,.docx" onChange={event => { const next = event.target.files?.[0] ?? null; setFile(next); if (next && !title) setTitle(next.name.replace(/\.[^.]+$/, "")); }} required /></label><label>书名 / 文献标题（必填）<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={500} /></label><label>来源类型<select value={sourceType} onChange={event => setSourceType(event.target.value)}>{sourceTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>作者（选填）<input value={author} onChange={event => setAuthor(event.target.value)} maxLength={300} /></label><label>时代（选填）<input value={era} onChange={event => setEra(event.target.value)} maxLength={120} /></label><label>版本 / 版次（选填）<input value={edition} onChange={event => setEdition(event.target.value)} maxLength={300} /></label><label>版权状态<select value={copyright} onChange={event => setCopyright(event.target.value)}><option value="UNKNOWN">待核实</option><option value="PUBLIC_DOMAIN">公版</option><option value="AUTHORIZED">已授权</option><option value="COPYRIGHTED">受版权保护</option></select></label><label>资料分级<select value={dataLevel} onChange={event => { setDataLevel(event.target.value); if (event.target.value !== "PUBLIC") { setOutboundAuthorized(false); setOutboundReason(""); } }}><option value="RESTRICTED">受限资料</option><option value="PUBLIC">公开资料</option><option value="SENSITIVE">敏感资料</option></select></label><label className="kwInline"><input type="checkbox" checked={outboundAuthorized} disabled={dataLevel !== "PUBLIC"} onChange={event => setOutboundAuthorized(event.target.checked)} />允许此公开来源的原文用于云端研究生成</label>{outboundAuthorized && dataLevel === "PUBLIC" && <label>外发授权理由（必填）<input value={outboundReason} onChange={event => setOutboundReason(event.target.value)} required maxLength={500} placeholder="例如：公版资料，授权本次研究引用与模型分析" /></label>}<label className="kwInline"><input type="checkbox" checked={newRevision} disabled={!sourceId} onChange={event => setNewRevision(event.target.checked)} />作为所选来源的新修订{source && `（${source.title}）`}</label><p className="kwHint">文件保存在本地；公开来源可单独授权云端研究使用原文。受限和敏感资料保持本地。扫描 PDF 需要 OCR 时会显示阻断状态。</p><button type="submit" className="kwPrimary" aria-describedby="kw-import-reason" disabled={!!importReason}>{busy ? "处理中…" : "导入并解析"}</button><DisabledReason id="kw-import-reason" reason={importReason} />{error && errorStep === "import" && <p className="kwError" role="alert">导入未完成：{error}。请检查上述字段和文件后重新提交。</p>}</form></details>
        <div className="kwSourceGrid"><aside className="kwSourceList"><div className="kwColumnHead"><h3>文献目录</h3><span>{sources.length} 份</span></div><input className="kwSourceSearch" type="search" aria-label="搜索文献" placeholder="搜索文献标题" value={sourceSearch} onChange={event => setSourceSearch(event.target.value)} />{!sources.length && <p className="kwEmpty">导入第一份真实来源开始建立知识库。</p>}{sources.filter(row => row.title.toLowerCase().includes(sourceSearch.trim().toLowerCase())).map(row => <button key={row.source_id} className={sourceId === row.source_id ? "selected" : ""} disabled={busy} onClick={() => { setSourceId(row.source_id); setNewRevision(false); }}><strong>{row.title}</strong><small>{sourceTypes.find(([value]) => value === row.source_type)?.[1] || "文献"} · {row.data_level === "PUBLIC" ? "公开" : row.data_level === "SENSITIVE" ? "敏感" : "受限"}</small></button>)}</aside><div className="kwSourceContent">{!source ? <div className="kwBlank"><span className="kwBlankIcon" aria-hidden="true">▤</span><h3>{sources.length ? "选择一份文献开始阅读" : "从第一份文献开始"}</h3><p>导入 TXT、PDF 或 DOCX，保留原文与每一条知识的出处。</p><button className="kwPrimary" onClick={() => setImportOpen(true)}>导入文献</button></div> : <>
          <header className="kwSourceTitle"><div><h3>{source.title}</h3><p>{[source.author, source.era, source.edition].filter(Boolean).join(" · ") || "尚未填写作者与版次"}</p></div><div className="kwSourceTools"><label>来源修订<select value={revision} disabled={busy} onChange={event => setRevision(Number(event.target.value))}>{source.revisions.map(row => <option key={row.revision_no} value={row.revision_no}>修订 {row.revision_no} · {row.file_format.toUpperCase()} · {displayStatus(row.status)}</option>)}</select></label><button disabled={busy} onClick={() => { setTab("sources"); openReplacementImport(); }}>导入新修订</button><button onClick={() => setTab("review")}>前往审核</button></div></header>
          {currentRevision?.error_code && <p className="kwError" role="alert">解析未完成：{currentRevision.error_code}。此修订暂不能创建精确证据。</p>}
          <div className="kwSegmentGrid"><div className="kwSegments"><h4>{structureView ? "结构与子句" : "章节与完整段落"}</h4><label className="kwViewToggle"><input type="checkbox" checked={structureView} disabled={busy} onChange={event => setStructureView(event.target.checked)} />显示结构与子句</label>{segments.map(row => <div key={row.segment_id} className={`kwSegmentRow ${row.segment_id === focusedSegment ? "selected" : ""} ${citedIds.includes(row.segment_id) ? "cited" : ""} ${row.parent_segment_id ? "child" : ""}`}><input aria-label={`选中段落 ${row.sequence_no + 1}`} type="checkbox" disabled={!selectable(row) || busy} checked={selectedSegments.includes(row.segment_id)} onChange={event => setSelectedSegments(values => event.target.checked ? [...values, row.segment_id] : values.filter(id => id !== row.segment_id))} /><button onClick={() => setFocusedSegment(row.segment_id)}><small>{currentRevision?.file_format === "pdf" && row.page_no != null ? `第 ${row.page_no} 页 · ` : ""}{row.chapter_no != null ? `第 ${row.chapter_no} 章 · ` : ""}{row.paragraph_no != null ? `第 ${row.paragraph_no} 段` : `段落 ${row.sequence_no + 1}`}</small><span>{row.original_text.slice(0, 90)}</span></button></div>)}{!segments.length && <p className="kwEmpty">尚无可用段落，等待来源解析完成后刷新。</p>}{hasMore && <button disabled={busy} onClick={() => void action(async () => { const cursor = segments.at(-1)?.sequence_no ?? after; const rows = await requestJson<Segment[]>(`${base}/sources/${enc(sourceId)}/revisions/${revision}/segments?limit=50&after=${cursor}&view=${structureView ? "all" : "reading"}`); setSegments(values => [...values, ...rows]); setAfter(cursor); setHasMore(rows.length === 50); })}>加载后续段落</button>}</div><article className="kwOriginal">{activeCitation ? <CitationReading detail={citationDetail} rows={citedRows} error={citationError} physicalPages={currentRevision?.file_format === "pdf"} /> : focused ? <><div className="kwReadingHead"><h4>原文阅读</h4><span>{currentRevision?.file_format === "pdf" && focused.page_no != null ? "第 " + focused.page_no + " 页" : "逻辑段 " + (focused.paragraph_no ?? focused.sequence_no + 1)}</span></div><blockquote>{readingText(focused.original_text)}</blockquote><details className="kwNormalized"><summary>查看规范文本</summary><p>{focused.normalized_text || "未生成规范文本"}</p></details><details><summary>查看上下文</summary><h5>上文</h5><p>{readingText(focused.context_before) || "无上文"}</p><h5>下文</h5><p>{readingText(focused.context_after) || "无下文"}</p></details><details className="kwCitation"><summary>引用位置与结构详情</summary><Locator value={focused.locator} /><h5>保留物理换行的原始文本</h5><pre className="kwPhysicalText">{focused.original_text}</pre></details></> : <p className="kwEmpty">选择段落查看原文、规范文本与上下文。</p>}</article></div>
          <div className="kwEvidenceBar" aria-busy={busy}><span>已选 {selectedSegments.length} 个原文段落</span><label>证据强度<select value={strength} onChange={event => setStrength(event.target.value)}>{[["DIRECT", "直接证据"], ["INDIRECT", "间接证据"], ["INTERPRETIVE", "解释性证据"], ["EMPIRICAL", "经验性证据"], ["BACKGROUND", "背景证据"], ["UNVERIFIED", "待核实"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button className="kwPrimary" aria-describedby="kw-evidence-reason" disabled={!!evidenceReason} onClick={() => void createEvidence()}>创建精确证据草稿</button><small>仅引用所选连续段落；上下文保留为上下文。公开状态、解析完成和人工核对分别记录。</small><DisabledReason id="kw-evidence-reason" reason={evidenceReason} />{error && errorStep === "evidence" && <p className="kwError" role="alert">证据创建未完成：{error}。请调整原文选择后重试。</p>}</div>
          <details className="kwExtraction"><summary>自动提取与候选记录</summary><div className="kwActions"><button disabled={busy || currentRevision?.status !== "SEGMENTED"} onClick={() => void extract()}>从此修订提取知识候选</button><button disabled={busy || currentRevision?.status !== "SEGMENTED" || !candidates} onClick={() => void action(async () => { setCandidates(await requestJson<Candidates>(`${base}/sources/${enc(sourceId)}/revisions/${revision}/candidates`)); await refreshReview(sourceId, revision); })}>查看已有候选</button><button onClick={() => setTab("review")}>前往审核</button></div><DisabledReason id="kw-extract-reason" reason={busy ? "正在处理，请等待完成。" : parseReason || (!candidates ? "尚未提取候选；可提取知识候选，或直接勾选原文建立证据。" : "")} /><p className="kwHint">按原文规则生成候选，保留提及位置；可能存在歧义，不会自动审核。</p>{candidates && <div className="kwCandidateSummary"><p>原文段落 {candidates.segment_count} · 提及 {candidates.mention_count} · 概念 {candidates.concept_count} · 关系 {candidates.relation_count} · 方剂 {candidates.formula_count}</p><details><summary>查看原文提及位置与歧义</summary>{candidates.segments.filter(row => row.mentions.length > 0).map(row => <article key={row.segment_ref}><small>{row.segment_ref}</small>{row.mentions.map((mention, index) => <p key={index}><strong>{mention.surface_text}</strong> · 字符 {mention.start_offset}–{mention.end_offset}{mention.ambiguous && <span className="kwBadge">需消歧</span>}</p>)}</article>)}<small>提取器 {candidates.extractor_version}</small></details></div>}</details>
        </>}</div></div>
      </>}
      {tab === "review" && <>
        <div className="kwReviewHead"><label>审核范围<select value={sourceId} disabled={busy} onChange={event => setSourceId(event.target.value)}><option value="">全部来源</option>{sources.map(row => <option key={row.source_id} value={row.source_id}>{row.title}</option>)}</select></label><span>审核通过后才会纳入知识版本。通过时可补充说明；拒绝时必须填写原因。</span></div>
        <section className="kwBatchReview" aria-label="批量人工审核"><div className="kwActions"><button className="kwPrimary" disabled={busy || !sourceId || !revision} onClick={() => void approveSource()}>通过此修订全部待审对象</button><span>包含分页外的条目；先检查证据，再检查方剂字段。通过无需填写原因，失败项保留。</span></div><div><strong>已选 {batchSelection.length} 条待审对象</strong><p>逐项查看原文后勾选；先审核证据，再审核关联知识。</p></div><details><summary>补充说明 / 拒绝原因</summary><label>本批说明（通过选填，拒绝必填）<textarea value={batchNote} disabled={busy} onChange={event => setBatchNote(event.target.value)} maxLength={4000} /></label></details><div className="kwActions"><button className="kwPrimary" disabled={busy || !batchSelection.length || batchBlocked} onClick={() => void reviewBatch("APPROVE")}>确认所选已核对并通过</button><button disabled={busy || !batchSelection.length || !batchNote.trim()} onClick={() => void reviewBatch("REJECT")}>拒绝所选并记录原因</button><button disabled={busy || !batchSelection.length} onClick={() => setBatchSelection([])}>清空选择</button></div>{batchBlocked && <p className="kwHint">所选知识的关联证据尚未全部通过，请先审核原文证据。</p>}</section><div className="kwReviewGrid"><div><h3>原文证据</h3>{!evidence.length && <p className="kwEmpty">先在来源中选取段落创建证据草稿。</p>}{evidence.map(row => <article className={`kwCard ${selectedEvidence === evidenceRef(row) ? "selected" : ""} ${batchEvidence.has(evidenceRef(row)) ? "batch" : ""}`} key={evidenceRef(row)}><div className="kwCardHead"><strong>{row.source_title} · 修订 {row.source_revision_no}{batchEvidence.has(evidenceRef(row)) && <small className="kwBatchLabel">本批候选</small>}</strong><span className="kwBadge">{displayStatus(row.status)}</span></div><blockquote>{readingText(row.quote_text)}</blockquote>{row.status === "DRAFT" && <label className="kwInline"><input type="checkbox" disabled={busy} checked={batchSelection.includes(reviewKey("evidence_revision", evidenceRef(row)))} onChange={event => toggleBatch(reviewKey("evidence_revision", evidenceRef(row)), event.target.checked)} />已查看此证据，加入批量审核</label>}<details><summary>原文上下文与引用位置</summary><h5>上文</h5><p>{row.context_before || "无上文"}</p><h5>下文</h5><p>{row.context_after || "无下文"}</p><Locator value={row.citation_locator} /></details><div className="kwActions"><button disabled={busy} onClick={() => { setSelectedEvidence(evidenceRef(row)); setReviewTarget(row.status === "DRAFT" ? { kind: "evidence_revision", ref: evidenceRef(row), label: "原文证据" } : null); setReviewNote(""); }}>{row.status === "DRAFT" ? "核对并审核" : "选择此证据"}</button>{onEvidence && <button onClick={() => onEvidence({ evidence_id: row.evidence_id, revision_no: row.revision_no })}>查看完整证据</button>}</div></article>)}</div><div>{reviewTarget && <section className="kwReviewAction" aria-label="人工审核"><h3>人工审核：{reviewTarget.label}</h3><label>审核说明（通过选填，拒绝必填）<textarea value={reviewNote} onChange={event => setReviewNote(event.target.value)} placeholder="补充核对说明；拒绝时填写原因" maxLength={4000} /></label><div className="kwActions"><button className="kwPrimary" disabled={busy || !canApproveTarget} onClick={() => void review("APPROVE")}>确认审核通过</button><button className="kwReject" disabled={busy || !reviewNote.trim()} onClick={() => void review("REJECT")}>拒绝并记录原因</button><button onClick={() => setReviewTarget(null)}>取消</button></div><DisabledReason id="kw-review-reason" reason={busy ? "正在保存人工核对记录，请稍候。" : !canApproveTarget ? "关联证据尚未核对通过，请先处理原文证据；仍可填写说明并拒绝。" : ""} />{error && errorStep === "review" && <p className="kwError" role="alert">人工核对未保存：{error}。请处理后重新提交。</p>}<p className="kwHint">由当前会话操作者提交人工审核；不会自动标记医学专家审核。</p></section>}<h3>建立知识草稿</h3><form className="kwForm kwDraftForm" aria-busy={busy} onSubmit={event => void createDraft(event)}><label>已核对的原文证据（必填）<select value={chosenEvidence?.status === "REVIEWED" ? selectedEvidence : ""} onChange={event => setSelectedEvidence(event.target.value)} required><option value="">请选择证据</option>{reviewedEvidence.map(row => <option value={evidenceRef(row)} key={evidenceRef(row)}>{row.source_title}：{row.quote_text.slice(0, 55)}</option>)}</select></label><label>知识类型<select value={draftKind} onChange={event => setDraftKind(event.target.value as DraftKind)}><option value="concept">概念</option><option value="herb">药物</option><option value="formula">方剂</option></select></label>{draftKind === "formula" ? <FormulaEditor key={formulaKey} evidence={chosenEvidence?.status === "REVIEWED" ? chosenEvidence : undefined} initial={formulaInitial} busy={busy} onSave={async body => { await action(async () => { await postJson(`${base}/drafts/formulas`, body, csrf); await refreshReview(sourceId, revision); setFormulaInitial(undefined); setFormulaKey(key => key + 1); setNotice("方剂及逐字段原文依据已保存，请核对后审核。"); }, "draft"); }} /> : <><label>规范名称（必填）<input value={draftName} onChange={event => setDraftName(event.target.value)} required maxLength={300} placeholder="依据选定原文填写" /></label>{draftKind === "concept" && <label>概念类别<select value={conceptType} onChange={event => setConceptType(event.target.value)}><option value="THEORY">理论</option><option value="DISEASE">病证</option><option value="SYMPTOM">症状</option><option value="TREATMENT">治法</option><option value="OTHER">其他</option></select></label>}<label>原文术语 / 别名（选填）<input value={terms} onChange={event => setTerms(event.target.value)} placeholder="以逗号分隔；无别名可留空" /></label><button type="submit" className="kwPrimary" aria-describedby="kw-draft-reason" disabled={!!draftReason}>建立待审核草稿</button><DisabledReason id="kw-draft-reason" reason={draftReason} />{!reviewedEvidence.length && (pendingEvidence.length ? <button type="button" disabled={busy} onClick={() => beginEvidenceReview(pendingEvidence[0])}>核对待处理证据</button> : <button type="button" disabled={busy} onClick={() => setTab("sources")}>返回原文建立证据</button>)}{error && errorStep === "draft" && <p className="kwError" role="alert">知识草稿创建未完成：{error}。已保留填写内容，请处理后重试。</p>}</>}</form><h3>知识草稿与审核记录</h3>{!drafts.length && <p className="kwEmpty">创建的概念、药物或方剂草稿会显示在这里。</p>}{drafts.map(row => <article className={`kwCard ${batchDrafts.has(row.ref) ? "batch" : ""}`} key={row.ref}><div className="kwCardHead"><strong>{draftTitle(row)}{batchDrafts.has(row.ref) && <small className="kwBatchLabel">本批候选</small>}</strong><span className="kwBadge">{displayStatus(row.status)}</span></div><DraftDetails draft={row} />{row.kind === "formula_revision" && <button disabled={busy || !row.evidence.some(item => item.status === "REVIEWED")} onClick={() => { const item = row.evidence.find(item => item.status === "REVIEWED")!; setSelectedEvidence(evidenceRef(item)); setDraftKind("formula"); setFormulaInitial({ formula_id: row.ref.split("@")[0], original_name: row.original_name || "", ingredients: row.ingredients?.map(item => ({ original_name: item.original_name, amount_original: item.amount_original || "", unit: item.unit || "", processing: item.processing || "" })) || [], method: row.method || "", indications: row.indications || "", effects: row.effects || "", preparation: row.preparation || "", cautions: row.cautions || "" }); setFormulaKey(key => key + 1); document.querySelector(".kwDraftForm")?.scrollIntoView({ block: "center" }); }}>编辑为新方剂修订</button>}{row.status === "DRAFT" && <label className="kwInline"><input type="checkbox" disabled={busy} checked={batchSelection.includes(reviewKey(row.kind, row.ref))} onChange={event => toggleBatch(reviewKey(row.kind, row.ref), event.target.checked)} />已查看此草稿，加入批量审核</label>}<details className="kwDraftEvidence"><summary>原文依据 · {row.evidence.length} 条</summary>{row.evidence.map(item => <blockquote key={evidenceRef(item)}>{readingText(item.quote_text)}<cite>{item.source_title} · 来源修订 {item.source_revision_no}</cite></blockquote>)}{onEvidence && <div className="kwActions">{row.evidence.map(item => <button key={evidenceRef(item)} onClick={() => onEvidence({ evidence_id: item.evidence_id, revision_no: item.revision_no })}>查看完整证据</button>)}</div>}</details>{row.status === "DRAFT" && <><button disabled={busy || !evidenceReady(row)} title={!evidenceReady(row) ? "先审核关联原文证据，再审核知识草稿。" : undefined} onClick={() => { setReviewTarget({ kind: row.kind, ref: row.ref, label: draftTitle(row) }); setReviewNote(""); }}>审核此草稿</button>{!evidenceReady(row) && <p className="kwHint">先审核关联原文证据，再审核知识草稿。</p>}</>}</article>)}</div></div>
      </>}
      {tab === "publish" && <>
        <JobsPanel />
        <section className="kwPublicationFlow" aria-label="加入知识库进度"><h3>加入知识库</h3><p>所有来源中已审核的最新对象一起纳入；未核对、已拒绝及被替代对象不纳入。构建完成后确认启用，旧检索版本在切换前继续可用。</p>
          <p role="status">{version?.active ? "当前所选版本可检索" : job?.purpose === "publish" && job.status === "FAILED" ? "构建失败：可重试当前版本，旧版本继续可用" : readyBuild ? "索引已就绪，等待确认启用" : job?.purpose === "publish" && !terminal(job.status) ? "正在构建索引，刷新可恢复进度" : "核对 → 加入知识库 → 构建索引 → 确认启用 → 检索 / 研究"}</p>
          {publicationPreview ? <><p>本次可纳入：{Object.entries(publicationPreview.item_counts).map(([kind, count]) => `${kindNames[kind] || kind} ${count}`).join(" · ")}</p>{publicationPreview.sources.map(row => <p key={row.source_id + row.revision_no}>{row.title} · 来源修订 {row.revision_no} · 证据 {row.evidence_count}</p>)}{publicationPreview.excluded.length > 0 && <details><summary>尚未纳入对象及原因</summary>{publicationPreview.excluded.map(row => <p key={row.kind + row.status}>{kindNames[row.kind]} {row.count}：{row.reason}</p>)}</details>}</> : <p>正在读取可纳入范围…</p>}
          <button className="kwPrimary" disabled={busy || !publicationPreview?.item_counts.evidence_revision || quality?.publication_blocked || configuration?.available === false} onClick={() => void publish(true)}>加入知识库并构建索引</button>{!publicationPreview?.item_counts.evidence_revision && <p className="kwHint">尚无可纳入对象，请先核对至少一条原文证据。</p>}
        </section>
        <div className={`kwQuality ${quality?.publication_blocked ? "blocked" : ""}`}><div><h3>{quality?.publication_blocked ? "质量阻断：暂不能发布" : "发布质量概况"}</h3><p>阻断 {quality?.open_issues.BLOCKER ?? "—"} · 警告 {quality?.open_issues.WARNING ?? "—"} · 提示 {quality?.open_issues.INFO ?? "—"}</p></div><button disabled={busy || !quality || quality.publication_blocked} onClick={() => void action(async () => { const result = await postJson<Version>(`${base}/versions`, {}, csrf); await refreshOverview(); setVersionId(result.version_id); setNotice("已生成不可变知识快照，仅包含已审核对象。"); })}>创建已审核知识快照</button></div>
        <div className="kwVersionGrid"><aside className="kwVersions"><h3>知识版本</h3>{versions.map(row => <button key={row.version_id} className={versionId === row.version_id ? "selected" : ""} onClick={() => { setVersionId(row.version_id); setVersion(null); }}><strong>版本 {row.version_no}{row.active && " · 当前检索版本"}</strong><small>{displayStatus(row.status)}</small></button>)}{!versions.length && <p className="kwEmpty">审核完成后创建第一个版本快照。</p>}</aside><div>{version ? <><h3>版本 {version.version_no} · {displayStatus(version.status)}</h3><p>已审核对象：{Object.entries(version.item_counts).map(([kind, count]) => `${({ concept: "概念", herb: "药物", evidence_revision: "证据", formula_revision: "方剂", relation: "关系" } as Record<string, string>)[kind] ?? kind} ${count}`).join(" · ")}</p><details><summary>快照校验摘要</summary><code>{version.manifest_hash}</code></details><p className="kwHint">发布方式：{configuration?.configuration?.strategy === "local-fts-exact-v1" ? "本地全文、精确与结构索引，无模型调用" : configuration?.configuration?.strategy === "hybrid-rrf-v1" ? "混合索引，含向量与重排模型调用" : "以管理员提供的发布配置为准"}</p>{version.index_builds.map(row => <div className="kwBuild" key={row.index_build_id}><strong>索引：{displayStatus(row.status)}</strong><span>全文 {displayStatus(row.fts_status)} · 向量 {displayStatus(row.vector_status)}</span></div>)}<div className="kwActions"><button disabled={busy || quality?.publication_blocked || configuration?.available === false || !configuration || !["PRE_PUBLISH_SNAPSHOT", "INDEXING", "VALIDATING"].includes(version.status)} onClick={() => void publish()}>发布并构建索引</button><button disabled={busy || !readyBuild || version.active || quality?.publication_blocked} onClick={() => void action(async () => { await postJson(`${base}/versions/${enc(versionId)}/activate`, { index_build_id: readyBuild!.index_build_id }, csrf); await Promise.all([refreshOverview(), refreshVersion(versionId)]); onPublished?.(); setNotice("版本已激活，可在检索工作区查询此版本中的证据。"); })}>激活为当前检索版本</button></div>{configuration?.available === false && <p className="kwError">{configuration.detail || "发布配置未就绪。"}</p>}{version.active && <div className="kwPublished"><strong>此版本已在检索中生效</strong><div className="kwActions"><button onClick={() => onPublished?.()}>前往知识检索</button>{onResearch && publishedSources.map(row => <button key={row.source_id} onClick={() => onResearch(row.source_id)}>研究：{row.title}</button>)}</div></div>}</> : <p className="kwEmpty">选择快照查看索引构建与发布状态。</p>}</div></div>
<details className="kwIssueList"><summary>质量问题 {issues.length} 条 · 展开查看</summary>{issues.map(row => <article className="kwCard" key={row.issue_id}><div className="kwCardHead"><strong>{row.issue_type}</strong><span className="kwBadge">{row.severity === "BLOCKER" ? "阻断发布" : row.severity === "WARNING" ? "警告" : "提示"}</span></div><details><summary>查看问题详情</summary><p>{row.description}</p></details><small>{row.target_kind} · {row.target_ref}</small><button disabled={busy} onClick={() => { setSelectedIssue(row.issue_id); setIssueNote(""); }}>处理此问题</button>{selectedIssue === row.issue_id && <div className="kwIssueAction"><label>处理说明<textarea value={issueNote} onChange={event => setIssueNote(event.target.value)} maxLength={4000} /></label><button disabled={busy || !issueNote.trim()} onClick={() => void action(async () => { await postJson(`${base}/quality-issues/${enc(row.issue_id)}/resolve`, { note: issueNote.trim(), waive: false }, csrf); await refreshOverview(); setSelectedIssue(""); setNotice("质量问题处理记录已保存。"); })}>记录已解决</button></div>}</article>)}</details>
      </>}
    </>}
  </section>;
}
