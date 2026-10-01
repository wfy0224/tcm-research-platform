/** Reparse the user's existing demo source through the UI as a new revision. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Cdp, connect, until } from "./research_browser_driver.mjs";

const title="方剂学（麻黄汤与大青龙汤研究）";
const profile=await mkdtemp(join(tmpdir(),"tcm-fangji-repair-"));
const browser=spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",["--headless=new","--no-first-run",`--user-data-dir=${profile}`,"--remote-debugging-port=19277","about:blank"],{windowsHide:true,stdio:"ignore"});
let page;
try {
  await connect(19277);
  const target=await(await fetch("http://127.0.0.1:19277/json/new?http://127.0.0.1:18067/?workspace=knowledge",{method:"PUT"})).json();
  page=new Cdp(target.webSocketDebuggerUrl);
  await until(()=>page.eval("document.body.innerText.includes('本机工作区已连接')"),"session");
  await until(()=>page.eval(`[...document.querySelectorAll('.kwSourceList button')].some(b=>b.querySelector('strong')?.textContent===${JSON.stringify(title)})`),"existing source");
  await page.eval(`[...document.querySelectorAll('.kwSourceList button')].find(b=>b.querySelector('strong')?.textContent===${JSON.stringify(title)}).click()`);
  await until(()=>page.eval(`document.querySelector('.kwSourceTitle h3')?.textContent===${JSON.stringify(title)} && !!document.querySelector('.kwOriginal blockquote')`),"source ready");
  const source=await page.eval(`fetch('/api/v1/knowledge/sources?limit=100').then(r=>r.json()).then(rows=>rows.find(row=>row.title===${JSON.stringify(title)}))`);
  const detail=await page.eval(`fetch('/api/v1/knowledge/sources/${source.source_id}').then(r=>r.json())`);
  const latest=detail.revisions.at(-1).revision_no;
  await page.eval(`fetch('/api/v1/knowledge/sources/${source.source_id}/revisions/1/segments?limit=500').then(r=>r.json()).then(rows=> { window.originalSegments=rows; return rows.length; })`);
  const current=await page.eval("document.querySelector('.kwOriginal blockquote').textContent");
  if (!current.includes("经过长期")) {
    await page.eval("[...document.querySelectorAll('.kwSourceTools button')].find(b=>b.textContent==='导入新修订').click()");
    assert.equal(await page.eval("document.querySelector('.kwImport select').value"),source.source_type);
    assert.equal(await page.eval("document.querySelector('.kwImport input[maxlength=\"500\"]').value"),title);
    const text=await readFile("C:/Users/wangfeiyu/Downloads/方剂学.txt","utf8");
    await page.eval(`(() => {const input=document.querySelector('.kwImport input[type=file]');const transfer=new DataTransfer();transfer.items.add(new File([${JSON.stringify(text)}],'方剂学.txt',{type:'text/plain'}));input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await until(()=>page.eval("!![...document.querySelectorAll('.kwImport button')].find(b=>b.textContent==='导入并解析'&&!b.disabled)"),"new revision enabled");
    await page.eval("[...document.querySelectorAll('.kwImport button')].find(b=>b.textContent==='导入并解析').click()");
    console.log("Complete original Fangji file submitted as a new revision; waiting for real parser and alignment.");
    await until(()=>page.eval(`document.querySelector('.kwSourceTools select')?.value==='${latest+1}' && document.querySelector('.kwOriginal blockquote')?.textContent.includes('经过长期')`),"new revision complete",180000);
  }
  const preserved=await page.eval(`fetch('/api/v1/knowledge/sources/${source.source_id}/revisions/1/segments?limit=500').then(r=>r.json()).then(rows=>JSON.stringify(window.originalSegments)===JSON.stringify(rows))`);
  assert.equal(preserved,true,"original revision text, identity and locator must stay unchanged");
  console.log(JSON.stringify({source_id:source.source_id,revision:Number(await page.eval("document.querySelector('.kwSourceTools select').value")),continuous_reading:true,original_revision_unchanged:true,real_reviews_submitted:0}));
} finally {page?.close();browser.kill();}
