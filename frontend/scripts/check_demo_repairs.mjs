/** Actual UI/API/Worker checks in tcm_vib62_demo_repairs_test; no model calls. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { Cdp, connect, until } from "./research_browser_driver.mjs";

const origin = "http://127.0.0.1:18075";
const profile = await mkdtemp(join(tmpdir(), "tcm-demo-repairs-"));
const artifacts = resolve(import.meta.dirname, "../../docs/acceptance-artifacts/demo-repairs");
await mkdir(artifacts, { recursive: true });
const browser = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", ["--headless=new", "--no-first-run", "--no-default-browser-check", `--user-data-dir=${profile}`, "--remote-debugging-port=19276", "about:blank"], { windowsHide: true, stdio: "ignore" });
let page;
const evalJs = code => page.eval(code);
const click = async label => {
  const expression = `[...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)} && !b.disabled)`;
  await until(() => evalJs(`!!(${expression})`), label);
  await evalJs(`(${expression}).click()`);
};
const fill = (selector, value) => evalJs(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if(!el) throw Error('Missing field'); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input',{bubbles:true})); })()`);
const checkbox = selector => evalJs(`document.querySelector(${JSON.stringify(selector)}).click()`);
const snapshot = async name => {
  const result = await page.send("Page.captureScreenshot", { format: "png" });
  await writeFile(join(artifacts, name), Buffer.from(result.data, "base64"));
};
const importText = async (text, title) => {
  await click("＋ 导入文献");
  await evalJs(`(() => { const input=document.querySelector('.kwImport input[type=file]'); const transfer=new DataTransfer(); transfer.items.add(new File([${JSON.stringify(text)}],'demo-repair.txt',{type:'text/plain'})); input.files=transfer.files; input.dispatchEvent(new Event('change',{bubbles:true})); })()`);
  await fill(".kwImport input[maxlength='500']",title);
  await click("导入并解析");
  await until(() => evalJs(`document.querySelector('.kwSourceTitle h3')?.textContent === ${JSON.stringify(title)} && !!document.querySelector('.kwSegmentRow input:not(:disabled)')`),"import segmented",60000);
};
try {
  await connect(19276);
  const target = await (await fetch(`http://127.0.0.1:19276/json/new?${encodeURIComponent(origin + '/?workspace=knowledge')}`,{method:"PUT"})).json();
  page = new Cdp(target.webSocketDebuggerUrl);
  await page.send("Emulation.setDeviceMetricsOverride",{width:1280,height:900,deviceScaleFactor:1,mobile:false});
  await until(() => evalJs("document.body.innerText.includes('本机工作区已连接')"),"development session");
  const sample = "【组成】合成麻黄三两。\n续文保留剂量说明。\n【用法】合成水煎服。";
  await importText(sample, `合成演示修复 ${randomUUID()}`);
  assert.equal(await evalJs("document.querySelectorAll('.kwSegmentRow input:not(:disabled)').length"),3,"reading excludes sentence duplicates");
  await evalJs("[...document.querySelectorAll('.kwSegmentRow input:not(:disabled)')].forEach(el=>el.click())");
  await click("创建精确证据草稿");
  await until(() => evalJs("!!document.querySelector('.kwReviewAction')"),"complete quote");
  assert.equal(await evalJs("document.querySelector('.kwCard blockquote').textContent"),sample);
  await click("取消");
  await click("1 · 来源与原文");
  await until(() => evalJs("!!document.querySelector('.kwSegmentRow input:not(:disabled)')"),"source restored");
  await evalJs("[...document.querySelectorAll('.kwSegmentRow input:checked')].forEach(el=>el.click())");
  await checkbox(".kwSegmentRow input:not(:disabled)");
  await click("创建精确证据草稿");
  await until(() => evalJs("document.querySelectorAll('.kwReviewGrid > div:first-child .kwCard').length === 2"),"two evidence drafts");
  await click("取消");
  await evalJs("document.querySelectorAll('.kwReviewGrid > div:first-child .kwCard input[type=checkbox]').forEach(el=>el.click())");
  // Fail the second request once: the first decision must stay saved, while
  // selection and note for unsaved work remain available for a user retry.
  await evalJs(`window.repairFetch=window.fetch; window.reviewRequests=0; window.fetch=async (...args)=> { if(String(args[0]).includes('/reviews/')) { if(++window.reviewRequests===2) return Response.json({detail:'合成网络故障'},{status:503}); } return window.repairFetch(...args); };`);
  await fill(".kwBatchReview textarea","合成样本批量核对说明");
  await click("确认所选已核对并通过");
  await until(() => evalJs("!!document.querySelector('.kwError') && !document.querySelector('.kwOperation')"),"partial batch failure");
  assert.match(await evalJs("document.querySelector('.kwNotice').textContent"),/1 \/ 2/);
  assert.equal(await evalJs("document.querySelectorAll('.kwReviewGrid input:checked').length"),1);
  assert.equal(await evalJs("document.querySelector('.kwBatchReview textarea').value"),"合成样本批量核对说明");
  await evalJs("window.fetch=window.repairFetch");
  await click("确认所选已核对并通过");
  await until(() => evalJs("document.querySelectorAll('.kwReviewGrid input[type=checkbox]').length === 0 && !document.querySelector('.kwOperation')"),"remaining evidence reviewed");
  await fill(".kwDraftForm input[maxlength='300']","合成演示修复概念");
  await click("建立待审核草稿");
  await until(() => evalJs("!!document.querySelector('.kwReviewGrid > div:last-child .kwCard input')"),"knowledge draft");
  await checkbox(".kwReviewGrid > div:last-child .kwCard input");
  await click("确认所选已核对并通过");
  await until(() => evalJs("document.querySelectorAll('.kwReviewGrid > div:last-child .kwCard input').length === 0 && !document.querySelector('.kwOperation')"),"knowledge batch saved");
  await snapshot("batch-review.png");
  await click("1 · 来源与原文");
  // Delay only the response delivery to make transient UI feedback observable.
  await evalJs(`window.repairFetch=window.fetch; window.fetch=async (...args)=> { if(String(args[0]).endsWith('/extract')) await new Promise(r=>setTimeout(r,1800)); return window.repairFetch(...args); };`);
  await click("提取并进入审核");
  await until(() => evalJs("document.querySelector('.kwOperation')?.innerText.includes('已耗时 1 秒')"),"visible extraction elapsed");
  await snapshot("extraction-progress.png");
  await until(() => evalJs("!!document.querySelector('.kwReviewGrid') && !document.querySelector('.kwOperation')"),"extraction done",60000);
  await evalJs("window.fetch=window.repairFetch");
  await click("1 · 来源与原文");
  const fullText = await readFile("C:/Users/wangfeiyu/Downloads/方剂学.txt","utf8");
  await importText(fullText,`方剂学完整修复验收 ${randomUUID()}`);
  assert.match(await evalJs("document.querySelector('.kwOriginal blockquote').textContent"),/经过长期/);
  await snapshot("full-text-reading.png");
  // Locate the actual 麻黄汤 composition using page loads, then select its
  // complete contiguous composition/use/action/mechanism/explanation range.
  let found = false;
  for(let i=0;i<80;i++) {
    found=await evalJs("[...document.querySelectorAll('.kwSegmentRow')].some(row=>row.innerText.includes('【组成】麻黄去节，三两'))");
    if(found) break;
    await click("加载后续段落");
    await until(() => evalJs("!document.querySelector('.kwOperation')"),"page appended");
  }
  assert.ok(found,"real 麻黄汤 range located through reading pages");
  await click("加载后续段落");
  await until(() => evalJs("!document.querySelector('.kwOperation')"),"following paragraphs");
  const selectedText=await evalJs(`(() => { const rows=[...document.querySelectorAll('.kwSegmentRow')]; const start=rows.findIndex(row=>row.innerText.includes('【组成】麻黄去节，三两')); let end=rows.findIndex((row,i)=>i>start && row.innerText.includes('【附方】')); if(end<0) end=rows.findIndex((row,i)=>i>start && row.innerText.includes('【医案举例】')); if(end<0) throw Error('Range end not loaded'); const chosen=rows.slice(start,end).filter(row=>!row.querySelector('input').disabled); chosen.forEach(row=>row.querySelector('input').click()); return chosen.map(row=>row.innerText); })()`);
  assert.ok(selectedText.length>5);
  await click("创建精确证据草稿");
  await until(() => evalJs("!!document.querySelector('.kwReviewAction')"),"full real evidence created");
  assert.match(await evalJs("document.querySelector('.kwReviewGrid').innerText"),/【组成】麻黄去节/);
  await snapshot("full-text-evidence.png");
  // Leave all real material pending: engineering checks are not medical review.
  await page.send("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
  assert.equal(await evalJs("document.documentElement.scrollWidth <= innerWidth"),true,"mobile overflow");
  await snapshot("mobile-review.png");
  console.log("Demo repairs passed: reading, mixed complete quote, partial batch recovery, evidence then knowledge, optional approval note, extraction elapsed, full Fangji input/read/evidence and mobile layout; real evidence remains DRAFT.");
} catch (error) {
  if (page) {
    await snapshot("failure.png");
    await writeFile(join(artifacts,"failure-state.txt"),await evalJs("document.querySelector('.kwWorkspace')?.innerText || ''"));
  }
  throw error;
} finally {
  page?.close(); browser.kill();
}
