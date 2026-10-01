/** VIB-87: actual API/Workers, synthetic input, manual evidence path, no cloud calls. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { Cdp, connect, until } from "./research_browser_driver.mjs";

const origin = process.env.TCM_IMPORT_E2E_ORIGIN || "http://127.0.0.1:18075";
assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
const profile = await mkdtemp(join(tmpdir(), "tcm-import-guidance-"));
const port = 19275;
const browser = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", [
  "--headless=new", "--no-first-run", "--no-default-browser-check",
  `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "about:blank",
], { windowsHide: true, stdio: "ignore" });
let page;
const text = () => page.eval("document.body?.innerText || ''");
const click = async (label) => {
  const expr = `[...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)} && !b.disabled)`;
  await until(() => page.eval(`!!(${expr})`), label);
  await page.eval(`(${expr}).click()`);
};
const fill = (selector, value) => page.eval(`(() => {
  const el = document.querySelector(${JSON.stringify(selector)}); if (!el) throw new Error('Missing field');
  Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(value)});
  el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
const title = `合成导入引导 ${randomUUID()}`;
const sample = "合成核对流程用于验证操作引导。\n第二段保留原文来源。\n第三段用于验证不连续选择。";
function blankPdf() {
  const objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>", "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> >>"];
  let value = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, i) => { offsets.push(value.length); value += `${i + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = value.length;
  return `${value}xref\n0 4\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
}
try {
  await connect(port);
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(`${origin}/?workspace=knowledge`)}`, { method: "PUT" })).json();
  page = new Cdp(target.webSocketDebuggerUrl);
  await until(async () => (await text()).includes("本机工作区已连接"), "session");
  const sourceCount = await page.eval("fetch('/api/v1/knowledge/sources?limit=100').then(r => r.json()).then(rows => rows.length)");
  await until(() => page.eval(`document.querySelectorAll('.kwSourceList button').length === ${sourceCount}`), "source catalogue loaded");
  await page.eval("document.querySelector('.kwImport').open = true");
  assert.match(await page.eval("document.querySelector('.kwImport').innerText"), /请选择.*文件/, "missing-file reason must be visible beside disabled import");
  await page.eval(`(() => { const input = document.querySelector('.kwImport input[type=file]');
    const transfer = new DataTransfer(); transfer.items.add(new File([${JSON.stringify(sample)}], 'guidance.txt', {type:'text/plain'}));
    input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles:true})); })()`);
  await fill(".kwImport input[maxlength='500']", " ");
  assert.match(await page.eval("document.querySelector('.kwImport').innerText"), /填写.*标题/);
  await fill(".kwImport input[maxlength='500']", title);
  await click("导入并解析");
  await until(() => page.eval("!!document.querySelector('.kwSegmentRow input:not(:disabled)')"), "parse", 60000);
  await click("前往审核");
  assert.match(await page.eval("document.querySelector('.kwDraftForm').innerText"), /没有.*证据/);
  await click("返回原文建立证据");
  await until(() => page.eval("!!document.querySelector('.kwSegmentRow input:not(:disabled)')"), "return to original");
  await page.eval(`(() => {
    const inputs = [...document.querySelectorAll('.kwSegmentRow input:not(:disabled)')];
    inputs[0].click(); inputs.at(-1).click(); })()`);
  await until(async () => (await text()).includes("连续原文段落，避免重复"), "non-contiguous reason");
  assert.equal(await page.eval("[...document.querySelectorAll('.kwEvidenceBar button')].find(b => b.textContent === '创建精确证据草稿').disabled"), true);
  await page.eval("[...document.querySelectorAll('.kwSegmentRow input:checked')].forEach(input => input.click())");
  await page.eval("document.querySelector('.kwSegmentRow input:not(:disabled)').click()");
  await click("创建精确证据草稿");
  await until(() => page.eval("!!document.querySelector('.kwReviewAction')"), "manual review");
  assert.match(await page.eval("document.querySelector('.kwDraftForm').innerText"), /核对/);
  await fill(".kwReviewAction textarea", "合成工程样本：核对精确原文；不代表真实文献或专家审核。");
  await click("确认审核通过");
  await until(() => page.eval("!document.querySelector('.kwReviewAction')"), "review persisted");
  assert.ok(await page.eval("document.querySelector('.kwDraftForm select').value"), "reviewed evidence is selected automatically");
  await fill(".kwDraftForm input[maxlength='300']", "合成流程概念");
  await page.send("Network.enable");
  await page.send("Network.setBlockedURLs", { urls: ["*/api/v1/knowledge/drafts/concepts"] });
  await click("建立待审核草稿");
  await until(() => page.eval("!!document.querySelector('.kwDraftForm [role=alert]')"), "draft failure beside form");
  assert.equal(await page.eval("document.querySelector('.kwDraftForm input[maxlength=\"300\"]').value"), "合成流程概念");
  await page.send("Network.setBlockedURLs", { urls: [] });
  await page.eval("(() => { const button = [...document.querySelectorAll('.kwDraftForm button')].find(b => b.textContent === '建立待审核草稿'); button.click(); button.click(); })()");
  await until(async () => (await text()).includes("知识草稿已创建"), "draft created");
  assert.match(await text(), /合成流程概念/);
  assert.equal(await page.eval("[...document.querySelectorAll('.kwCard strong')].filter(el => el.textContent === '合成流程概念').length"), 1, "double click creates one draft");
  await page.send("Page.reload");
  await until(() => page.eval("!!document.querySelector('.kwReviewHead')"), "review step restored");
  await until(() => page.eval(`document.querySelector('.kwReviewHead select').selectedOptions[0]?.textContent === ${JSON.stringify(title)}`), "source restored");
  await until(async () => (await text()).includes("合成流程概念"), "draft restored");
  assert.ok(await page.eval("document.querySelector('.kwDraftForm select').value"));
  await click("1 · 来源与原文");
  await until(() => page.eval("!!document.querySelector('.kwImport input[type=file]')"), "import second source");
  const secondTitle = `${title} 第二份`;
  await page.eval(`(() => { document.querySelector('.kwImport').open = true;
    const input = document.querySelector('.kwImport input[type=file]'); const transfer = new DataTransfer();
    transfer.items.add(new File(['第二份合成资料用于验证切换范围。'], 'second.txt', {type:'text/plain'}));
    input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles:true})); })()`);
  await fill(".kwImport input[maxlength='500']", secondTitle);
  await click("导入并解析");
  await until(() => page.eval(`document.querySelector('.kwSourceTitle h3')?.textContent === ${JSON.stringify(secondTitle)} && !!document.querySelector('.kwSegmentRow input:not(:disabled)')`), "second source parsed", 60000);
  await click("前往审核");
  await until(() => page.eval("!!document.querySelector('.kwDraftForm')"), "second review");
  assert.match(await page.eval("document.querySelector('.kwDraftForm').innerText"), /没有.*证据/);
  assert.equal(await page.eval("document.querySelector('.kwDraftForm select').value"), "");
  await page.eval(`(() => { const select = document.querySelector('.kwReviewHead select');
    const option = [...select.options].find(o => o.textContent === ${JSON.stringify(title)});
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, option.value);
    select.dispatchEvent(new Event('change', {bubbles:true})); })()`);
  await until(() => page.eval("!!document.querySelector('.kwDraftForm select').value"), "switch restores correct reviewed evidence");
  await page.send("Page.reload");
  await until(() => page.eval("!!document.querySelector('.kwDraftForm select')?.value"), "switched scope survives reload");
  for (const [filename, content, reason] of [["broken.pdf", "not a PDF", "解析失败"], ["scan.pdf", blankPdf(), "需要 OCR"]]) {
    await click("1 · 来源与原文");
    await until(() => page.eval("!!document.querySelector('.kwImport input[type=file]')"), "failure fixture import form");
    const fixtureTitle = `${title} ${filename}`;
    await page.eval(`(() => { document.querySelector('.kwImport').open = true;
      const input = document.querySelector('.kwImport input[type=file]'); const transfer = new DataTransfer();
      transfer.items.add(new File([${JSON.stringify(content)}], ${JSON.stringify(filename)}, {type:'application/pdf'}));
      input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles:true})); })()`);
    await fill(".kwImport input[maxlength='500']", fixtureTitle);
    await click("导入并解析");
    await until(() => page.eval(`document.querySelector('.kwSourceTitle h3')?.textContent === ${JSON.stringify(fixtureTitle)} && document.querySelector('.kwNextStep').innerText.includes(${JSON.stringify(reason)})`), reason, 60000);
    await click("重新导入此来源");
    assert.ok(await page.eval("document.querySelector('.kwImport').open"));
    assert.ok(await page.eval("[...document.querySelectorAll('.kwImport label')].find(el => el.textContent.includes('作为所选来源的新修订')).querySelector('input').checked"));
    await page.eval("[...document.querySelectorAll('.kwImport label')].find(el => el.textContent.includes('作为所选来源的新修订')).querySelector('input').click()");
  }
  await page.send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 1, mobile: true });
  assert.ok(await page.eval("document.documentElement.scrollWidth <= innerWidth + 1"), "mobile flow fits viewport");
  console.log(JSON.stringify({ passed: true, missing_file: true, missing_title: true,
    no_evidence_recovery: true, manual_review: true, draft_failure_retry: true,
    reload: true, source_switch: true, non_contiguous_selection: true,
    parse_failure: true, ocr_required: true, double_submit_guard: true,
    narrow_screen: true, real_model_calls: 0, real_corpus_approved: false }));
} catch (error) {
  console.error(error);
  process.exitCode = 1;
} finally {
  page?.close();
  if (browser.exitCode === null) { const done = new Promise(resolve => browser.once("exit", resolve)); browser.kill(); await done; }
  if (resolve(dirname(profile)) !== resolve(tmpdir()) || !basename(profile).startsWith("tcm-import-guidance-")) throw new Error("Unexpected cleanup path");
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
