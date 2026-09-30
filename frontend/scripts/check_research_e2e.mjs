/** Browser → real HTTP API → real Workers, using deterministic model doubles. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { createServer, request } from "node:http";
import { tmpdir } from "node:os";
import { extname, join, relative, resolve, sep } from "node:path";
import { createInterface } from "node:readline";
import { Cdp, connect, sleep, until } from "./research_browser_driver.mjs";

const dist = resolve(import.meta.dirname, "..", "dist");
const edge = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const pageUrl = "http://127.0.0.1:18064/";
const secret = randomBytes(32).toString("hex");
const prefix = `VIB-63 browser ${randomBytes(8).toString("hex")}`;
const profile = await mkdtemp(join(tmpdir(), "tcm-research-e2e-"));
const downloads = join(profile, "downloads");
const calls = [];
const events = new Set();
const upstreams = new Set();
let api, browser, cdp, taskId, ready;
let sequence = 0;
const pending = new Map();
let apiExited;
let resolveReady, rejectReady;
const apiReady = new Promise((done, fail) => { resolveReady = done; rejectReady = fail; });

function drive(action, format) {
  const id = ++sequence;
  return new Promise((done, fail) => {
    const timer = setTimeout(() => { pending.delete(id); fail(new Error(`Worker timed out: ${action}`)); }, 45000);
    pending.set(id, { done, fail, timer });
    api.stdin.write(JSON.stringify({ id, action, format }) + "\n");
  });
}

const server = createServer(async (req, res) => {
  const path = new URL(req.url, pageUrl).pathname;
  if (path.startsWith("/api/")) {
    calls.push(`${req.method} ${path}`);
    const upstream = request(`http://127.0.0.1:18063${req.url}`, {
      method: req.method, headers: { ...req.headers, host: "127.0.0.1:18063" },
    }, (response) => {
      res.writeHead(response.statusCode, response.headers);
      if (path.endsWith("/events")) {
        let tail = "";
        response.on("data", (chunk) => {
          const value = tail + chunk.toString();
          const lines = value.split("\n"); tail = lines.pop();
          for (const line of lines) if (line.startsWith("event: ")) events.add(line.slice(7).trim());
        });
      }
      response.pipe(res);
    });
    upstreams.add(upstream);
    upstream.on("close", () => upstreams.delete(upstream));
    upstream.on("error", () => { if (!res.headersSent) res.writeHead(502); res.end(); });
    res.on("close", () => upstream.destroy());
    req.pipe(upstream); return;
  }
  const file = path === "/" ? join(dist, "index.html") : resolve(dist, `.${path}`);
  const within = relative(dist, file);
  if (within.startsWith("..") || within.includes(`..${sep}`)) { res.writeHead(403); res.end(); return; }
  try {
    const contents = await readFile(file);
    res.writeHead(200, { "Content-Type": ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css" })[extname(file)] || "application/octet-stream" });
    res.end(contents);
  } catch { res.writeHead(404); res.end(); }
});

try {
  // Docker Desktop and the two existing test containers must already be running.
  // The separate forwarding container publishes only 127.0.0.1:18063.
  api = spawn("docker", ["exec", "-i", "-e", "PYTHONPATH=/workspace/backend/src",
    "-e", "TCM_E2E_DATABASE=tcm_vib60_test", "tcm-vib54-py", "python", "-u",
    "/workspace/backend/scripts/serve_research_e2e.py"], { windowsHide: true, stdio: ["pipe", "pipe", "inherit"] });
  apiExited = new Promise((done) => api.once("close", done));
  api.on("error", rejectReady);
  api.once("exit", (code) => {
    rejectReady(new Error(`API harness exited: ${code}`));
    for (const { fail, timer } of pending.values()) { clearTimeout(timer); fail(new Error(`API harness exited: ${code}`)); }
    pending.clear();
  });
  createInterface({ input: api.stdout }).on("line", (line) => {
    let message;
    try { message = JSON.parse(line); } catch { console.error(line); return; }
    if (message.ready) { ready = message; resolveReady(message); }
    const waiter = pending.get(message.id);
    if (waiter) {
      clearTimeout(waiter.timer); pending.delete(message.id);
      message.error ? waiter.fail(new Error(message.error)) : waiter.done(message);
    }
  });
  api.stdin.write(JSON.stringify({ secret, prefix }) + "\n");
  let readyTimer;
  try {
    await Promise.race([apiReady, new Promise((_, fail) => { readyTimer = setTimeout(() => fail(new Error("API harness did not start")), 20000); })]);
  } finally { clearTimeout(readyTimer); }
  assert.equal(ready.database, "tcm_vib60_test");
  await until(async () => {
    try { return (await fetch("http://127.0.0.1:18063/api/v1/system/health")).ok; }
    catch { return false; }
  }, "real API through tcm-vib63-forward (see README startup command)");
  await new Promise((done, fail) => { server.once("error", fail); server.listen(18064, "127.0.0.1", done); });
  browser = spawn(edge, ["--headless=new", "--remote-debugging-port=9225", "--remote-allow-origins=*", `--user-data-dir=${profile}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
  await connect(9225);
  const target = await (await fetch(`http://127.0.0.1:9225/json/new?${encodeURIComponent(pageUrl)}`, { method: "PUT" })).json();
  cdp = new Cdp(target.webSocketDebuggerUrl);
  await cdp.send("Runtime.enable");
  await cdp.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads });
  const text = () => cdp.eval("document.body?.innerText || ''");
  const click = async (label) => {
    await until(() => cdp.eval(`[...document.querySelectorAll('button')].some(el => el.textContent.trim() === ${JSON.stringify(label)} && !el.disabled)`), `enabled button: ${label}`);
    return cdp.eval(`(() => { const el = [...document.querySelectorAll('button')].find(el => el.textContent.trim() === ${JSON.stringify(label)}); if (!el || el.disabled) throw new Error('Button unavailable: ' + ${JSON.stringify(label)}); el.click(); })()`);
  };
  const fill = (selector, value) => cdp.eval(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) throw new Error('Missing field'); const setter = Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set; setter.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  const get = (path) => cdp.eval(`fetch(${JSON.stringify(path)}).then(async r => { if (!r.ok) throw new Error('API HTTP ' + r.status); return r.json(); })`);
  const buttonDisabled = (label) => cdp.eval(`[...document.querySelectorAll('.actionRow button')].find(el => el.textContent.trim() === ${JSON.stringify(label)})?.disabled`);

  await until(async () => (await text()).includes("连接本地研究会话"), "bootstrap form");
  await fill("#bootstrap-secret", secret); await click("连接");
  await until(async () => (await text()).includes("创建研究任务"), "research form");
  await fill("#research-question", ready.question);
  await until(() => cdp.eval(`!!document.querySelector('.sourceChoices input[value="${ready.source_id}"]')`), "fixture source choice");
  await cdp.eval(`document.querySelector('.sourceChoices input[value="${ready.source_id}"]').click()`);
  await click("创建研究任务");
  await until(async () => {
    taskId = await cdp.eval("document.querySelector('.taskOverview .sectionLabel')?.textContent");
    return taskId?.startsWith("RT-");
  }, "browser-created task");
  const base = `/api/v1/research/tasks/${taskId}`;
  assert.deepEqual((await get(base)).source_ids, [ready.source_id]);
  assert.equal(await buttonDisabled("暂停"), true);
  await fill("#model-version", ready.model_version);
  await cdp.eval("document.querySelector('.startForm input[type=checkbox]').click()");
  await click("开始研究");
  await until(async () => (await get(base)).status === "PLANNING" && !(await buttonDisabled("暂停")), "started task");
  await click("暂停");
  await until(async () => (await get(base)).control_state === "PAUSED" && !(await buttonDisabled("恢复")), "pause before Worker lease");
  assert.equal(await buttonDisabled("暂停"), true);
  await click("恢复");
  await until(async () => (await get(base)).control_state === "ACTIVE" && !(await buttonDisabled("暂停")), "resume before Worker lease");
  assert.equal((await drive("research")).status, "WAITING_HUMAN");
  await until(async () => (await text()).includes("等待人工审核") && (await text()).includes("提交审核并继续"), "human review from real Worker");
  assert.equal(await buttonDisabled("暂停"), true);
  assert.deepEqual((await get(base)).allowed_actions, ["resolve_review"]);
  const before = await get(`${base}/details`);
  const firstRuns = before.agent_runs.filter(run => run.round_no === 1).map(run => run.id).sort();
  assert.equal(firstRuns.length, 3);
  const revisedIds = before.claims.filter(claim => claim.parent_claim_id).map(claim => claim.id);
  assert.ok(revisedIds.length);
  assert.ok(before.audits.some(audit => revisedIds.includes(audit.claim_id) && audit.stage === "SEMANTIC"));
  assert.ok(before.debate.retrievals.length);
  assert.ok(before.disputes.length || before.evidence_gaps.length);
  await click("Report"); assert.match(await text(), /最终报告尚未生成/);
  await click("Claims"); assert.match(await text(), /sample finding/);
  await click("Debate"); assert.match(await text(), /需限定断言/);
  assert.match(await text(), /接受限定意见/);
  assert.match(await text(), /复审 SEMANTIC/);
  await click("Claim View"); assert.match(await text(), /需限定断言/);
  await click("Round View"); assert.match(await text(), /第 2 轮/);
  await click("Evidence"); assert.ok((await text()).includes(before.evidence[0].evidence_id));
  await click("Disputes"); assert.match(await text(), /OPEN/);
  await click("Summary"); assert.match(await text(), /子问题 1/);
  await fill("#review-note", "浏览器实链路审核完成"); await click("提交审核并继续");
  await until(async () => (await get(base)).status === "STOP_EVALUATION", "review resolution persisted");
  assert.equal((await drive("research")).status, "COMPLETED");
  await until(async () => (await text()).includes("COMPLETED") && await buttonDisabled("开始研究"), "completed task refresh");
  const after = await get(`${base}/details`);
  assert.deepEqual(after.agent_runs.filter(run => run.round_no === 1).map(run => run.id).sort(), firstRuns, "review resume must preserve first-round runs");
  assert.equal(after.human_reviews[0].status, "RESOLVED");
  assert.equal(after.human_reviews[0].resolution_note, "浏览器实链路审核完成");
  await click("Report");
  await until(async () => (await text()).includes(ready.quote), "report with original evidence");
  for (const format of ["markdown", "docx"]) {
    await until(() => cdp.eval(`[...document.querySelectorAll('button')].some(el => el.textContent.trim() === ${JSON.stringify(`生成 ${format.toUpperCase()}`)} && !el.disabled)`), "export enabled");
    await click(`生成 ${format.toUpperCase()}`);
    await until(async () => {
      if (!calls.includes(`POST ${base}/exports/${format}`)) return false;
      try { return (await get(`${base}/exports/${format}`)).status === "PENDING"; }
      catch (error) { if (error.message.includes("API HTTP 404")) return false; throw error; }
    }, "export queued");
    await drive("export", format);
    await until(async () => (await text()).includes(`下载 ${format.toUpperCase()}`), "completed export download link");
    const href = `${base}/exports/${format}/download`;
    const downloaded = await cdp.eval(`fetch(${JSON.stringify(href)}).then(async r => { if (!r.ok) throw new Error('Download HTTP ' + r.status); const bytes = new Uint8Array(await r.arrayBuffer()); return { type: r.headers.get('content-type'), data: btoa(String.fromCharCode(...bytes)) }; })`);
    const bytes = Buffer.from(downloaded.data, "base64");
    assert.ok(bytes.length > 100);
    if (format === "markdown") assert.ok(bytes.toString().includes(ready.quote));
    else { assert.equal(bytes.subarray(0, 2).toString(), "PK"); assert.ok(bytes.includes(Buffer.from("word/document.xml"))); }
    const previous = new Set(await readdir(downloads).catch(() => []));
    await cdp.eval(`document.querySelector('a[href="${href}"]').click()`);
    let filename;
    await until(async () => {
      filename = (await readdir(downloads).catch(() => [])).find(name => !previous.has(name) && !name.endsWith(".crdownload"));
      return !!filename;
    }, "browser file download");
    assert.deepEqual(await readFile(join(downloads, filename)), bytes);
  }
  assert.ok(events.has("snapshot"), "browser must receive real SSE snapshot");
  assert.ok(events.has("research_task.waiting_human"), "browser must receive persisted human-review event");
  assert.ok(events.has("research_task.report_saved"), "browser must receive completion report event");
  await cdp.send("Page.reload");
  await until(async () => (await text()).includes(ready.question), "session and persisted task after reload");
  await cdp.eval(`(() => { const el = [...document.querySelectorAll('.taskList button')].find(el => el.textContent.includes(${JSON.stringify(taskId)})); if (!el) throw new Error('Persisted task missing'); el.click(); })()`);
  await click("Report");
  await until(async () => (await text()).includes("下载 DOCX"), "persisted report and exports after reload");
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 1, mobile: true });
  await sleep(200);
  assert.equal(await cdp.eval("document.documentElement.scrollWidth <= window.innerWidth + 1"), true);
  console.log(JSON.stringify({ passed: true, database: ready.database, task_id: taskId,
    flow: "create → pause/resume → debate → human review → resumed Worker → Markdown/DOCX browser downloads → reload",
    sse_events: [...events].sort(), real_calls: 0 }, null, 2));
} catch (error) {
  if (cdp) console.error("Browser state:", await cdp.eval("document.querySelector('.researchMain')?.innerText || document.querySelector('[role=alert]')?.innerText || 'unavailable'").catch(() => "unavailable"));
  throw error;
} finally {
  cdp?.close();
  if (browser) {
    browser.kill();
    await new Promise(done => { if (browser.exitCode !== null) done(); else browser.once("exit", done); });
  }
  for (const upstream of upstreams) upstream.destroy();
  server.closeAllConnections(); server.close();
  if (api) { api.stdin.end(); await apiExited; }
  const profilePath = resolve(profile);
  if (profilePath.startsWith(`${resolve(tmpdir())}${sep}`) && profilePath.split(sep).at(-1).startsWith("tcm-research-e2e-")) {
    try { await rm(profilePath, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); }
    catch { console.warn(`Temporary Edge profile retained: ${profilePath}`); }
  }
}
