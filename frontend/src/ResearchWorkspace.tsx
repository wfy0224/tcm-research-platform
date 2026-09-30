import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";

const base = "/api/v1/research/tasks";
const csrfKey = "tcm.local.csrf";
const tabs = ["Summary", "Claims", "Debate", "Evidence", "Disputes", "Report"] as const;
type Tab = typeof tabs[number];
type Ref = { evidence_id: string; revision_no: number };
type Task = { task_id: string; question: string; status: string; control_state: string; source_ids: string[]; allowed_actions: string[]; job_id: string | null; report_available: boolean };
type Claim = { id: string; parent_claim_id: string | null; agent_run_id: string; agent_role: string; claim_type: string; assertion_text: string; rationale_summary: string; status: string; audit_status: string; evidence: Ref[] };
type Audit = { id: string; claim_id: string; sequence_no: number; stage: string; verdict: string; rationale_summary: string; evidence: Ref[] };
type Critique = { id: string; target_claim_id: string; agent_run_id: string; issue_type: string; rationale_summary: string; status: string };
type Request = { id: string; critique_id: string; query_text: string; status: string; result_count: number };
type Retrieval = { request_id: string; evidence: Ref; rank: number; channels: string[] };
type Rebuttal = { id: string; critique_id: string; round_no: number; action: string; rationale_summary: string; revised_claim_id: string | null };
type Detail = { task_id: string; subquestions: { sequence_no: number; question: string }[]; evidence: Ref[]; agent_runs: { id: string; role: string; round_no: number; status: string; model_version: string }[]; claims: Claim[]; audits: Audit[]; canonical_claims: { id: string; assertion_text: string; members: { claim_id: string; audit_id: string }[] }[]; debate: { critiques: Critique[]; evidence_requests: Request[]; retrievals: Retrieval[]; rebuttals: Rebuttal[] }; disputes: { id: string; target_claim_id: string; competing_claim_id: string | null; reason_code: string; rationale_summary: string; status: string; supporting_evidence: Ref[]; opposing_evidence: Ref[] }[]; evidence_gaps: { id: string; claim_id: string; reason_code: string; rationale_summary: string; status: string; evidence: Ref[] }[]; stop_evaluations: { id: string; round_no: number; decision: string; reason_code: string }[]; human_reviews: { id: string; status: string; reason_code: string; interrupted_stage: string; resume_stage: string; resolution_note: string | null }[] };
type Source = { source_id: string; title: string; status: string; data_level: string };
type Finding = { assertion_text: string; claim_type: string; agent_role: string; audit_verdict: string; audit_rationale: string; reason_type: string; evidence: { evidence_id: string; evidence_revision_no: number; source_title: string; quote_text: string; citation_locator: Record<string, unknown> }[] };
type Report = { task_id: string; schema_version: string; content_hash: string; question: string; counts: Record<string, number>; sections: Record<string, Finding[]>; open_disputes: { reason_code: string; rationale_summary: string }[]; unresolved_gaps: { reason_code: string; rationale_summary: string }[]; excluded_claim_count: number };
type Export = { file_format: string; status: string; job_id: string; download_url: string | null };
type Job = { job_id: string; status: string; attempts: number; max_attempts: number };
const researchEvents = ["created", "started", "planned", "evidence_retrieved", "first_round_prepared", "critic_prepared", "rebuttal_prepared", "claims_normalized", "debate_round_completed", "stop_evaluated", "waiting_human", "human_review_resolved", "judge_prepared", "synthesized", "report_saved", "pause_requested", "paused", "resume_requested", "resumed", "cancel_requested", "cancelled"];

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.code || `HTTP ${response.status}`);
  return data as T;
}

function writeHeaders(csrf: string): HeadersInit {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID() };
}

function RefList({ refs }: { refs: Ref[] }) {
  return refs.length ? <div className="refList">{refs.map((ref) => <span className="refChip" key={`${ref.evidence_id}:${ref.revision_no}`}>{ref.evidence_id} · 修订 {ref.revision_no}</span>)}</div> : <span className="muted">未关联证据</span>;
}

function Item({ title, children }: { title: string; children: ReactNode }) {
  return <article className="researchItem"><h4>{title}</h4>{children}</article>;
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="empty researchEmpty">{children}</p>;
}

export default function ResearchWorkspace() {
  const [csrf, setCsrf] = useState(() => sessionStorage.getItem(csrfKey) || "");
  const [sessionActive, setSessionActive] = useState(false);
  const [bootstrapSecret, setBootstrapSecret] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [question, setQuestion] = useState("");
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [modelVersion, setModelVersion] = useState("");
  const [allowOutbound, setAllowOutbound] = useState(false);
  const [tab, setTab] = useState<Tab>("Summary");
  const [view, setView] = useState<"round" | "claim">("round");
  const [reviewNote, setReviewNote] = useState("");
  const [exports, setExports] = useState<Record<string, Export | null>>({});
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refreshList = useCallback(async () => {
    const [nextTasks, nextSources] = await Promise.all([
      requestJson<Task[]>(base), requestJson<Source[]>("/api/v1/knowledge/sources"),
    ]);
    setTasks(nextTasks);
    setSources(nextSources);
  }, []);

  const refreshTask = useCallback(async (id: string) => {
    const [nextTask, nextDetail] = await Promise.all([
      requestJson<Task>(`${base}/${encodeURIComponent(id)}`),
      requestJson<Detail>(`${base}/${encodeURIComponent(id)}/details`),
    ]);
    setTask(nextTask);
    setDetail(nextDetail);
    setJob(nextTask.job_id ? await requestJson<Job>(`/api/v1/jobs/${encodeURIComponent(nextTask.job_id)}`) : null);
    setReport(nextTask.report_available ? await requestJson<Report>(`${base}/${encodeURIComponent(id)}/report`) : null);
    if (nextTask.report_available) {
      const formats = await Promise.all(["markdown", "docx"].map(async (format) => {
        try { return [format, await requestJson<Export>(`${base}/${encodeURIComponent(id)}/exports/${format}`)] as const; }
        catch { return [format, null] as const; }
      }));
      setExports(Object.fromEntries(formats));
    } else setExports({});
  }, []);

  useEffect(() => {
    let active = true;
    void requestJson("/api/v1/local-session").then(() => {
      if (active) { setSessionActive(true); void refreshList().catch((cause) => setError(String(cause))); }
    }).catch(() => { if (active) setSessionActive(false); });
    return () => { active = false; };
  }, [refreshList]);

  useEffect(() => {
    if (!sessionActive || !taskId) return;
    let active = true;
    const refresh = () => { void refreshTask(taskId).catch((cause) => { if (active) setError(String(cause)); }); };
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
    try { await action(); await refreshList(); if (taskId) await refreshTask(taskId); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  function post(url: string, body: object = {}) {
    if (!csrf) throw new Error("当前会话缺少 CSRF 凭据，请由桌面程序重新建立本地会话。");
    return requestJson(url, { method: "POST", headers: writeHeaders(csrf), body: JSON.stringify(body) });
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run(async () => {
      const created = await post(base, { question: question.trim(), source_ids: sourceIds }) as Task;
      setTaskId(created.task_id); setTask(created); setDetail(null); setReport(null); setTab("Summary"); setQuestion("");
    });
  }

  async function bootstrap(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const issued = await requestJson<{ csrf_token: string }>("/api/v1/local-session/bootstrap", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bootstrap_secret: bootstrapSecret }),
      });
      if (!issued.csrf_token) throw new Error("本地会话未返回 CSRF 凭据");
      sessionStorage.setItem(csrfKey, issued.csrf_token); setCsrf(issued.csrf_token);
      setBootstrapSecret(""); setSessionActive(true); await refreshList();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  const pendingReview = detail?.human_reviews.find((review) => review.status === "PENDING");
  const activeJob = task?.job_id;
  const selectedTask = tasks.find((item) => item.task_id === taskId);
  const can = (action: string) => !busy && !!task?.allowed_actions.includes(action);
  const claimed = detail?.claims || [];
  const auditFor = (id: string) => detail?.audits.filter((row) => row.claim_id === id) || [];
  const critiqueFor = (id: string) => detail?.debate.critiques.filter((row) => row.target_claim_id === id) || [];

  return <section className="researchWorkspace" aria-labelledby="research-title">
    <div className="workspaceHead"><div><span className="sectionLabel">理论研究工作区</span><h2 id="research-title">从问题到可追溯报告</h2></div><span className="modelNote">研究过程与最终结论分开保存</span></div>
    {error && <p className="error workspaceAlert" role="alert">{error}</p>}
    {sessionActive && !csrf && <p className="workspaceAlert" role="status">当前标签页没有写操作凭据。请回到建立会话的标签页，或由桌面程序重新建立本地会话。</p>}
    {!sessionActive ? <div className="panel">
      <h3>连接本地研究会话</h3><p className="muted">请输入桌面程序提供的一次性启动密钥。会话建立后可创建和管理研究任务。</p>
      <form className="inlineForm" onSubmit={(event) => void bootstrap(event)}><label htmlFor="bootstrap-secret">启动密钥</label><input id="bootstrap-secret" type="password" autoComplete="off" value={bootstrapSecret} onChange={(event) => setBootstrapSecret(event.target.value)} required /><button disabled={busy || !bootstrapSecret}>连接</button></form>
    </div> : <div className="workspaceGrid">
      <aside className="panel researchSidebar">
        <h3>创建研究</h3>
        <form onSubmit={create} className="researchForm">
          <label htmlFor="research-question">研究问题</label><textarea id="research-question" rows={4} maxLength={2000} required value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="输入待研究的问题" />
          <fieldset><legend>来源范围</legend><p className="muted">不选择时使用当前可用知识范围。</p><div className="sourceChoices">{sources.map((source) => <label key={source.source_id}><input type="checkbox" value={source.source_id} checked={sourceIds.includes(source.source_id)} onChange={(event) => setSourceIds((ids) => event.target.checked ? [...ids, source.source_id] : ids.filter((id) => id !== source.source_id))} />{source.title}<small>{source.status}</small></label>)}</div></fieldset>
          <button disabled={busy || !csrf || !question.trim()}>创建研究任务</button>
        </form>
        <h3>研究任务</h3><div className="taskList">{tasks.map((item) => <button key={item.task_id} className={taskId === item.task_id ? "selected" : ""} onClick={() => { setTaskId(item.task_id); setTask(item); setDetail(null); setReport(null); setTab("Summary"); }}><strong>{item.question}</strong><span>{item.status} · {item.task_id}</span></button>)}</div>
      </aside>
      <div className="researchMain">
        {!taskId ? <Empty>创建研究或从左侧选择已有任务。</Empty> : <>
          <section className="panel taskOverview">
            <div className="panelHead"><div><span className="sectionLabel">{taskId}</span><h3>{task?.question || selectedTask?.question || "读取中…"}</h3></div><span className={`badge ${task?.status === "COMPLETED" ? "ready" : "pending"}`}>{task?.status || "读取中"}</span></div>
            <p className="muted">控制状态：{task?.control_state || "—"} · 来源 {task?.source_ids.length || 0} 项</p>
            {(task?.status === "WAITING_HUMAN" || task?.status === "FAILED" || task?.status === "CANCELLED" || job?.status === "FAILED" || job?.status === "RETRY_WAIT") && <p className="workspaceAlert" role="status">{task?.status === "WAITING_HUMAN" ? "研究已暂停，等待人工审核。处理下方待审事项后才能继续。" : job?.status === "RETRY_WAIT" ? `研究任务执行失败，等待重试（${job.attempts}/${job.max_attempts}）。` : task?.status === "FAILED" || job?.status === "FAILED" ? "研究运行失败。请查看任务状态和审计记录。" : "研究已取消，现有过程记录仍可查看。"}</p>}
            {task?.status === "CREATED" && <div className="startForm"><label htmlFor="model-version">模型路由（provider/model）</label><input id="model-version" value={modelVersion} onChange={(event) => setModelVersion(event.target.value)} placeholder="例如 siliconflow/模型名" /><label className="hint"><input type="checkbox" checked={allowOutbound} onChange={(event) => setAllowOutbound(event.target.checked)} />同意将本次研究问题发送给已配置模型；请先核对来源外发授权。</label></div>}
            <div className="actionRow">
              {(["start", "pause", "resume", "cancel"] as const).map((action) => <button key={action} type="button" disabled={!can(action) || (action === "start" && (!modelVersion.trim() || !allowOutbound))} onClick={() => void run(async () => { await post(`${base}/${encodeURIComponent(taskId)}/${action}`, action === "start" ? { model_version: modelVersion.trim(), allow_question_outbound: allowOutbound } : {}); })}>{ { start: "开始研究", pause: "暂停", resume: "恢复", cancel: "取消" }[action] }</button>)}
            </div>
            {activeJob && <p className="muted">运行任务：{activeJob}</p>}
            {pendingReview && <form className="reviewForm" onSubmit={(event) => { event.preventDefault(); void run(async () => { await post(`${base}/${encodeURIComponent(taskId)}/human-reviews/${encodeURIComponent(pendingReview.id)}/resolve`, { note: reviewNote.trim() }); setReviewNote(""); }); }}><h4>待人工审核 · {pendingReview.reason_code}</h4><p>中断阶段：{pendingReview.interrupted_stage} · 恢复阶段：{pendingReview.resume_stage}</p><label htmlFor="review-note">审核说明</label><textarea id="review-note" required maxLength={2000} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} /><button disabled={!can("resolve_review") || !reviewNote.trim()}>提交审核并继续</button></form>}
          </section>
          <nav className="researchTabs" aria-label="研究详情">{tabs.map((name) => <button type="button" key={name} aria-current={tab === name ? "page" : undefined} onClick={() => setTab(name)}>{name}</button>)}</nav>
          <section className="panel tabPanel" aria-label={tab}>
            {tab === "Summary" && <><h3>研究概览</h3>{detail ? <><p>子问题 {detail.subquestions.length} · Claim {detail.claims.length} · 审计 {detail.audits.length} · 争议 {detail.disputes.length}</p>{detail.subquestions.map((row) => <Item key={row.sequence_no} title={`子问题 ${row.sequence_no}`}><p>{row.question}</p></Item>)}{detail.stop_evaluations.map((row) => <Item key={row.id} title={`第 ${row.round_no} 轮停止判定：${row.decision}`}><p>{row.reason_code}</p></Item>)}{detail.human_reviews.map((row) => <Item key={row.id} title={`人工审核：${row.status}`}><p>{row.reason_code} · {row.resolution_note || "待处理"}</p></Item>)}</> : <Empty>正在读取研究详情。</Empty>}</>}
            {tab === "Claims" && <><h3>Claims 与审计</h3>{claimed.length ? claimed.map((claim) => <Item key={claim.id} title={`${claim.claim_type} · ${claim.agent_role}`}><p>{claim.assertion_text}</p><p className="muted">{claim.id} · 状态 {claim.status} · 审计 {claim.audit_status}{claim.parent_claim_id && ` · 修订自 ${claim.parent_claim_id}`}</p><p>{claim.rationale_summary}</p><RefList refs={claim.evidence} />{auditFor(claim.id).map((audit) => <div className="timelineStep" key={audit.id}><strong>审计 {audit.sequence_no} · {audit.stage} · {audit.verdict}</strong><p>{audit.rationale_summary}</p><RefList refs={audit.evidence} /></div>)}</Item>) : <Empty>尚无 Claim。首轮草稿会出现在这里，只有 Report 中的内容才是最终报告。</Empty>}</>}
            {tab === "Debate" && <><div className="panelHead"><h3>完整辩论时间线</h3><div className="viewSwitch"><button className={view === "round" ? "selected" : ""} onClick={() => setView("round")}>Round View</button><button className={view === "claim" ? "selected" : ""} onClick={() => setView("claim")}>Claim View</button></div></div>{!detail?.debate.critiques.length ? <Empty>尚无质疑与反驳记录。</Empty> : view === "claim" ? claimed.filter((claim) => critiqueFor(claim.id).length).map((claim) => <Item key={claim.id} title={claim.assertion_text}>{critiqueFor(claim.id).map((critique) => <DebateChain key={critique.id} critique={critique} detail={detail!} />)}</Item>) : [...new Set(detail.debate.rebuttals.map((row) => row.round_no).concat(detail.agent_runs.map((row) => row.round_no)))].sort((a, b) => a - b).map((round) => <Item key={round} title={`第 ${round} 轮`}>{detail.debate.critiques.filter((critique) => detail.agent_runs.find((run) => run.id === critique.agent_run_id)?.round_no === round).map((critique) => <DebateChain key={critique.id} critique={critique} detail={detail} />)}</Item>)}</>}
            {tab === "Evidence" && <><h3>证据引用</h3>{detail?.evidence.length ? detail.evidence.map((ref) => <Item key={`${ref.evidence_id}:${ref.revision_no}`} title={`${ref.evidence_id} · 修订 ${ref.revision_no}`}><p className="muted">引用于 {claimed.filter((claim) => claim.evidence.some((item) => item.evidence_id === ref.evidence_id && item.revision_no === ref.revision_no)).length} 条 Claim。引用详情见最终报告。</p></Item>) : <Empty>尚无证据引用。</Empty>}</>}
            {tab === "Disputes" && <><h3>争议与证据缺口</h3>{detail?.disputes.map((row) => <Item key={row.id} title={`${row.status} · ${row.reason_code}`}><p>{row.rationale_summary}</p><p className="muted">Claim {row.target_claim_id}{row.competing_claim_id && ` · 对立 ${row.competing_claim_id}`}</p><strong>支持证据</strong><RefList refs={row.supporting_evidence} /><strong>反对证据</strong><RefList refs={row.opposing_evidence} /></Item>)}{detail?.evidence_gaps.map((row) => <Item key={row.id} title={`证据缺口 · ${row.status}`}><p>{row.rationale_summary}</p><p className="muted">{row.reason_code} · Claim {row.claim_id}</p><RefList refs={row.evidence} /></Item>)}{!detail?.disputes.length && !detail?.evidence_gaps.length && <Empty>尚无争议或证据缺口。</Empty>}</>}
            {tab === "Report" && <><h3>最终报告</h3>{!report ? <Empty>最终报告尚未生成。首轮待审草稿请在 Claims 查看，不作为最终结论。</Empty> : <><p className="muted">版本 {report.schema_version} · 内容摘要 {report.content_hash}</p><div className="reportCounts">{Object.entries(report.counts).map(([key, count]) => <span key={key}>{key}：{count}</span>)}</div>{Object.entries(report.sections).map(([section, findings]) => <div key={section}><h4>{section}</h4>{findings.length ? findings.map((finding, index) => <Item key={`${section}:${index}`} title={`${finding.claim_type} · ${finding.audit_verdict}`}><p>{finding.assertion_text}</p><p>{finding.audit_rationale}</p><p className="muted">依据：{finding.reason_type} · {finding.agent_role}</p>{finding.evidence.map((evidence) => <blockquote key={`${evidence.evidence_id}:${evidence.evidence_revision_no}`}><strong>{evidence.source_title}</strong>：{evidence.quote_text}<small>{evidence.evidence_id} · 修订 {evidence.evidence_revision_no}</small></blockquote>)}</Item>) : <p className="muted">无</p>}</div>)}<p>未纳入 Claim：{report.excluded_claim_count} · 开放争议：{report.open_disputes.length} · 未解决缺口：{report.unresolved_gaps.length}</p><div className="exportRow">{(["markdown", "docx"] as const).map((format) => <div key={format}><button disabled={!can("export")} onClick={() => void run(async () => { await post(`${base}/${encodeURIComponent(taskId)}/exports/${format}`); })}>生成 {format.toUpperCase()}</button><span>{exports[format]?.status || "尚未生成"}</span>{exports[format]?.status === "COMPLETED" && exports[format]?.download_url && <a href={exports[format]!.download_url!}>下载 {format.toUpperCase()}</a>}</div>)}</div></>}</>}
          </section>
        </>}
      </div>
    </div>}
  </section>;
}

function DebateChain({ critique, detail }: { critique: Critique; detail: Detail }) {
  const requests = detail.debate.evidence_requests.filter((row) => row.critique_id === critique.id);
  const rebuttals = detail.debate.rebuttals.filter((row) => row.critique_id === critique.id);
  return <div className="debateChain"><div className="timelineStep"><strong>质疑 · {critique.issue_type}</strong><p>{critique.rationale_summary}</p><small>针对 {critique.target_claim_id}</small></div>{requests.map((row) => <div className="timelineStep" key={row.id}><strong>补证请求 · {row.status}</strong><p>{row.query_text}</p><small>检索结果 {row.result_count}</small><RefList refs={detail.debate.retrievals.filter((item) => item.request_id === row.id).map((item) => item.evidence)} /></div>)}{rebuttals.map((row) => <div className="timelineStep" key={row.id}><strong>第 {row.round_no} 轮反驳 · {row.action}</strong><p>{row.rationale_summary}</p>{row.revised_claim_id && <><small>修订 Claim {row.revised_claim_id}</small>{detail.audits.filter((audit) => audit.claim_id === row.revised_claim_id).map((audit) => <p key={audit.id}>复审 {audit.stage}：{audit.verdict} · {audit.rationale_summary}</p>)}</>}</div>)}</div>;
}
