/** Read-only regression against the existing Fangji evidence, real local API. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { Cdp, connect, until } from "./research_browser_driver.mjs";

const origin = process.env.TCM_CITATION_ORIGIN || "http://127.0.0.1:18067";
const source = "SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350";
const evidence = "EV-01a0f68d-647a-78cf-8b60-1d51bd1adb64";
const artifacts = resolve(import.meta.dirname, "../../docs/acceptance-artifacts/vib89");
await mkdir(artifacts, { recursive: true });
const profile = await mkdtemp(join(tmpdir(), "tcm-citation-"));
const browser = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", ["--headless=new", "--no-first-run", "--no-default-browser-check", `--user-data-dir=${profile}`, "--remote-debugging-port=19279", "about:blank"], { windowsHide: true, stdio: "ignore" });
let page;
const evalJs = code => page.eval(code);
const click = async label => {
  const expr = `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)} && !b.disabled)`;
  await until(() => evalJs(`!!(${expr})`), label);
  await evalJs(`(${expr}).click()`);
};
const snapshot = async name => {
  const shot = await page.send("Page.captureScreenshot", { format: "png" });
  await writeFile(join(artifacts, name), Buffer.from(shot.data, "base64"));
};
try {
  await connect(19279);
  const target = await (await fetch(`http://127.0.0.1:19279/json/new?${encodeURIComponent(origin)}`, { method: "PUT" })).json();
  page = new Cdp(target.webSocketDebuggerUrl);
  await page.send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  await until(() => evalJs("document.body?.innerText.includes('本机工作区已连接')"), "local session");
  await evalJs(`sessionStorage.setItem('tcm.knowledge.position', JSON.stringify({sourceId:${JSON.stringify(source)},revision:1,tab:'publish'}))`);
  await page.send("Page.navigate", { url: `${origin}/?workspace=search` });
  await until(() => evalJs("!!document.querySelector('#knowledge-query')"), "search page");
  await evalJs(`(() => { const el=document.querySelector('#knowledge-query'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'大青龙汤'); el.dispatchEvent(new Event('input',{bubbles:true})); })()`);
  await click("检索证据");
  await until(() => evalJs("document.querySelectorAll('.resultCard').length===1"), "existing published evidence");
  await click("查看证据详情");
  await until(() => evalJs("!!document.querySelector('.drawer .textButton') && !document.querySelector('.drawerBody .muted')?.textContent.includes('正在读取')"), "exact evidence");
  await until(() => evalJs("document.querySelector('.drawer .textButton')?.disabled===false"), "verified evidence");
  assert.ok(await evalJs("[...document.querySelectorAll('.drawer h4')].some(el=>el.textContent==='原文上下文')"), "live API supplies complete contexts");
  await click("打开来源文献");
  await until(() => evalJs("!!document.querySelector('.kwTabs .active')"), "source workspace");
  assert.equal(await evalJs("document.querySelector('.kwTabs .active').textContent"), "1 · 来源与原文", "citation must force original reading, overriding saved publish tab");
  await until(() => evalJs("!!document.querySelector('.kwOriginal mark')"), "citation loaded and highlighted");
  assert.equal(await evalJs("document.querySelector('.kwSourceTitle select').value"), "2");
  assert.match(await evalJs("location.search"), new RegExp(`citation=${evidence}`));
  assert.match(await evalJs("document.querySelector('.kwOriginal mark').textContent"), /麻黄.*六两/);
  assert.equal(await evalJs("document.querySelectorAll('.kwSegmentRow.cited').length"), 15);
  assert.match(await evalJs("document.querySelector('.kwOriginal').innerText"), /伤寒论/);
  await snapshot("fangji-citation.png");
  await page.send("Page.reload");
  await until(() => evalJs("document.querySelectorAll('.kwOriginal mark').length===15"), "reload restores precise citation");
  assert.equal(await evalJs("document.querySelector('.kwSourceTitle select').value"), "2");
  // Browser Back still returns to the exact evidence URL after a reload.
  await click("返回引用处");
  await until(() => evalJs("!!document.querySelector('.drawer .textButton')"), "return evidence");
  assert.match(await evalJs("location.search"), /workspace=search/);
  assert.match(await evalJs("document.querySelector('.drawerQuote').textContent"), /麻黄.*六两/);
  await page.send("Page.navigate", { url: `${origin}/?workspace=knowledge&source=${source}&source_revision=2&citation=${evidence}&citation_revision=1` });
  await until(() => evalJs("document.querySelectorAll('.kwOriginal mark').length===15"), "direct citation URL");
  await page.send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  assert.equal(await evalJs("document.documentElement.scrollWidth <= innerWidth + 1"), true, "citation mobile layout");
  await snapshot("fangji-citation-mobile.png");
  await writeFile(join(artifacts, "real-result.json"), JSON.stringify({ source, evidence, source_revision: 2, evidence_revision: 1, highlighted_paragraphs: 15, search: "passed", reload: "passed", return: "passed", direct_url: "passed", mobile: "passed", model_calls: 0 }, null, 2));
  console.log("PASS: real Fangji search → revision 2 / all 15 highlighted paragraphs → exact evidence return; reload, direct URL and mobile layout.");
} catch (error) {
  console.error(error.message);
  if (page) {
    await writeFile(join(artifacts, "failure-state.txt"), await evalJs("document.body.innerText"));
  }
  throw error;
} finally {
  page?.close(); browser.kill();
}
