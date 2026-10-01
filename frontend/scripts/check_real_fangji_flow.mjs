/** Real Fangji material and configured cloud models only; resumes persisted work. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { Cdp, connect, until, sleep } from "./research_browser_driver.mjs";

const origin = "http://127.0.0.1:18067";
const source = "SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350";
const oldTask = "RT-01a0f690-2bea-7fc1-aa32-347c177acf1b";
const full = process.env.TCM_REAL_FANGJI_FULL === "1";
const artifacts = resolve(import.meta.dirname, full ? "../../docs/acceptance-artifacts/full-fangji-research" : "../../docs/acceptance-artifacts/real-fangji-flow");
await mkdir(artifacts, { recursive: true });
const browserPort = Number(process.env.TCM_REAL_BROWSER_PORT || 19281);
const profile = await mkdtemp(join(tmpdir(), "tcm-real-fangji-"));
const browser = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", ["--headless=new", "--no-first-run", "--no-default-browser-check", `--user-data-dir=${profile}`, `--remote-debugging-port=${browserPort}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
let page;
let previousResult = {};
try { previousResult = JSON.parse(await readFile(join(artifacts, "result.json"), "utf8")); } catch { /* first real run */ }
const state = { ...previousResult, failure: undefined, last_page: undefined, origin, source, old_task: oldTask, model_doubles: false, verified_at: new Date().toISOString() };
const save = () => writeFile(join(artifacts, "result.json"), JSON.stringify(state, null, 2));
const apiSession = await fetch(`${origin}/api/v1/local-session/development`, { method: "POST", headers: { Origin: origin } });
assert.ok(apiSession.ok);
const apiCookie = apiSession.headers.get("set-cookie").split(";")[0];
const get = async path => {
  const response = await fetch(origin + path, { headers: { Cookie: apiCookie }, signal: AbortSignal.timeout(60000) });
  const body = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(body));
  return body;
};
const text = () => page.eval("document.body?.innerText || ''");
const click = async label => {
  const expr = `[...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)} && !b.disabled)`;
  await until(() => page.eval(`!!(${expr})`), `button ${label}`, 60000);
  await page.eval(`(${expr}).click()`);
};
const fill = async (selector, value) => {
  await page.eval(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); if(!el)throw new Error('Missing '+${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)}); el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true})); })()`);
};
const screenshot = async name => {
  const shot = await page.send("Page.captureScreenshot", { format: "png" });
  await writeFile(join(artifacts, name), Buffer.from(shot.data, "base64"));
};
try {
  await connect(browserPort);
  const target = await (await fetch(`http://127.0.0.1:${browserPort}/json/new?${encodeURIComponent(`${origin}/?workspace=knowledge&source=${source}`)}`, { method: "PUT" })).json();
  page = new Cdp(target.webSocketDebuggerUrl);
  await page.send("Emulation.setDeviceMetricsOverride", { width: 1400, height: 1000, deviceScaleFactor: 1, mobile: false });
  await until(() => page.eval("document.body?.innerText.includes('本机工作区已连接')"), "session");
  state.configuration = await get("/api/v1/knowledge/publication-config");
  assert.equal(state.configuration.mode, "CLOUD_ALLOWED");
  assert.equal(state.configuration.configuration.strategy, "hybrid-rrf-v1");
  const sourceDetail = await get(`/api/v1/knowledge/sources/${source}`);
  assert.equal(sourceDetail.outbound_authorized, true);
  assert.equal(sourceDetail.data_level, "PUBLIC");
  state.source_revision = 2;
  const old = await get(`/api/v1/research/tasks/${oldTask}`);
  state.question = full ? "依据所选完整《方剂学》修订2的全部已核对材料，比较麻黄汤与大青龙汤的组成、证候和配伍，重点研究为何倍用麻黄。必须检索总论剂量说明、教材鉴别、柯琴方论，以及小青龙汤、麻杏甘石汤、麻黄加术汤等对照材料，不限于两方本方段落。区分三两/六两与9g/12g，比较教材与方论的不同解释，并检验发汗之力尤峻是否足以支持定量或因果结论。各角色独立论证，质疑角色审查问题覆盖、相反解释和证据边界，回应角色逐项回应实际质疑；不编造分歧。结论注明不足，仅作理论研究。" : old.question;
  if (process.env.TCM_REAL_FANGJI_EXPORT_ONLY !== "1") {
  await click("3 · 质量与版本发布");
  await until(() => page.eval("!!document.querySelector('.kwPublicationFlow')"), "publication preview");
  state.preview = await get("/api/v1/knowledge/publication-preview");
  await click("加入知识库并构建索引");
  await until(async () => {
    const versions = await get("/api/v1/knowledge/versions");
    const newest = await get(`/api/v1/knowledge/versions/${versions[0].version_id}`);
    state.version = newest;
    return newest.item_counts.evidence_revision === state.preview.item_counts.evidence_revision
      && newest.item_counts.formula_revision === state.preview.item_counts.formula_revision
      && newest.publication_job != null && newest.index_builds.length > 0
      && newest.index_builds.every(row => row.vector_status !== "NOT_APPLICABLE");
  }, "real index build queued", 60000);
  await page.send("Page.reload");
  await until(() => page.eval("!!document.querySelector('.kwPublicationFlow') && document.querySelector('.kwVersions button.selected') != null"), "refresh restores publication panel");
  await until(async () => {
    state.version = await get(`/api/v1/knowledge/versions/${state.version.version_id}`);
    const job = state.version.publication_job;
    if (job?.status === "FAILED") throw new Error(`Cloud index failed: ${JSON.stringify(await get('/api/v1/jobs/' + job.job_id))}`);
    return state.version.index_builds.some(row => row.status === "READY");
  }, "real cloud vector index", 600000);
  assert.ok(state.version.index_builds.some(row => row.vector_status === "READY"));
  state.ready_before_activation = state.version.active === false;
  await screenshot("cloud-index-ready.png");
  if (!state.version.active) await click("激活为当前检索版本");
  else await click("前往知识检索");
  await until(() => page.eval("!!document.querySelector('#knowledge-query')"), "search workspace", 60000);
  await until(() => page.eval("document.body.innerText.includes('云端语义检索与重排已就绪')"), "cloud capability shown");
  await page.eval("document.querySelector('.searchPanel input[type=checkbox]').click()");
  await fill("#knowledge-query", "大青龙汤为何倍用麻黄，如何兼顾表寒与里热？");
  await click("检索证据");
  await until(() => page.eval("!!document.querySelector('.retrievalStatus')"), "real semantic search", 60000);
  state.search_ui = await page.eval("document.querySelector('.searchPanel').innerText");
  assert.match(state.search_ui, /混合检索/);
  assert.match(state.search_ui, /语义检索/);
  assert.match(state.search_ui, /云端重排/);
  state.search_results = await page.eval("[...document.querySelectorAll('.resultCard')].map(row=>row.innerText)");
  assert.match(state.search_results.join("\n"), /大青龙汤/);
  await screenshot("cloud-search.png");
  console.log(JSON.stringify({ stage: "cloud-search-passed", version: state.version.version_id }));
  await save();
  }

  await page.send("Page.navigate", { url: `${origin}/?workspace=research&source=${source}` });
  await until(() => page.eval("!!document.querySelector('#research-question')"), "research form", 60000);
  const tasks = await get("/api/v1/research/tasks");
  let task = tasks.find(row => row.task_id !== oldTask && row.question === state.question && row.status !== "CANCELLED");
  if (!task) {
    await fill("#research-question", state.question);
    await click("创建研究任务");
    await until(async () => {
      task = (await get("/api/v1/research/tasks")).find(row => row.task_id !== oldTask && row.question === state.question && row.status !== "CANCELLED");
      return !!task;
    }, "new continuation task");
  } else {
    await page.eval(`([...document.querySelectorAll('.taskList button')].find(b=>b.textContent.includes(${JSON.stringify(task.question)})) || [...document.querySelectorAll('button')].find(b=>b.textContent.includes(${JSON.stringify(task.question)}))).click()`);
  }
  state.task_id = task.task_id;
  await save();
  if (task.status === "CREATED") {
    await until(() => page.eval("!!document.querySelector('#model-version')"), "start configuration");
    await fill("#model-version", "siliconflow/deepseek-ai/DeepSeek-V3.2");
    await page.eval("document.querySelector('.startForm input[type=checkbox]').click()");
    await click("开始研究");
  }
  if (task.allowed_actions.includes("retry")) await click("重试失败步骤");
  console.log(JSON.stringify({ stage: "real-research-started", task_id: task.task_id }));
  let previous = "";
  const deadline = Date.now() + 3600000;
  while (Date.now() < deadline) {
    task = await get(`/api/v1/research/tasks/${state.task_id}`);
    state.task = task;
    if (task.status !== previous) { console.log(JSON.stringify({ stage: "research", status: task.status })); previous = task.status; await save(); }
    if (task.status === "COMPLETED") break;
    const job = task.job_id ? await get(`/api/v1/jobs/${task.job_id}`) : null;
    state.job = job;
    if (["FAILED", "CANCELLED", "WAITING_HUMAN"].includes(task.status) || job?.status === "FAILED") throw new Error(`Real research needs attention: ${JSON.stringify({ task, job })}`);
    await sleep(3000);
  }
  assert.equal(task.status, "COMPLETED");
  state.details = await get(`/api/v1/research/tasks/${state.task_id}/details`);
  state.report = await get(`/api/v1/research/tasks/${state.task_id}/report`);
  assert.ok(state.details.agent_runs.length > 0);
  if(full) assert.ok(state.details.evidence.length > 2, "Full-corpus research must retrieve beyond the two original excerpts");
  assert.ok(state.details.agent_runs.every(run => run.model_version === "siliconflow/deepseek-ai/DeepSeek-V3.2"));
  await until(() => page.eval("document.body.innerText.includes('研究完成') || document.body.innerText.includes('已完成')"), "completed research page", 30000);
  await screenshot("research-completed.png");
  await click("研究报告");
  await until(() => page.eval("!!document.querySelector('.exportRow')"), "report export controls");
  state.report_ui = await page.eval(`({ visibleConclusions: document.querySelectorAll('.reportConclusion').length, uniqueEvidence: document.querySelectorAll('.reportEvidence details').length, openEvidence: document.querySelectorAll('.reportEvidence details[open]').length })`);
  assert.equal(state.report_ui.openEvidence, 0);
  assert.ok(state.report_ui.visibleConclusions > 0);
  await screenshot("real-report.png");
  // Exports are existing task operations, and never rerun the completed model work.
  for (const format of ["markdown", "docx"]) {
    await click(format === "markdown" ? "生成 MARKDOWN" : "生成 DOCX");
    let exported;
    await until(async () => { try { exported = await get(`/api/v1/research/tasks/${state.task_id}/exports/${format}`); return exported.download_url != null; } catch (cause) { if (String(cause).includes("EXPORT_NOT_FOUND")) return false; throw cause; } }, `${format} export`, 60000);
    const downloaded = await page.eval(`fetch(${JSON.stringify(exported.download_url)}).then(async r=>{ if(!r.ok)throw new Error('download '+r.status); return Array.from(new Uint8Array(await r.arrayBuffer())); })`);
    await writeFile(join(artifacts, `fangji-report.${format === "markdown" ? "md" : "docx"}`), Buffer.from(downloaded));
  }
  state.completed = new Date().toISOString();
  await save();
  console.log(JSON.stringify({ stage: "real-flow-completed", task_id: state.task_id, artifacts }));
} catch (error) {
  state.failure = String(error); state.last_page = page ? await text().catch(() => "") : "";
  if (page) await screenshot("last-state.png").catch(() => {});
  await save();
  console.error(state.failure); process.exitCode = 1;
} finally { page?.close(); browser.kill(); }
