/** Browser flow for the research workspace, using installed Edge and a local fake API. */
import assert from "node:assert/strict";
import { Cdp, connect, sleep, until } from "./research_browser_driver.mjs";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { extname, join, resolve } from "node:path";

const dist = resolve(import.meta.dirname, "..", "dist");
const edge = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const profile = await mkdtemp(join(tmpdir(), "tcm-research-browser-"));
const state = { session: false, task: null, exported: false, review: "PENDING", requests: [] };
const taskId = "RT-browser-test";
const jobId = "JOB-browser-test";
const sourceId = "SRC-browser-test";
const evidence = { evidence_id: "EV-browser-test", revision_no: 1 };
const claim = { id: "CLM-original", parent_claim_id: null, agent_run_id: "RUN-1", agent_role: "researcher", claim_type: "THEORY", assertion_text: "首轮待审草稿", rationale_summary: "原文支持", status: "REVISED", audit_status: "AUDITED", evidence: [evidence] };
const revised = { ...claim, id: "CLM-revised", parent_claim_id: claim.id, assertion_text: "修订后的主张", status: "ACTIVE" };
const detail = () => ({
  task_id: taskId, subquestions: [{ sequence_no: 1, question: "如何解释原文？" }], evidence: [evidence],
  agent_runs: [{ id: "RUN-1", role: "researcher", round_no: 1, status: "COMPLETED", model_version: "siliconflow/test" }],
  claims: [claim, revised], audits: [{ id: "AUD-1", claim_id: revised.id, sequence_no: 1, stage: "SEMANTIC", verdict: "SUPPORTED", rationale_summary: "修订后已复审", evidence: [evidence] }],
  canonical_claims: [],
  debate: { critiques: [{ id: "CRT-1", target_claim_id: claim.id, agent_run_id: "RUN-1", issue_type: "OVERCLAIM", rationale_summary: "质疑范围过宽", status: "ANSWERED" }],
    evidence_requests: [{ id: "REQ-1", critique_id: "CRT-1", query_text: "补充原文", status: "COMPLETED", result_count: 1 }],
    retrievals: [{ request_id: "REQ-1", evidence, rank: 1, channels: ["exact"] }],
    rebuttals: [{ id: "REB-1", critique_id: "CRT-1", round_no: 1, action: "REVISE", rationale_summary: "反驳并收窄表述", revised_claim_id: revised.id }] },
  disputes: [{ id: "DSP-1", target_claim_id: claim.id, competing_claim_id: revised.id, reason_code: "INTERPRETATION", rationale_summary: "解释仍有争议", status: "OPEN", supporting_evidence: [evidence], opposing_evidence: [] }],
  evidence_gaps: [], stop_evaluations: [{ id: "STP-1", round_no: 1, decision: "WAITING_HUMAN", reason_code: "MANDATORY_REVIEW" }],
  human_reviews: [{ id: "HREV-1", status: state.review, reason_code: "MANDATORY_REVIEW", interrupted_stage: "STOP_EVALUATION", resume_stage: "STOP_EVALUATION", resolution_note: state.review === "RESOLVED" ? "审核完成" : null }],
});
const report = { task_id: taskId, schema_version: "1", content_hash: "test-hash", question: "太阳病的脉象是什么？", counts: { SUPPORTED: 1 },
  sections: { supported: [{ assertion_text: revised.assertion_text, claim_type: "THEORY", agent_role: "researcher", audit_verdict: "SUPPORTED", audit_rationale: "修订后已复审", reason_type: "AUDIT", evidence: [{ evidence_id: evidence.evidence_id, evidence_revision_no: 1, source_title: "测试来源", quote_text: "太阳之为病", citation_locator: {} }] }] },
  open_disputes: [], unresolved_gaps: [], excluded_claim_count: 1 };

function json(res, status, body, extra = {}) {
  res.writeHead(status, { "Content-Type": "application/json", ...extra });
  res.end(JSON.stringify(body));
}
function currentTask() { return state.task && { ...state.task }; }
const openStreams = new Set();
const server = createServer(async (req, res) => {
  const path = new URL(req.url, "http://127.0.0.1").pathname;
  const body = await new Promise((done) => {
    if (req.method === "GET") return done({});
    let raw = ""; req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => { try { done(JSON.parse(raw || "{}")); } catch { done({}); } });
  });
  if (path.startsWith("/api/")) {
    state.requests.push(`${req.method} ${path}`);
    if (req.method === "POST" && path !== "/api/v1/local-session/bootstrap") {
      assert.equal(req.headers["x-csrf-token"], "browser-csrf");
      assert.ok(req.headers["idempotency-key"]);
    }
    if (path === "/api/v1/system/health") return json(res, 200, { state: "READY", database: "ok", schema: "ok", blob_store: "ok", preview_corpus: "none" });
    if (path === "/api/v1/local-session" && req.method === "GET") return json(res, state.session ? 200 : 401, state.session ? { session_id: "LS-browser", csrf_token: null } : { detail: "No session" });
    if (path === "/api/v1/local-session/bootstrap") {
      assert.equal(body.bootstrap_secret, "browser-secret"); state.session = true;
      return json(res, 200, { session_id: "LS-browser", csrf_token: "browser-csrf" }, { "Set-Cookie": "local_session=fake; Path=/api/v1; HttpOnly; SameSite=Strict" });
    }
    if (!state.session) return json(res, 401, { detail: "No session" });
    if (path === "/api/v1/knowledge/sources") return json(res, 200, [{ source_id: sourceId, title: "测试来源", status: "PUBLISHED", data_level: "PUBLIC" }]);
    if (path === "/api/v1/research/tasks" && req.method === "GET") return json(res, 200, state.task ? [currentTask()] : []);
    if (path === "/api/v1/research/tasks" && req.method === "POST") {
      assert.equal(body.question, "太阳病的脉象是什么？"); assert.deepEqual(body.source_ids, [sourceId]);
      state.task = { task_id: taskId, question: body.question, status: "CREATED", control_state: "ACTIVE", source_ids: body.source_ids, allowed_actions: ["start", "cancel"], job_id: null, report_available: false };
      return json(res, 201, currentTask());
    }
    if (path === `/api/v1/research/tasks/${taskId}`) return json(res, 200, currentTask());
    if (path === `/api/v1/research/tasks/${taskId}/details`) return json(res, 200, state.task.status === "CREATED" ? { ...detail(), claims: [], audits: [], debate: { critiques: [], evidence_requests: [], retrievals: [], rebuttals: [] }, evidence: [], disputes: [], human_reviews: [] } : detail());
    if (path === `/api/v1/research/tasks/${taskId}/events`) {
      res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store" });
      res.write(`event: snapshot\ndata: {"task_id":"${taskId}"}\n\n`);
      openStreams.add(res); req.on("close", () => openStreams.delete(res)); return;
    }
    if (path === `/api/v1/research/tasks/${taskId}/start`) {
      assert.equal(body.model_version, "siliconflow/test"); assert.equal(body.allow_question_outbound, true);
      Object.assign(state.task, { status: "WAITING_HUMAN", job_id: jobId, allowed_actions: ["resolve_review"] });
      return json(res, 202, { job_id: jobId, status: "PENDING" });
    }
    if (path === `/api/v1/jobs/${jobId}`) return json(res, 200, { job_id: jobId, status: "COMPLETED", attempts: 1, max_attempts: 3 });
    if (path === `/api/v1/research/tasks/${taskId}/human-reviews/HREV-1/resolve`) {
      assert.equal(body.note, "审核完成"); state.review = "RESOLVED";
      Object.assign(state.task, { status: "COMPLETED", allowed_actions: ["export"], report_available: true });
      return json(res, 200, currentTask());
    }
    if (path === `/api/v1/research/tasks/${taskId}/report`) return json(res, 200, report);
    if (path === `/api/v1/research/tasks/${taskId}/exports/markdown` && req.method === "POST") { state.exported = true; return json(res, 202, { job_id: "JOB-export" }); }
    if (path === `/api/v1/research/tasks/${taskId}/exports/markdown` && req.method === "GET") return state.exported ? json(res, 200, { file_format: "markdown", status: "COMPLETED", job_id: "JOB-export", download_url: `/api/v1/research/tasks/${taskId}/exports/markdown/download` }) : json(res, 404, { detail: "No export" });
    if (path === `/api/v1/research/tasks/${taskId}/exports/docx`) return json(res, 404, { detail: "No export" });
    if (path === `/api/v1/research/tasks/${taskId}/exports/markdown/download`) { res.writeHead(200, { "Content-Type": "text/markdown" }); return res.end("# 测试报告"); }
    return json(res, 404, { detail: `Unknown ${path}` });
  }
  const file = path === "/" ? join(dist, "index.html") : resolve(dist, `.${path}`);
  if (!file.startsWith(dist)) { res.writeHead(403); return res.end(); }
  try {
    const contents = await readFile(file);
    res.writeHead(200, { "Content-Type": ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css" })[extname(file)] || "application/octet-stream" });
    res.end(contents);
  } catch { res.writeHead(404); res.end(); }
});

let browser;
let cdp;
try {
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  const pageUrl = `http://127.0.0.1:${server.address().port}/`;
  browser = spawn(edge, ["--headless=new", "--remote-debugging-port=9224", "--remote-allow-origins=*", `--user-data-dir=${profile}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
  await connect(9224);
  const target = await (await fetch(`http://127.0.0.1:9224/json/new?${encodeURIComponent(pageUrl)}`, { method: "PUT" })).json();
  cdp = new Cdp(target.webSocketDebuggerUrl);
  await cdp.send("Runtime.enable");
  const text = () => cdp.eval("document.body?.innerText || ''");
  const click = (label) => cdp.eval(`(() => { const button = [...document.querySelectorAll('button')].find(el => el.textContent.trim() === ${JSON.stringify(label)}); if (!button || button.disabled) throw new Error('Button unavailable: ${label}'); button.click(); return true; })()`);
  const fill = (selector, value) => cdp.eval(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) throw new Error('Missing: ${selector}'); const setter = Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set; setter.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  await until(async () => (await text()).includes("连接本地研究会话"), "bootstrap form");
  await fill("#bootstrap-secret", "browser-secret"); await click("连接");
  await until(async () => (await text()).includes("创建研究任务"), "research form");
  await fill("#research-question", "太阳病的脉象是什么？");
  await cdp.eval("document.querySelector('.sourceChoices input[type=checkbox]').click()");
  await click("创建研究任务");
  await until(async () => (await text()).includes(taskId), "created task");
  await fill("#model-version", "siliconflow/test");
  await cdp.eval("document.querySelector('.startForm input[type=checkbox]').click()");
  await click("开始研究");
  await until(async () => (await text()).includes("等待人工审核"), "human review");
  assert.equal(await cdp.eval("[...document.querySelectorAll('.actionRow button')].find(el => el.textContent.trim() === '暂停')?.disabled"), true);
  await click("Report"); assert.match(await text(), /最终报告尚未生成/);
  await click("Claims"); assert.match(await text(), /首轮待审草稿/);
  await click("Debate"); assert.match(await text(), /质疑范围过宽/);
  assert.match(await text(), /反驳并收窄表述/);
  assert.match(await text(), /修订后已复审/);
  await click("Claim View"); assert.match(await text(), /质疑范围过宽/);
  await click("Round View"); assert.match(await text(), /第 1 轮/);
  await click("Evidence"); assert.match(await text(), /EV-browser-test/);
  await click("Disputes"); assert.match(await text(), /解释仍有争议/);
  await click("Summary"); assert.match(await text(), /子问题 1/);
  await fill("#review-note", "审核完成"); await click("提交审核并继续");
  await until(async () => (await text()).includes("COMPLETED"), "completed task");
  await click("Report"); await until(async () => (await text()).includes("修订后的主张"), "final report");
  await click("生成 MARKDOWN");
  await until(async () => (await text()).includes("下载 MARKDOWN"), "download link");
  assert.equal(await cdp.eval("document.querySelector('.exportRow a')?.getAttribute('href')"), `/api/v1/research/tasks/${taskId}/exports/markdown/download`);
  const download = await fetch(new URL(`/api/v1/research/tasks/${taskId}/exports/markdown/download`, pageUrl));
  assert.equal(download.status, 200);
  assert.match(await download.text(), /测试报告/);
  assert.ok(state.requests.includes(`POST /api/v1/research/tasks/${taskId}/human-reviews/HREV-1/resolve`));
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 1, mobile: true });
  await sleep(200);
  assert.equal(await cdp.eval("document.documentElement.scrollWidth <= window.innerWidth + 1"), true, "mobile page must not overflow horizontally");
  console.log("Browser flow passed: create → review → six tabs / debate views → report export and download; mobile width checked.");
} finally {
  cdp?.close();
  if (browser) {
    browser.kill();
    await new Promise((done) => { if (browser.exitCode !== null) done(); else browser.once("exit", done); });
  }
  for (const stream of openStreams) stream.end();
  server.close();
  const tempRoot = resolve(tmpdir());
  const profilePath = resolve(profile);
  if (profilePath.startsWith(`${tempRoot}\\`) && profilePath.split("\\").at(-1).startsWith("tcm-research-browser-")) {
    try { await rm(profilePath, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); }
    catch { console.warn(`Temporary Edge profile could not be removed: ${profilePath}`); }
  }
}
