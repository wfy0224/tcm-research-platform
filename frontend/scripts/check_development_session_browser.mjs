/** Browser regression against the running real development API; no model calls. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { Cdp, connect, until } from "./research_browser_driver.mjs";

const origin = "http://127.0.0.1:18067";
const profile = await mkdtemp(join(tmpdir(), "tcm-dev-session-"));
const port = 19267;
const browser = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", [
  "--headless=new", "--no-first-run", "--no-default-browser-check",
  `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "about:blank",
], { windowsHide: true, stdio: "ignore" });
const pages = [];

async function openPage(url) {
  const response = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: "PUT" });
  const target = await response.json();
  const page = new Cdp(target.webSocketDebuggerUrl); pages.push(page);
  await until(async () => (await page.eval("document.body.innerText")).includes("本机工作区已连接"), "automatic connection");
  assert.equal(await page.eval("document.querySelector('#bootstrap-secret') === null"), true);
  return page;
}

async function session(page) {
  return page.eval("fetch('/api/v1/local-session').then(r => r.json()).then(s => ({id: s.session_id, csrf: sessionStorage.getItem('tcm.local.csrf')}))");
}

try {
  const config = await fetch(`${origin}/api/v1/local-session/config`).then(r => r.json());
  assert.equal(config.development_auto_session, true);
  await connect(port);
  const first = await openPage(`${origin}/?workspace=knowledge`);
  assert.equal(await first.eval("fetch('/api/v1/knowledge/sources').then(r => r.status)"), 200);
  const initial = await session(first); assert.ok(initial.csrf);
  await first.send("Page.reload");
  await until(async () => (await first.eval("document.body.innerText")).includes("本机工作区已连接"), "reload restores session");
  assert.deepEqual(await session(first), initial);
  const second = await openPage(`${origin}/?workspace=research`);
  assert.deepEqual(await session(second), initial);
  await first.eval("sessionStorage.setItem('tcm.local.csrf', 'stale-token')");
  await first.send("Page.reload");
  await until(async () => (await first.eval("document.body.innerText")).includes("本机工作区已连接"), "stale credentials recover");
  assert.deepEqual(await session(first), initial);
  assert.equal(await second.eval("fetch('/api/v1/research/tasks').then(r => r.status)"), 200);
  assert.equal(await first.eval(`fetch('/api/v1/knowledge/sources/import', {
    method: 'POST', headers: {'Content-Type': 'application/json',
    'X-CSRF-Token': sessionStorage.getItem('tcm.local.csrf'), 'Idempotency-Key': crypto.randomUUID()},
    body: '{}'}).then(r => r.status)`), 422);
  // Losing tab storage recovers the same credentials from the existing development session.
  await second.eval("sessionStorage.clear()"); await second.send("Page.reload");
  await until(async () => (await second.eval("document.body.innerText")).includes("本机工作区已连接"), "new tab recovers CSRF");
  assert.deepEqual(await session(second), initial);
  await second.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 1, mobile: true });
  assert.equal(await second.eval("document.querySelector('#bootstrap-secret') === null"), true);
  await second.send("Network.enable");
  await second.send("Network.setBlockedURLs", { urls: ["*/api/v1/local-session/config"] });
  await second.send("Page.reload");
  await until(async () => (await second.eval("document.body.innerText")).includes("重新连接"), "service outage offers retry");
  assert.equal(await second.eval("document.querySelector('#bootstrap-secret') === null"), true);
  await second.send("Network.setBlockedURLs", { urls: [] });
  await second.eval("Array.from(document.querySelectorAll('button')).find(b => b.textContent === '重新连接').click()");
  await until(async () => (await second.eval("document.body.innerText")).includes("本机工作区已连接"), "retry reconnects automatically");
  assert.deepEqual(await session(second), initial);
  console.log(JSON.stringify({ automatic_connection: true, reload: true, new_tab: true,
    csrf_preserved: true, storage_recovery: true, stale_csrf_recovery: true, knowledge_api: 200, research_api: 200,
    mobile_without_code: true, outage_retry: true, real_model_calls: 0 }));
} finally {
  pages.forEach(page => page.close());
  const exited = new Promise(done => browser.once("exit", done));
  browser.kill(); await exited;
  if (resolve(dirname(profile)) !== resolve(tmpdir()) || !basename(profile).startsWith("tcm-dev-session-")) {
    throw new Error("refusing unexpected browser profile cleanup path");
  }
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
