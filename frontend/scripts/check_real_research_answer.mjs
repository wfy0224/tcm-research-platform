/** Real uploaded corpus and real configured models; no business/model doubles. */
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const origin = "http://127.0.0.1:18067";
const directory = resolve(import.meta.dirname, "../../docs/acceptance-artifacts/real-research-answer");
await mkdir(directory, { recursive: true });
const question = "比较麻黄汤和大青龙汤，分析大青龙汤中麻黄用量为什么比麻黄汤多";
const source = "SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350";
const sessionResponse = await fetch(origin + "/api/v1/local-session/development", {
  method: "POST", headers: { Origin: origin },
});
assert.ok(sessionResponse.ok);
const cookie = sessionResponse.headers.get("set-cookie").split(";")[0];
const { csrf_token: csrf } = await sessionResponse.json();
async function api(path, body) {
  const response = await fetch(origin + path, {
    method: body === undefined ? "GET" : "POST",
    headers: { Cookie: cookie, Origin: origin, ...(body === undefined ? {} : {
      "Content-Type": "application/json", "X-CSRF-Token": csrf,
      "Idempotency-Key": crypto.randomUUID(),
    }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(60000),
  });
  const result = await response.json();
  assert.ok(response.ok, JSON.stringify(result));
  return result;
}
let state = {};
try { state = JSON.parse(await readFile(resolve(directory, "result.json"), "utf8")); } catch { /* first run */ }
const save = () => writeFile(resolve(directory, "result.json"), JSON.stringify(state, null, 2));
state.question = question;
state.source = source;
state.model_doubles = false;
state.verified_at = new Date().toISOString();
const base = "/api/v1/research/tasks";
if (!state.task_id) {
  const old = await api(base + "/RT-01a0f773-3445-7c68-bd35-6c56ba0761eb");
  if (old.status !== "CANCELLED" && old.allowed_actions.includes("cancel"))
    await api(base + "/" + old.task_id + "/cancel", {});
  const task = await api(base, { question, source_ids: [source] });
  state.task_id = task.task_id;
  await save();
}
let task = await api(base + "/" + state.task_id);
assert.equal(task.question, question);
if (task.job_id && task.allowed_actions.includes("retry")) {
  const job = await api("/api/v1/jobs/" + task.job_id);
  if (job.status === "FAILED") {
    state.retry_from = { task_id: task.task_id, job_id: task.job_id,
      task_status: task.status, previous_attempts: job.attempts };
    await save();
    task = await api(base + "/" + task.task_id + "/retry", {});
  }
}
if (task.status === "CREATED") {
  const capabilities = await api("/api/v1/research/capabilities");
  state.model = "siliconflow/deepseek-ai/DeepSeek-V3.2";
  assert.ok(capabilities.models.some(m => m.model_version === state.model));
  await api(base + "/" + state.task_id + "/start", {
    model_version: state.model, allow_question_outbound: true,
  });
}
let last = "";
for (;;) {
  task = await api(base + "/" + state.task_id);
  const [details, job] = await Promise.all([
    api(base + "/" + state.task_id + "/details"), api("/api/v1/jobs/" + task.job_id),
  ]);
  state.task = task;
  state.job = job;
  state.details = details;
  await save();
  const progress = JSON.stringify({ task_id: state.task_id, phase: task.status,
    job: job.status, evidence: details.evidence.length, claims: details.claims.length,
    audits: details.audits.filter(a => a.stage === "SEMANTIC").length,
    critiques: details.debate.critiques.length, rebuttals: details.debate.rebuttals.length,
    runs: details.agent_runs.map(r => `${r.role}:${r.status}`),
  });
  if (progress !== last) { console.log(progress); last = progress; }
  assert.notEqual(job.status, "FAILED", JSON.stringify(job));
  assert.notEqual(task.status, "CANCELLED");
  assert.notEqual(task.status, "WAITING_HUMAN");
  if (task.report_available) break;
  await new Promise(r => setTimeout(r, 5000));
}
const report = await api(base + "/" + state.task_id + "/report");
assert.equal(report.question, question);
assert.equal(report.schema_version, "research-report/v2");
assert.ok(report.answer?.paragraphs.length >= 1, "missing synthesized answer");
assert.ok(report.answer.review_summary.length > 0, "missing independent narrative review");
assert.ok(state.details.evidence.length > 2, "research must retrieve beyond original two citations");
assert.ok(state.details.agent_runs.some(r => r.role === "ReportWriter" && r.status === "COMPLETED"));
assert.ok(state.details.agent_runs.some(r => r.role === "ReportReviewer" && r.status === "COMPLETED"));
state.report = report;
await writeFile(resolve(directory, "report.json"), JSON.stringify(report, null, 2));
for (const format of ["markdown", "docx"]) {
  await api(base + "/" + state.task_id + "/exports/" + format, {});
  let exported;
  for (;;) {
    exported = await api(base + "/" + state.task_id + "/exports/" + format);
    assert.notEqual(exported.status, "FAILED");
    if (exported.download_url) break;
    await new Promise(r => setTimeout(r, 1500));
  }
  const downloaded = await fetch(origin + exported.download_url, { headers: { Cookie: cookie } });
  assert.ok(downloaded.ok);
  const bytes = Buffer.from(await downloaded.arrayBuffer());
  if (format === "markdown") assert.ok(bytes.toString("utf8").includes(report.answer.paragraphs[0].text));
  await writeFile(resolve(directory, format === "markdown" ? "report.md" : "report.docx"), bytes);
}
state.outcome = "COMPLETED_WITH_REVIEWED_NARRATIVE";
await save();
console.log(JSON.stringify({ outcome: state.outcome, task_id: state.task_id,
  answer: report.answer.paragraphs.map(p => p.text) }));
