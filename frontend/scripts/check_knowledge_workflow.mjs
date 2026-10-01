/** One UI smoke on a fresh isolated test API with automatic local parse/publish Workers.
 * Start that API/proxy on 18069/18070 first. Never point this at a user or preview database.
 * Every mutation uses the rendered UI; GETs only verify IDs and persisted results.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { Cdp, connect, until } from "./research_browser_driver.mjs";

const origin = process.env.TCM_KNOWLEDGE_E2E_ORIGIN || "http://127.0.0.1:18070";
assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
const port = 19270;
const title = `合成知识流程 ${randomBytes(6).toString("hex")}`;
const formulaName = "合成流程湯";
const sample = `${formulaName}方\n甲藥二兩；乙藥三兩\n右二味，以水三升，煮取一升，分服。`;
const profile = await mkdtemp(join(tmpdir(), "tcm-knowledge-smoke-"));
let browser, page;
const get = async (path) => page.eval(`fetch(${JSON.stringify(path)}).then(async r => {
  if (!r.ok) throw new Error('Verification GET HTTP ' + r.status); return r.json(); })`);
const text = () => page.eval("document.body?.innerText || ''");
const click = async (label, scope = "document") => {
  const expression = `[...((${scope})?.querySelectorAll('button') || [])].find(b => b.textContent.trim() === ${JSON.stringify(label)} && !b.disabled)`;
  await until(() => page.eval(`!!(${expression})`), `enabled UI: ${label}`, 120000);
  await page.eval(`(${expression}).click()`);
};
const fill = (selector, value) => page.eval(`(() => {
  const el = document.querySelector(${JSON.stringify(selector)}); if (!el) throw new Error('Missing field: ' + ${JSON.stringify(selector)});
  Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(value)});
  el.dispatchEvent(new Event('input', { bubbles: true })); })()`);

try {
  browser = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", [
    "--headless=new", "--no-first-run", "--no-default-browser-check",
    `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "about:blank",
  ], { windowsHide: true, stdio: "ignore" });
  await connect(port);
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(`${origin}/?workspace=knowledge`)}`, { method: "PUT" })).json();
  page = new Cdp(target.webSocketDebuggerUrl);
  await until(async () => (await text()).includes("本机工作区已连接"), "automatic local session");
  assert.equal((await get("/api/v1/local-session/config")).development_auto_session, true);
  assert.equal((await get("/api/v1/knowledge/sources")).length, 0, "smoke requires a fresh isolated database");
  const configuration = await get("/api/v1/knowledge/publication-config");
  assert.equal(configuration.configuration?.strategy, "local-fts-exact-v1", "smoke must not call cloud models");

  await page.eval(`(() => {
    const input = document.querySelector('.kwImport input[type=file]');
    const transfer = new DataTransfer(); transfer.items.add(new File([${JSON.stringify(sample)}], 'synthetic-knowledge-workflow.txt', { type: 'text/plain' }));
    input.files = transfer.files; input.dispatchEvent(new Event('change', { bubbles: true }));
    document.querySelector('.kwImport').open = true;
  })()`);
  await fill(".kwImport input[maxlength='500']", title);
  await click("导入并解析");
  let source;
  await until(async () => {
    source = (await get("/api/v1/knowledge/sources")).find(row => row.title === title);
    return source?.status === "SEGMENTED";
  }, "real parse/segment Workers", 120000);
  await click("从此修订提取知识候选");
  await until(async () => (await text()).includes("合成流程湯") && (await text()).includes("核对并审核"), "candidate review screen");

  await click("查看完整证据");
  await until(() => page.eval("!!document.querySelector('.drawerQuote')"), "exact EvidenceDrawer");
  const quote = await page.eval("document.querySelector('.drawerQuote').textContent");
  assert.ok(quote.length > 0 && sample.includes(quote), "drawer must show an exact synthetic original span");
  assert.match(await page.eval("document.querySelector('.drawer').innerText"), /来源修订 1 · 证据修订 1/);
  await page.eval("document.querySelector('[aria-label=\"关闭证据详情\"]').click()");

  // Review only this imported synthetic source's Evidence cards, then its one formula.
  while (await page.eval("[...document.querySelectorAll('.kwReviewGrid button')].some(b => b.textContent.trim() === '核对并审核')")) {
    await click("核对并审核");
    await fill(".kwReviewAction textarea", "仅合成主流程样本：已核对精确原文；不代表专家或真实文献审核。");
    await click("确认审核通过");
    await until(() => page.eval("!document.querySelector('.kwReviewAction')"), "synthetic Evidence review persisted");
  }
  const formulaScope = `[...document.querySelectorAll('.kwCard')].find(card => card.querySelector('.kwIngredients') && card.querySelector('strong')?.textContent === ${JSON.stringify(formulaName)})`;
  await click("审核此草稿", `(${formulaScope})`);
  await fill(".kwReviewAction textarea", "仅合成方剂工程门禁：原药味剂量和方法核对通过，未知保持null；非专家验收。");
  await click("确认审核通过");
  await until(() => page.eval("!document.querySelector('.kwReviewAction')"), "synthetic formula review persisted");
  await click("3 · 质量与版本发布");
  await click("创建已审核知识快照");
  await until(async () => (await text()).includes("方剂 1"), "reviewed formula in snapshot");
  await click("发布并构建索引");
  await click("激活为当前检索版本");
  await until(() => page.eval("!!document.querySelector('#knowledge-query')"), "activated search workspace");
  assert.equal(await page.eval("document.querySelector('.searchPanel input[type=checkbox]').checked"), false);
  await fill("#knowledge-query", formulaName);
  await click("检索证据");
  await until(async () => (await text()).includes(title) && (await text()).includes("本地检索"), "published original returned by local search");
  assert.ok(await page.eval(`document.querySelector('.resultCard blockquote')?.textContent.includes(${JSON.stringify(formulaName)})`));

  const versions = await get("/api/v1/knowledge/versions");
  const active = versions.find(row => row.active);
  assert.ok(active);
  const version = await get(`/api/v1/knowledge/versions/${encodeURIComponent(active.version_id)}`);
  assert.equal(version.item_counts.formula_revision, 1);
  assert.ok(version.item_counts.evidence_revision > 0);
  assert.equal(version.index_builds[0].vector_status, "NOT_APPLICABLE");
  console.log(JSON.stringify({ passed: true, source_id: source.source_id, knowledge_version_id: active.version_id,
    flow: "synthetic UI import → extraction → exact EvidenceDrawer → Evidence review → formula review → snapshot → local publish → activate → search",
    real_model_calls: 0, real_corpus_approved: false }, null, 2));
} catch (error) {
  if (page) console.error("Browser state:", await text().catch(() => "unavailable"));
  throw error;
} finally {
  page?.close();
  if (browser && browser.exitCode === null) {
    const exited = new Promise(done => browser.once("exit", done)); browser.kill(); await exited;
  }
  if (resolve(dirname(profile)) !== resolve(tmpdir()) || !basename(profile).startsWith("tcm-knowledge-smoke-")) {
    throw new Error("refusing unexpected browser profile cleanup path");
  }
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
