import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { apiErrorText, postJson, requestJson } from "./api";
import { readingText } from "./knowledgeSelection";
import "./research.css";
import ModelSettings from "./ModelSettings";
import ResearchReport from "./ResearchReport";

const base = "/api/v1/research/tasks";
const tabs = ["Summary", "Claims", "Debate", "Evidence", "Disputes", "Report"] as const;
type Tab = typeof tabs[number];
const tabLabels: Record<Tab, string> = { Summary: "研究概览", Claims: "观点与审计", Debate: "辩论过程", Evidence: "原文证据", Disputes: "争议与缺口", Report: "研究报告" };
const labels: Record<string, string> = {
  REPORT_REVIEW_REQUIRED: "报告已保存，综合回答待修订",
  FOLLOWUP_REVIEW: "继续审查上一轮回应",
  MECHANICAL: "引用完整性检查", SEMANTIC: "语义支持审计", PENDING_SEMANTIC: "等待语义审计", NOT_VERIFIABLE: "无法验证", Rebuttal: "回应质疑", ACCEPT: "接受质疑", PARTIAL_ACCEPT: "部分接受", REJECT: "驳回质疑", OVERCLAIM: "过度推断", TEXTUAL_MISREAD: "原文误读", HISTORICAL_SCOPE: "时代边界", CONTRADICTION: "结论矛盾", MANDATORY_REVIEW: "需人工确认", OPEN_DISPUTE_REVIEW: "存在争议，需人工审核", NO_FIRST_ROUND_CLAIMS: "首轮未形成可用观点", NO_CRITIQUES: "本轮无新增质疑", MIN_ROUNDS: "尚需完成最低辩论轮次", STABLE_EVIDENCE: "证据与观点已稳定", ROUND_LIMIT: "达到最大研究轮次", MORE_EVIDENCE_NEEDED: "需要补充证据", FIRST_DEBATE_REQUIRED: "需要进行交叉辩论",
  CREATED: "待开始", PLANNING: "拆解问题", FIRST_ROUND_COMPLETE: "首轮观点已形成", DEBATE_ROUND_COMPLETE: "本轮辩论已完成", STOP_EVALUATION: "评估停止条件", REPORTING: "生成报告", HIGH_CONFIDENCE: "高可信结论", CONDITIONAL: "条件性结论", DISPUTED: "争议结论", UNRESOLVED: "未解决问题", RETRIEVING: "检索证据", RESEARCHING: "形成观点", DEBATING: "交叉辩论", JUDGING: "综合判断", SYNTHESIZING: "汇总报告", COMPLETED: "已完成", FAILED: "执行失败", CANCELLED: "已取消", WAITING_HUMAN: "等待人工审核", ACTIVE: "运行中", PAUSED: "已暂停", PAUSE_REQUESTED: "正在暂停", RESUME_REQUESTED: "正在恢复", CANCEL_REQUESTED: "正在取消", PENDING: "待处理", RUNNING: "运行中", RETRY_WAIT: "等待重试", RESOLVED: "已处理", OPEN: "待解决", ACCEPTED: "已采纳", REJECTED: "已拒绝", WITHDRAWN: "已撤回", DRAFT: "草稿", AUDITED: "已审计", PASS: "通过", FAIL: "未通过", SUPPORTED: "证据支持", UNSUPPORTED: "证据不足", PARTIALLY_SUPPORTED: "部分支持", UNCERTAIN: "尚不确定", CONTRADICTED: "存在矛盾", DIRECT_TEXT: "原文陈述", TEXTUAL_RELATION: "文本关联", HISTORICAL_FACT: "史实", LATER_INTERPRETATION: "后世解释", THEORETICAL_INFERENCE: "理论推断", Classicist: "经典研究", HistoricalScholar: "历史考证", Theorist: "理论分析", Critic: "质疑审查", Judge: "综合裁判", Planner: "研究规划", ReportWriter: "综合写作", ReportReviewer: "回答复核", AUDIT: "证据审计", DISPUTE: "争议记录", EVIDENCE_GAP: "证据缺口", CONTINUE: "继续研究", STOP: "结束研究", REVISE: "修订观点", RETAIN: "保留观点", WITHDRAW: "撤回观点", supported: "证据支持", disputed: "存在争议", uncertain: "尚不确定", unsupported: "证据不足",
};
function label(value: string) { return labels[value] || value; }
type Ref = { evidence_id: string; revision_no: number };
type Task = { task_id: string; question: string; status: string; control_state: string; source_ids: string[]; allowed_actions: string[]; job_id: string | null; job_status?: string | null; report_available: boolean };
type Claim = { id: string; parent_claim_id: string | null; agent_run_id: string; agent_role: string; claim_type: string; assertion_text: string; rationale_summary: string; status: string; audit_status: string; evidence: Ref[] };
type Audit = { id: string; claim_id: string; sequence_no: number; stage: string; verdict: string; rationale_summary: string; evidence: Ref[] };
type Critique = { id: string; target_claim_id: string; agent_run_id: string; issue_type: string; rationale_summary: string; status: string };
type Request = { id: string; critique_id: string; query_text: string; status: string; result_count: number };
type Retrieval = { request_id: string; evidence: Ref; rank: number; channels: string[] };
type Rebuttal = { id: string; critique_id: string; round_no: number; action: string; rationale_summary: string; revised_claim_id: string | null };
type Detail = { task_id: string; subquestions: { sequence_no: number; question: string }[]; evidence: Ref[]; agent_runs: { id: string; role: string; round_no: number; status: string; model_version: string; review_summary?: string | null }[]; claims: Claim[]; audits: Audit[]; canonical_claims: { id: string; assertion_text: string; members: { claim_id: string; audit_id: string }[] }[]; debate: { critiques: Critique[]; evidence_requests: Request[]; retrievals: Retrieval[]; rebuttals: Rebuttal[] }; disputes: { id: string; target_claim_id: string; competing_claim_id: string | null; reason_code: string; rationale_summary: string; status: string; supporting_evidence: Ref[]; opposing_evidence: Ref[] }[]; evidence_gaps: { id: string; claim_id: string; reason_code: string; rationale_summary: string; status: string; evidence: Ref[] }[]; stop_evaluations: { id: string; round_no: number; decision: string; reason_code: string }[]; human_reviews: { id: string; status: string; reason_code: string; interrupted_stage: string; resume_stage: string; resolution_note: string | null }[] };
type Source = { source_id: string; title: string; status: string; data_level: string };
type Capabilities = { models: { model_version: string; label: string }[]; default_model?: string; unavailable_reason: string | null };
type Props = { sessionActive: boolean; csrf: string; initialSourceId?: string; onEvidence?: (ref: Ref) => void };
type Finding = { assertion_text: string; claim_type: string; agent_role: string; audit_verdict: string; audit_rationale: string; reason_type: string; evidence: { evidence_id: string; evidence_revision_no: number; source_title: string; quote_text: string; citation_locator: Record<string, unknown> }[] };
type Report = { task_id: string; schema_version: string; content_hash: string; question: string; counts: Record<string, number>; sections: Record<string, Finding[]>; answer?: { paragraphs: { text: string; kind: string; evidence: Finding["evidence"] }[]; review_summary: string } | null; open_disputes: { reason_code: string; rationale_summary: string }[]; unresolved_gaps: { reason_code: string; rationale_summary: string }[]; excluded_claim_count: number };
type Export = { file_format: string; status: string; job_id: string; download_url: string | null };
type Job = { job_id: string; status: string; attempts: number; max_attempts: number; failure_reason?: string | null };
const researchEvents = ["created", "started", "planned", "evidence_retrieved", "first_round_prepared", "critic_prepared", "rebuttal_prepared", "claims_normalized", "debate_round_completed", "stop_evaluated", "waiting_human", "human_review_resolved", "judge_prepared", "synthesized", "report_written", "report_reviewed", "report_saved", "pause_requested", "paused", "resume_requested", "resumed", "cancel_requested", "cancelled"];

function RefList({ refs, onEvidence }: { refs: Ref[]; onEvidence?: Props["onEvidence"] }) {
  return refs.length ? <div className="refList">{refs.map((ref) => <button type="button" className="refChip" key={`${ref.evidence_id}:${ref.revision_no}`} onClick={() => onEvidence?.(ref)} disabled={!onEvidence} aria-label={`查看证据 ${ref.evidence_id} 修订 ${ref.revision_no}`}>查看原文 · 修订 {ref.revision_no}<small>{ref.evidence_id}</small></button>)}</div> : <span className="muted">未关联证据</span>;
}

function Item({ title, children }: { title: string; children: ReactNode }) {
  return <article className="researchItem"><h4>{title}</h4>{children}</article>;
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="empty researchEmpty">{children}</p>;
}

export default function ResearchWorkspace({ sessionActive, csrf, initialSourceId, onEvidence }: Props) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [question, setQuestion] = useState("");
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [modelVersion, setModelVersion] = useState("");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState("");
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [allowOutbound, setAllowOutbound] = useState(false);
  const [tab, setTab] = useState<Tab>("Summary");
  const [view, setView] = useState<"round" | "claim">("round");
  const [reviewNote, setReviewNote] = useState("");
  const [exports, setExports] = useState<Record<string, Export | null>>({});
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refreshError, setRefreshError] = useState("");
  const selectedId = useRef("");
  const sessionReady = useRef(sessionActive);
  const preselectedSource = useRef("");
  sessionReady.current = sessionActive;

  const refreshList = useCallback(async () => {
    const [nextTasks, nextSources] = await Promise.all([
      requestJson<Task[]>(base), requestJson<Source[]>("/api/v1/knowledge/published-sources"),
    ]);
    if (!sessionReady.current) return;
    setTasks(nextTasks);
    setSources(nextSources);
    if (!selectedId.current) setRefreshError("");
    if (!selectedId.current) {
      let saved = "";
      try { saved = sessionStorage.getItem("tcm.research.task") || ""; } catch { /* optional position storage */ }
      const previous = nextTasks.find(item => item.task_id === saved);
      if (previous) { selectedId.current = previous.task_id; setTaskId(previous.task_id); setTask(previous); }
    }
    setSourceIds((ids) => ids.filter((id) => nextSources.some((source) => source.source_id === id)));
  }, []);

  const refreshTask = useCallback(async (id: string) => {
    const [nextTask, nextDetail] = await Promise.all([
      requestJson<Task>(`${base}/${encodeURIComponent(id)}`),
      requestJson<Detail>(`${base}/${encodeURIComponent(id)}/details`),
    ]);
    const [nextJob, nextReport] = await Promise.all([
      nextTask.job_id ? requestJson<Job>(`/api/v1/jobs/${encodeURIComponent(nextTask.job_id)}`) : null,
      nextTask.report_available ? requestJson<Report>(`${base}/${encodeURIComponent(id)}/report`) : null,
    ]);
    let nextExports: Record<string, Export | null> = {};
    if (nextTask.report_available) {
      const formats = await Promise.all(["markdown", "docx"].map(async (format) => {
        try { return [format, await requestJson<Export>(`${base}/${encodeURIComponent(id)}/exports/${format}`)] as const; }
        catch (cause) {
          if (cause && typeof cause === "object" && "code" in cause && cause.code === "EXPORT_NOT_FOUND") return [format, null] as const;
          throw cause;
        }
      }));
      nextExports = Object.fromEntries(formats);
    }
    if (!sessionReady.current || selectedId.current !== id) return;
    setTask(nextTask); setDetail(nextDetail); setJob(nextJob); setReport(nextReport); setExports(nextExports);
    setRefreshError("");
  }, []);

  useEffect(() => {
    if (!sessionActive) { selectedId.current = ""; preselectedSource.current = ""; setTasks([]); setSources([]); setSourceIds([]); setTaskId(""); setTask(null); setDetail(null); setReport(null); setJob(null); setExports({}); setCapabilities(null); setAllowOutbound(false); return; }
    let active = true;
    void refreshList().catch((cause) => { if (active) setRefreshError(apiErrorText(cause)); });
    void requestJson<Capabilities>("/api/v1/research/capabilities").then((next) => {
      if (active) { setCapabilities(next); setCapabilityError(""); setModelVersion(next.default_model || ""); }
    }).catch((cause) => { if (active) setCapabilityError(apiErrorText(cause)); });
    return () => { active = false; };
  }, [sessionActive, refreshList]);

  useEffect(() => {
    if (initialSourceId && preselectedSource.current !== initialSourceId && sources.some((source) => source.source_id === initialSourceId)) {
      preselectedSource.current = initialSourceId;
      setSourceIds((ids) => ids.includes(initialSourceId) ? ids : [...ids, initialSourceId]);
    }
  }, [initialSourceId, sources]);

  useEffect(() => {
    if (!sessionActive || !taskId) return;
    let active = true;
    const refresh = () => { void refreshTask(taskId).catch((cause) => { if (active) setRefreshError(apiErrorText(cause)); }); };
    refresh();
    const timer = window.setInterval(() => {
      refresh();
      void refreshList().catch(() => {});
    }, 5000);
    const stream = new EventSource(`${base}/${encodeURIComponent(taskId)}/events`);
    stream.addEventListener("snapshot", refresh);
    researchEvents.forEach((name) => stream.addEventListener(`research_task.${name}`, refresh));
    // Polling repairs missed events and updates export jobs, which have no task event.
    return () => { active = false; window.clearInterval(timer); stream.close(); };
  }, [sessionActive, taskId, refreshTask, refreshList]);

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await action(); await refreshList(); if (selectedId.current) await refreshTask(selectedId.current); }
    catch (cause) { setError(apiErrorText(cause)); }
    finally { setBusy(false); }
  }

  function post(url: string, body: object = {}) {
    if (!csrf) throw new Error("当前会话缺少 CSRF 凭据，请由桌面程序重新建立本地会话。");
    return postJson(url, body, csrf);
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run(async () => {
      const created = await post(base, { question: question.trim(), source_ids: sourceIds }) as Task;
      selectTask(created); setQuestion("");
    });
  }

  function selectTask(next: Task) {
    selectedId.current = next.task_id;
    try { sessionStorage.setItem("tcm.research.task", next.task_id); } catch { /* optional position storage */ }
    setTaskId(next.task_id); setTask(next); setDetail(null); setReport(null); setJob(null); setExports({});
    setTab(next.report_available ? "Report" : "Summary"); setAllowOutbound(false); setReviewNote(""); setError("");
  }

  const pendingReview = detail?.human_reviews.find((review) => review.status === "PENDING");
  const activeJob = task?.job_id;
  const selectedTask = tasks.find((item) => item.task_id === taskId);
  const can = (action: string) => !busy && !!csrf && !!task?.allowed_actions.includes(action);
  const claimed = detail?.claims || [];
  const auditFor = (id: string) => detail?.audits.filter((row) => row.claim_id === id) || [];
  const critiqueFor = (id: string) => detail?.debate.critiques.filter((row) => row.target_claim_id === id) || [];
  const firstRuns = detail?.agent_runs.filter(row => row.round_no === 1 && ["Classicist", "HistoricalScholar", "Theorist"].includes(row.role)) || [];
  const mechanicallyChecked = new Set(detail?.audits.filter(row => row.stage === "MECHANICAL").map(row => row.claim_id)).size;
  const semanticallyChecked = new Set(detail?.audits.filter(row => row.stage === "SEMANTIC").map(row => row.claim_id)).size;
  const nextRole = detail?.agent_runs.find(row => row.status === "PENDING");
  const jobStatus = job?.status || task?.job_status;
  const executionStatus = jobStatus === "FAILED" ? "执行失败，已停止" : jobStatus === "RETRY_WAIT" ? "等待重试" : ["COMPLETED", "CANCELLED", "REPORT_REVIEW_REQUIRED"].includes(task?.status || "") ? "已结束" : label(task?.control_state || "—");
  const progressText = job?.status === "FAILED" ? (task?.allowed_actions.includes("retry") ? "执行失败，可重试当前步骤" : "执行失败，现有研究记录已保留") : task?.status === "FIRST_ROUND_COMPLETE" ? `正在审计观点：语义审计已完成 ${semanticallyChecked} / ${claimed.length}` : task?.status === "RESEARCHING" && nextRole ? `正在生成${label(nextRole.role)}观点` : ["DEBATING", "REPORTING"].includes(task?.status || "") && nextRole ? `正在执行${label(nextRole.role)}` : task?.status === "CREATED" ? "等待开始研究" : label(task?.status || "读取研究进度");

  return <section className="researchWorkspace" aria-labelledby="research-title">
    <div className="workspaceHead"><div><span className="sectionLabel">理论研究工作区</span><h2 id="research-title">从问题到可追溯报告</h2></div><div><span className="modelNote">研究过程与最终结论分开保存</span>{sessionActive && <button type="button" onClick={() => setShowModelSettings(value => !value)} aria-expanded={showModelSettings}>模型设置</button>}</div></div>
    {sessionActive && showModelSettings && <ModelSettings csrf={csrf} onClose={() => setShowModelSettings(false)} onSaved={async () => {
      const next = await requestJson<Capabilities>("/api/v1/research/capabilities");
      setCapabilities(next); setCapabilityError(""); setModelVersion(next.default_model || "");
    }} />}
    {(error || refreshError) && <p className="error workspaceAlert" role="alert">{error || refreshError}</p>}
    {sessionActive && !csrf && <p className="workspaceAlert" role="status">当前标签页没有写操作凭据。请回到建立会话的标签页，或由桌面程序重新建立本地会话。</p>}
    {!sessionActive ? <div className="panel"><h3>请先连接本地工作台</h3><p className="muted">在页面顶部建立会话后，可使用已发布知识开展研究。</p></div> : <div className="workspaceGrid">
      <aside className="panel researchSidebar">
        <h3>创建研究</h3>
        <form onSubmit={create} className="researchForm">
          <label htmlFor="research-question">研究问题</label><textarea id="research-question" rows={4} maxLength={2000} required value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="输入待研究的问题" />
          <fieldset><legend>已发布来源</legend><p className="muted">不选择时使用当前已发布知识范围。开始后冻结版本与证据修订。</p>{initialSourceId && !sources.some((source) => source.source_id === initialSourceId) && <p className="workspaceAlert">所选来源尚未进入当前发布版本，请先完成审核发布。</p>}<div className="sourceChoices">{sources.map((source) => <label key={source.source_id}><input type="checkbox" value={source.source_id} checked={sourceIds.includes(source.source_id)} onChange={(event) => setSourceIds((ids) => event.target.checked ? [...ids, source.source_id] : ids.filter((id) => id !== source.source_id))} />{source.title}<small>已发布</small></label>)}</div>{!sources.length && <p className="muted">当前没有已发布来源，请在知识工作台完成审核与发布。</p>}</fieldset>
          <button disabled={busy || !csrf || !question.trim() || !sources.length || (!!initialSourceId && !sources.some((source) => source.source_id === initialSourceId) && !sourceIds.length)}>创建研究任务</button>
        </form>
        <h3>研究任务</h3><div className="taskList">{tasks.map((item) => <button key={item.task_id} className={taskId === item.task_id ? "selected" : ""} onClick={() => selectTask(item)}><strong>{item.question}</strong><span>{label(item.job_status === "FAILED" ? "FAILED" : item.status)} · {item.task_id}</span></button>)}{!tasks.length && <p className="muted">还没有研究任务，请输入问题创建研究。</p>}</div>
      </aside>
      <div className="researchMain">
        {!taskId ? <Empty>创建研究或从左侧选择已有任务。</Empty> : <>
          <section className={`panel taskOverview ${tab === "Report" && task?.status === "COMPLETED" ? "reportOverview" : ""}`}>
            <div className="panelHead"><div><span className="sectionLabel">{taskId}</span><h3>{task?.question || selectedTask?.question || "读取中…"}</h3></div><span className={`badge ${task?.status === "COMPLETED" ? "ready" : "pending"}`}>{jobStatus === "FAILED" ? `执行失败 · ${label(task?.status || "")}` : label(task?.status || "读取中")}</span></div>
            <p className="muted">执行状态：{executionStatus} · {task?.source_ids.length ? `限定 ${task.source_ids.length} 项来源` : "使用已发布知识范围"}</p>
            <p className="muted">研究问题 → 原文证据 → 多角度观点 → 质疑与审计 → 可追溯报告</p>
            {detail && <section className="researchProgress" aria-label="研究实时进度" aria-live="polite"><strong>{progressText}</strong><div className="reportCounts"><span>子问题 {detail.subquestions.length}</span><span>原文证据 {detail.evidence.length}</span><span>首轮角色 {firstRuns.filter(row => row.status === "COMPLETED").length} / {firstRuns.length}</span><span>观点 {claimed.length}</span><span>引用检查 {mechanicallyChecked} / {claimed.length}</span><span>语义审计 {semanticallyChecked} / {claimed.length}</span><span>质疑 {detail.debate.critiques.length}</span><span>回应 {detail.debate.rebuttals.length}</span></div><small className="muted">每个节点保存后更新数量；云端模型调用期间，已完成数量可能暂时不变。</small></section>}
            {(task?.status === "WAITING_HUMAN" || task?.status === "FAILED" || task?.status === "CANCELLED" || job?.status === "FAILED" || job?.status === "RETRY_WAIT") && <p className="workspaceAlert" role="status">{task?.status === "WAITING_HUMAN" ? "研究已暂停，等待人工审核。处理下方待审事项后才能继续。" : job?.status === "RETRY_WAIT" ? `研究任务执行失败，等待重试（${job.attempts}/${job.max_attempts}）。` : task?.status === "FAILED" || job?.status === "FAILED" ? (job?.failure_reason || "研究运行失败。现有过程与证据仍可查看，请联系管理员处理后恢复。") : "研究已取消，现有过程记录仍可查看。"}</p>}
            {task?.status === "CREATED" && <div className="startForm"><label htmlFor="model-version">研究模型</label><select id="model-version" value={modelVersion} onChange={(event) => setModelVersion(event.target.value)} disabled={!capabilities?.models.length}><option value="">{capabilities ? "请选择已配置模型" : "读取模型配置中…"}</option>{capabilities?.models.map((model) => <option key={model.model_version} value={model.model_version}>{model.label}</option>)}</select>{(capabilityError || capabilities?.unavailable_reason) && <p className="workspaceAlert" role="status">无法开始真实研究：{capabilityError || capabilities?.unavailable_reason}</p>}<label className="hint"><input type="checkbox" checked={allowOutbound} onChange={(event) => setAllowOutbound(event.target.checked)} />同意将本次研究问题发送给所选云端模型。模型路由已配置，凭据与供应商可用性将在授权启动后核验。研究还会使用允许外发的原文证据；来源权利与外发权限由系统核验，调用可能产生费用。</label></div>}
            <div className="actionRow">
              {(["start", "pause", "resume", "retry", "cancel"] as const).map((action) => <button key={action} type="button" disabled={!can(action) || (action === "start" && (!capabilities?.models.some((model) => model.model_version === modelVersion) || !allowOutbound))} onClick={() => void run(async () => { await post(`${base}/${encodeURIComponent(taskId)}/${action}`, action === "start" ? { model_version: modelVersion, allow_question_outbound: allowOutbound } : {}); })}>{ { start: "开始研究", pause: "暂停", resume: "恢复", retry: "重试失败步骤", cancel: "取消" }[action] }</button>)}
            </div>
            {job?.status === "FAILED" && <button type="button" disabled={busy || !csrf || !task} onClick={() => void run(async () => { const created = await post(base, { question: task!.question, source_ids: task!.source_ids }) as Task; selectTask(created); })}>用最新规则重新研究</button>}
            {can("recover_report") && <button type="button" onClick={() => void run(async () => { await post(`${base}/${encodeURIComponent(taskId)}/recover-report`, {}); setTab("Report"); })}>保存已有研究报告</button>}
            {activeJob && <p className="muted">运行任务：{activeJob}</p>}
            {pendingReview && <form className="reviewForm" onSubmit={(event) => { event.preventDefault(); void run(async () => { await post(`${base}/${encodeURIComponent(taskId)}/human-reviews/${encodeURIComponent(pendingReview.id)}/resolve`, { note: reviewNote.trim() }); setReviewNote(""); }); }}><h4>待人工审核 · {label(pendingReview.reason_code)}</h4><p>中断阶段：{label(pendingReview.interrupted_stage)} · 恢复阶段：{label(pendingReview.resume_stage)}</p><label htmlFor="review-note">审核说明</label><textarea id="review-note" required maxLength={2000} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} /><button disabled={!can("resolve_review") || !reviewNote.trim()}>提交审核并继续</button></form>}
          </section>
          <nav className="researchTabs" aria-label="研究详情">{tabs.map((name) => <button type="button" key={name} aria-current={tab === name ? "page" : undefined} onClick={() => setTab(name)}>{tabLabels[name]}</button>)}</nav>
          <section className="panel tabPanel" aria-label={tabLabels[tab]}>
            {tab === "Summary" && <><h3>研究概览</h3>{detail ? <><p>子问题 {detail.subquestions.length} · 观点 {detail.claims.length} · 审计 {detail.audits.length} · 争议 {detail.disputes.length}</p>{detail.subquestions.map((row) => <Item key={row.sequence_no} title={`子问题 ${row.sequence_no}`}><p>{row.question}</p></Item>)}{detail.stop_evaluations.map((row) => <Item key={row.id} title={`第 ${row.round_no} 轮停止判定：${label(row.decision)}`}><p>{label(row.reason_code)}</p></Item>)}{detail.human_reviews.map((row) => <Item key={row.id} title={`人工审核：${label(row.status)}`}><p>{label(row.reason_code)} · {row.resolution_note || "待处理"}</p></Item>)}</> : <Empty>正在读取研究详情。</Empty>}</>}
            {tab === "Claims" && <><h3>观点与证据审计</h3>{claimed.length ? claimed.map((claim) => <Item key={claim.id} title={`${label(claim.claim_type)} · ${label(claim.agent_role)}`}><p>{claim.assertion_text}</p><p className="muted">{claim.id} · 状态 {label(claim.status)} · 审计 {label(claim.audit_status)}{claim.parent_claim_id && ` · 修订自 ${claim.parent_claim_id}`}</p><p>{claim.rationale_summary}</p><RefList onEvidence={onEvidence} refs={claim.evidence} />{auditFor(claim.id).map((audit) => <div className="timelineStep" key={audit.id}><strong>审计 {audit.sequence_no} · {label(audit.stage)} · {label(audit.verdict)}</strong><p>{audit.rationale_summary}</p><RefList onEvidence={onEvidence} refs={audit.evidence} /></div>)}</Item>) : <Empty>尚无观点。首轮草稿会出现在这里，研究报告生成后可查看最终结论。</Empty>}</>}
            {tab === "Debate" && <>{detail?.agent_runs.filter(run => run.role === "Critic" && run.review_summary).map(run => <Item key={run.id} title={`第 ${run.round_no} 轮审查说明`}><p>{run.review_summary}</p></Item>)}<div className="panelHead"><h3>完整辩论时间线</h3><div className="viewSwitch"><button className={view === "round" ? "selected" : ""} onClick={() => setView("round")}>按轮次</button><button className={view === "claim" ? "selected" : ""} onClick={() => setView("claim")}>按观点</button></div></div>{!detail?.debate.critiques.length ? <Empty>{detail?.agent_runs.some(run => run.role === "Critic" && run.status === "COMPLETED") ? "质疑审查已执行，未提出实质质疑，因此未产生回应轮次。" : "质疑审查尚未执行。"}</Empty> : view === "claim" ? claimed.filter((claim) => critiqueFor(claim.id).length).map((claim) => <Item key={claim.id} title={claim.assertion_text}>{critiqueFor(claim.id).map((critique) => <DebateChain key={critique.id} critique={critique} detail={detail!} onEvidence={onEvidence} />)}</Item>) : [...new Set(detail.debate.rebuttals.map((row) => row.round_no).concat(detail.agent_runs.map((row) => row.round_no)))].sort((a, b) => a - b).map((round) => <Item key={round} title={`第 ${round} 轮`}>{detail.debate.critiques.filter((critique) => detail.agent_runs.find((run) => run.id === critique.agent_run_id)?.round_no === round).map((critique) => <DebateChain key={critique.id} critique={critique} detail={detail} onEvidence={onEvidence} />)}</Item>)}</>}
            {tab === "Evidence" && <><h3>证据引用</h3>{detail?.evidence.length ? detail.evidence.map((ref) => <Item key={`${ref.evidence_id}:${ref.revision_no}`} title={`${ref.evidence_id} · 修订 ${ref.revision_no}`}><p className="muted">引用于 {claimed.filter((claim) => claim.evidence.some((item) => item.evidence_id === ref.evidence_id && item.revision_no === ref.revision_no)).length} 条观点。点击原文查看本次引用的精确修订。</p><RefList refs={[ref]} onEvidence={onEvidence} /></Item>) : <Empty>尚无证据引用。</Empty>}</>}
            {tab === "Disputes" && <><h3>争议与证据缺口</h3>{detail?.disputes.map((row) => <Item key={row.id} title={`${label(row.status)} · ${label(row.reason_code)}`}><p>{row.rationale_summary}</p><p className="muted">观点 {row.target_claim_id}{row.competing_claim_id && ` · 对立 ${row.competing_claim_id}`}</p><strong>支持证据</strong><RefList onEvidence={onEvidence} refs={row.supporting_evidence} /><strong>反对证据</strong><RefList onEvidence={onEvidence} refs={row.opposing_evidence} /></Item>)}{detail?.evidence_gaps.map((row) => <Item key={row.id} title={`证据缺口 · ${label(row.status)}`}><p>{row.rationale_summary}</p><p className="muted">{label(row.reason_code)} · 观点 {row.claim_id}</p><RefList onEvidence={onEvidence} refs={row.evidence} /></Item>)}{!detail?.disputes.length && !detail?.evidence_gaps.length && <Empty>尚无争议或证据缺口。</Empty>}</>}
            {tab === "Report" && <><h3>研究报告</h3>{!report ? <Empty>研究报告尚未生成。首轮待审草稿请在“观点与审计”查看，不作为最终结论。</Empty> : <><ResearchReport report={report} onEvidence={onEvidence} /><div className="exportRow">{(["markdown", "docx"] as const).map((format) => <div key={format}><button disabled={!can("export")} onClick={() => void run(async () => { await post(`${base}/${encodeURIComponent(taskId)}/exports/${format}`); })}>生成 {format.toUpperCase()}</button><span>{label(exports[format]?.status || "尚未生成")}</span>{exports[format]?.status === "COMPLETED" && exports[format]?.download_url && <a href={exports[format]!.download_url!}>下载 {format.toUpperCase()}</a>}</div>)}</div>{task?.allowed_actions.includes("revise_report") && <button type="button" disabled={!can("revise_report")} onClick={() => void run(async () => { await post(`${base}/${encodeURIComponent(taskId)}/revise-report`, {}); })}>继续修订综合回答</button>}</>}</>}
          </section>
        </>}
      </div>
    </div>}
  </section>;
}

function DebateChain({ critique, detail, onEvidence }: { critique: Critique; detail: Detail; onEvidence?: Props["onEvidence"] }) {
  const requests = detail.debate.evidence_requests.filter((row) => row.critique_id === critique.id);
  const rebuttals = detail.debate.rebuttals.filter((row) => row.critique_id === critique.id);
  return <div className="debateChain"><div className="timelineStep"><strong>质疑 · {label(critique.issue_type)}</strong><p>{critique.rationale_summary}</p><small>针对 {critique.target_claim_id}</small></div>{requests.map((row) => <div className="timelineStep" key={row.id}><strong>补证请求 · {label(row.status)}</strong><p>{row.query_text}</p><small>检索结果 {row.result_count}</small><RefList onEvidence={onEvidence} refs={detail.debate.retrievals.filter((item) => item.request_id === row.id).map((item) => item.evidence)} /></div>)}{rebuttals.map((row) => <div className="timelineStep" key={row.id}><strong>第 {row.round_no} 轮反驳 · {label(row.action)}</strong><p>{row.rationale_summary}</p>{row.revised_claim_id && <><small>修订观点 {row.revised_claim_id}</small>{detail.audits.filter((audit) => audit.claim_id === row.revised_claim_id).map((audit) => <div key={audit.id}><p>复审 {label(audit.stage)}：{label(audit.verdict)} · {audit.rationale_summary}</p><RefList refs={audit.evidence} onEvidence={onEvidence} /></div>)}</>}</div>)}</div>;
}
