/** Real browser -> HTTP API -> PostgreSQL with API egress physically blocked. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { createServer, request } from "node:http";
import { mkdtemp, readFile, rm, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, extname, join, relative, resolve, sep } from "node:path";
import { createInterface } from "node:readline";
import { Cdp, connect, until } from "./research_browser_driver.mjs";

const dist = resolve(import.meta.dirname, "../dist");
const artifacts = resolve(import.meta.dirname, "../../docs/acceptance-artifacts/vib48-offline");
const profile = await mkdtemp(join(tmpdir(), "tcm-retrieval-offline-"));
const pageUrl = "http://127.0.0.1:18066/";
let api, browser, cdp, ready, finalResult;
let resolveReady, rejectReady, resolveFinal, rejectFinal;
const readyPromise = new Promise((done, fail) => { resolveReady = done; rejectReady = fail; });
const finalPromise = new Promise((done, fail) => { resolveFinal = done; rejectFinal = fail; });
// Keep any early process failure handled while the browser has not awaited it.
finalPromise.catch(() => {});
const calls = [];
const upstreams = new Set();
const server = createServer(async (req, res) => {
  const path = new URL(req.url, pageUrl).pathname;
  if (path.startsWith("/api/")) {
    calls.push(`${req.method} ${req.url}`);
    const upstream = request(`http://127.0.0.1:18065${req.url}`, {
      method: req.method, headers: { ...req.headers, host: "127.0.0.1:18065" },
    }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res); });
    upstreams.add(upstream); upstream.on("close", () => upstreams.delete(upstream));
    upstream.on("error", () => { if (!res.headersSent) res.writeHead(502); res.end(); });
    res.on("close", () => upstream.destroy()); req.pipe(upstream); return;
  }
  const file = path === "/" ? join(dist, "index.html") : resolve(dist, `.${path}`);
  if (relative(dist, file).startsWith("..")) { res.writeHead(403); res.end(); return; }
  try {
    const data = await readFile(file);
    res.writeHead(200, { "Content-Type": ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css" })[extname(file)] || "application/octet-stream" });
    res.end(data);
  } catch { res.writeHead(404); res.end(); }
});

try {
  api = spawn("docker", ["exec", "-i", "-e", "PYTHONPATH=/workspace/backend/src",
    "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "TCM_OFFLINE_ACCEPTANCE=internal-network-v1",
    "-w", "/workspace/backend", "tcm-vib54-py", "python", "-u", "scripts/check_retrieval_offline_e2e.py"],
  { windowsHide: true, stdio: ["pipe", "pipe", "inherit"] });
  api.on("error", error => { rejectReady(error); rejectFinal(error); });
  api.once("exit", code => {
    if (!ready) rejectReady(new Error(`API exited before readiness: ${code}`));
    if (!finalResult) rejectFinal(new Error(`API exited before acceptance: ${code}`));
  });
  createInterface({ input: api.stdout }).on("line", line => {
    let value;
    try { value = JSON.parse(line); } catch { console.error(line); return; }
    if (value.ready) { ready = value; resolveReady(value); }
    if (value.passed) { finalResult = value; resolveFinal(value); }
  });
  api.stdin.write(JSON.stringify({ secret: randomBytes(32).toString("hex") }) + "\n");
  let timer;
  try {
    await Promise.race([readyPromise, new Promise((_, fail) => { timer = setTimeout(() => fail(new Error("Offline API readiness timed out")), 60000); })]);
  } finally { clearTimeout(timer); }
  await until(async () => {
    try { return (await fetch("http://127.0.0.1:18065/api/v1/system/health")).ok; }
    catch { return false; }
  }, "real HTTP relay");
  await new Promise((done, fail) => { server.once("error", fail); server.listen(18066, "127.0.0.1", done); });
  browser = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    ["--headless=new", "--remote-debugging-port=9226", "--remote-allow-origins=*", `--user-data-dir=${profile}`, "about:blank"],
    { windowsHide: true, stdio: "ignore" });
  await connect(9226);
  const target = await (await fetch(`http://127.0.0.1:9226/json/new?${encodeURIComponent(pageUrl)}`, { method: "PUT" })).json();
  cdp = new Cdp(target.webSocketDebuggerUrl); await cdp.send("Runtime.enable");
  const text = () => cdp.eval("document.body?.innerText || ''");
  const click = label => cdp.eval(`(() => { const el = [...document.querySelectorAll('button')].find(el => el.textContent.trim() === ${JSON.stringify(label)}); if (!el || el.disabled) throw new Error('Button unavailable'); el.click(); })()`);
  const fill = value => cdp.eval(`(() => { const el = document.querySelector('#knowledge-query'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  await until(() => cdp.eval("!!document.querySelector('#knowledge-query')"), "retrieval form");
  await fill(ready.query); await click("检索证据");
  await until(async () => (await text()).includes(ready.quote), "actual published evidence");
  assert.match(await text(), /本次查询未授权云端外发/);
  assert.ok(calls.some(call => call.includes("allow_remote_query=false")));
  await click("查看证据详情");
  assert.ok((await text()).includes(ready.quote));
  assert.ok((await text()).includes(ready.evidence_id));
  assert.match(await text(), /修订 1/);
  await cdp.eval("document.querySelector('[aria-label=\"关闭证据详情\"]').click()");
  await cdp.eval("document.querySelector('.searchPanel input[type=checkbox]').click()");
  await click("检索证据");
  await until(async () => (await text()).includes("云端语义检索失败"), "actual offline fallback status", 45000);
  assert.match(await text(), /检索已降级/);
  assert.ok((await text()).includes(ready.quote));
  await click("查看证据详情");
  assert.ok((await text()).includes(ready.quote));
  await mkdir(artifacts, { recursive: true });
  const screenshot = await cdp.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  await writeFile(join(artifacts, "offline-evidence.png"), Buffer.from(screenshot.data, "base64"));
  await cdp.eval("document.querySelector('[aria-label=\"关闭证据详情\"]').click()");
  await cdp.send("Page.reload");
  await until(() => cdp.eval("!!document.querySelector('#knowledge-query')"), "reload while offline");
  await fill(ready.query); await click("检索证据");
  await until(async () => (await text()).includes(ready.quote), "offline query after reload");
  assert.match(await text(), /本次查询未授权云端外发/);
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 1, mobile: true });
  assert.equal(await cdp.eval("document.documentElement.scrollWidth <= window.innerWidth + 1"), true);
  api.stdin.write(JSON.stringify({ action: "finish" }) + "\n");
  await finalPromise;
  const result = { ...finalResult, browser_passed: true,
    browser_checks: ["real_backend_local_query", "published_original_quote_and_revision_detail",
      "actual_transport_fault_fallback_notice_and_evidence", "reload_without_internet", "375px_layout"],
    api_requests: calls, network: "Docker internal; API has no external attachment" };
  await writeFile(join(artifacts, "result.json"), JSON.stringify(result, null, 2) + "\n");
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  if (cdp) console.error("Browser state:", await textSafe());
  throw error;
} finally {
  cdp?.close();
  if (browser) {
    browser.kill();
    await new Promise(done => { if (browser.exitCode !== null) done(); else browser.once("exit", done); });
  }
  for (const upstream of upstreams) upstream.destroy();
  server.closeAllConnections(); server.close();
  if (api) {
    api.stdin.end();
    await new Promise(done => { if (api.exitCode !== null) done(); else api.once("exit", done); });
  }
  const safeProfile = resolve(profile);
  if (safeProfile.startsWith(resolve(tmpdir()) + sep) && basename(safeProfile).startsWith("tcm-retrieval-offline-")) {
    await rm(safeProfile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}
async function textSafe() { return cdp.eval("document.querySelector('.searchPanel')?.innerText || 'unavailable'").catch(() => "unavailable"); }
