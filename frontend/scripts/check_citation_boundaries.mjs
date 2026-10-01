/** Isolated UI contracts; synthetic fixtures, no database/model operations. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { extname, join, resolve, sep } from "node:path";
import { Cdp, connect, until } from "./research_browser_driver.mjs";

const dist = resolve(import.meta.dirname, "../dist");
const sourceId = "SRC-contract", taskId = "RT-contract";
const state = { failEvidence: false, failSegments: false, missing: false, requests: [] };
const segments = Array.from({ length: 620 }, (_, n) => ({
  segment_id: `SEG-${n}`, source_revision_no: 1, sequence_no: n,
  segment_type: "PARAGRAPH", parent_segment_id: null,
  original_text: `旧修订逻辑段${n + 1}：保留原文，经\n过核对。`, normalized_text: "规范文本",
  context_before: n ? `完整上文${n}` : "", context_after: n < 619 ? `完整下文${n + 2}` : "",
  locator: { paragraph_no: n + 1, chapter_no: null, page_no: 1, path: `paragraph:${n + 1}`, physical_lines: [{ line_no: n + 1 }] },
  page_no: 1, chapter_no: null, paragraph_no: n + 1,
}));
const sentence = { ...segments[600], segment_id: "SEG-sentence", sequence_no: 600.5, segment_type: "SENTENCE", parent_segment_id: "SEG-600", original_text: "只引用第二句。", locator: { paragraph_no: 601, path: "paragraph:601/sentence:2" } };
const allSegments = [...segments, sentence].sort((a, b) => a.sequence_no - b.sequence_no);
const makeEvidence = (name) => {
  const chosen = name === "EV-start" ? [segments[0]] : name === "EV-end" ? [segments[619]] : name === "EV-sentence" ? [sentence] : [segments[600], segments[601]];
  return { evidence_id: name, revision_no: 1, source_id: sourceId, source_title: "同名文献", source_revision_no: 1,
    quote_text: chosen.map(row => row.original_text).join("\n"), context_before: chosen[0].context_before, context_after: chosen.at(-1).context_after,
    full_context_before: chosen[0].context_before ? chosen[0].context_before + "完整上文，".repeat(300) : "",
    full_context_after: chosen.at(-1).context_after ? chosen.at(-1).context_after + "完整下文，".repeat(300) : "", context_complete: true,
    citation_locator: { start: chosen[0].locator, end: chosen.at(-1).locator }, segment_ids: state.missing ? ["SEG-missing"] : chosen.map(row => row.segment_id) };
};
const task = { task_id: taskId, question: "合成报告溯源检查", status: "COMPLETED", control_state: "ACTIVE", source_ids: [sourceId], allowed_actions: [], job_id: null, report_available: true };
const detail = { task_id: taskId, subquestions: [], evidence: [{ evidence_id: "EV-middle", revision_no: 1 }], agent_runs: [], claims: [], audits: [], canonical_claims: [], debate: { critiques: [], evidence_requests: [], retrievals: [], rebuttals: [] }, disputes: [], evidence_gaps: [], stop_evaluations: [], human_reviews: [] };
const streams = new Set();
const json = (res, code, data) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(data)); };
const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1"), path = url.pathname;
  if (path.startsWith("/api/")) {
    state.requests.push(path + url.search);
    if (path === "/api/v1/system/health") return json(res, 200, { state: "READY", preview_corpus: "none" });
    if (path === "/api/v1/local-session/config") return json(res, 200, { development_auto_session: true });
    if (path === "/api/v1/local-session") return json(res, 200, { session_id: "LS-contract" });
    if (path === "/api/v1/local-session/development") return json(res, 200, { csrf_token: "contract-csrf" });
    if (path === "/api/v1/research/capabilities") return json(res, 200, { models: [], unavailable_reason: "model_not_configured" });
    if (path === "/api/v1/research/tasks") return json(res, 200, [task]);
    if (path === `/api/v1/research/tasks/${taskId}`) return json(res, 200, task);
    if (path === `/api/v1/research/tasks/${taskId}/details`) return json(res, 200, detail);
    if (path.endsWith("/events")) { res.writeHead(200, { "Content-Type": "text/event-stream" }); res.write(': ready\n\n'); streams.add(res); req.on("close", () => streams.delete(res)); return; }
    if (path.endsWith("/report")) return json(res, 200, { schema_version: "1", content_hash: "contract", counts: {}, sections: { supported: [{ assertion_text: "合成报告结论", claim_type: "DIRECT_TEXT", audit_verdict: "SUPPORTED", audit_rationale: "合成依据", reason_type: "AUDIT", agent_role: "Classicist", evidence: [{ ...makeEvidence("EV-middle"), evidence_revision_no: 1 }] }] }, open_disputes: [], unresolved_gaps: [], excluded_claim_count: 0 });
    if (path.includes("/exports/")) return json(res, 404, { code: "EXPORT_NOT_FOUND", detail: "未生成" });
    if (path.endsWith("/sources") || path.endsWith("/published-sources")) return json(res, 200, [
      { source_id: "SRC-other", title: "同名文献", source_type: "OTHER", status: "PUBLISHED", data_level: "PUBLIC" },
      { source_id: sourceId, title: "同名文献", source_type: "OTHER", status: "PUBLISHED", data_level: "PUBLIC" },
    ]);
    if (path === `/api/v1/knowledge/sources/${sourceId}`) return json(res, 200, { source_id: sourceId, title: "同名文献", source_type: "OTHER", data_level: "PUBLIC", revisions: [1, 2].map(revision_no => ({ revision_no, file_format: "txt", status: "SEGMENTED" })) });
    if (path.endsWith("/segments")) {
      if (state.failSegments) return json(res, 503, { detail: "合成段落读取故障" });
      const rows = allSegments.filter(row => row.sequence_no > Number(url.searchParams.get("after") ?? -1) && (url.searchParams.get("view") !== "reading" || row.segment_type !== "SENTENCE"));
      return json(res, 200, rows.slice(0, Number(url.searchParams.get("limit") ?? 100)));
    }
    if (path.startsWith("/api/v1/knowledge/evidence/")) {
      if (state.failEvidence) return json(res, 503, { detail: "合成证据读取故障" });
      return json(res, 200, makeEvidence(path.split("/").at(-1)));
    }
    if (path.endsWith("/quality-report")) return json(res, 200, { open_issues: {}, publication_blocked: false });
    if (path.endsWith("/publication-config")) return json(res, 200, { available: false });
    if (path.endsWith("/candidates")) return json(res, 404, { detail: "未提取" });
    return json(res, 200, []);
  }
  try {
    const file = resolve(dist, path === "/" ? "index.html" : `.${decodeURIComponent(path)}`);
    assert.ok(file.startsWith(dist + sep));
    const bytes = await readFile(file);
    res.writeHead(200, { "Content-Type": ({ ".html": "text/html", ".js": "application/javascript", ".css": "text/css" })[extname(file)] || "text/plain" }); res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const origin = `http://127.0.0.1:${server.address().port}`;
const profile = await mkdtemp(join(tmpdir(), "tcm-citation-contract-"));
const browser = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", ["--headless=new", "--no-first-run", "--no-default-browser-check", `--user-data-dir=${profile}`, "--remote-debugging-port=19280", "about:blank"], { windowsHide: true, stdio: "ignore" });
let page;
const evaluate = code => page.eval(code);
const click = async label => {
  const expression = `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)} && !b.disabled)`;
  await until(() => evaluate(`!!(${expression})`), label); await evaluate(`(${expression}).click()`);
};
const navigate = async query => { await page.send("Page.navigate", { url: origin + "/?" + query }); await until(() => evaluate("document.body?.innerText.includes('本机工作区已连接')"), "session"); };
const citationUrl = name => `workspace=knowledge&source=${sourceId}&source_revision=1&citation=${name}&citation_revision=1`;
const checks = [];
try {
  await connect(19280);
  const target = await (await fetch(`http://127.0.0.1:19280/json/new?${encodeURIComponent(origin)}`, { method: "PUT" })).json();
  page = new Cdp(target.webSocketDebuggerUrl);
  await navigate("workspace=search");
  await evaluate(`sessionStorage.setItem('tcm.knowledge.position',JSON.stringify({sourceId:'${sourceId}',revision:2,tab:'publish'}))`);
  for (const [name, before, after] of [["EV-start", "此范围没有上文", "完整下文2"], ["EV-middle", "完整上文600", "完整下文603"], ["EV-end", "完整上文619", "此范围没有下文"]]) {
    await navigate(citationUrl(name));
    await until(() => evaluate("!!document.querySelector('.kwOriginal mark')"), name);
    assert.equal(await evaluate("document.querySelector('.kwSourceTitle select').value"), "1", "old citation must override saved/latest revision");
    const text = await evaluate("document.querySelector('.kwOriginal').innerText");
    assert.ok(text.includes(before)); assert.ok(text.includes(after));
    if (name === "EV-middle") assert.ok(await evaluate("document.querySelector('[aria-label=引用上文] p').textContent.length > 1000 && document.querySelector('[aria-label=引用下文] p').textContent.length > 1000"), "whole long context rendered");
    assert.ok(!text.includes("第 1 页")); assert.ok(!text.includes("physical_lines"));
    assert.equal(await evaluate("document.querySelector('.kwSourceList .selected strong').textContent"), "同名文献");
    assert.match(await evaluate("location.search"), /source=SRC-contract/);
    checks.push(name);
  }
  await navigate(citationUrl("EV-sentence"));
  await until(() => evaluate("document.querySelector('.kwOriginal mark')?.textContent==='只引用第二句。'"), "child sentence");
  assert.equal(await evaluate("document.querySelectorAll('.kwSegmentRow.cited').length"), 1);
  checks.push("sentence target");
  state.failEvidence = true;
  await navigate("workspace=search&evidence=EV-middle&revision=1");
  await until(() => evaluate("document.querySelector('.drawer .error')?.innerText.includes('读取失败')"), "evidence error");
  assert.ok(!(await evaluate("document.querySelector('.drawerBody').innerText")).includes("此范围没有"));
  state.failEvidence = false; await click("重试读取证据");
  await until(() => evaluate("document.querySelector('.drawer .textButton')?.disabled===false"), "evidence retry");
  assert.ok(await evaluate("document.querySelector('.drawer .contextText').textContent.length > 1000"), "drawer renders whole long context");
  checks.push("evidence failure/retry");
  state.failSegments = true;
  await click("打开来源文献");
  await until(() => evaluate("document.querySelector('.kwCitationNavigation')?.innerText.includes('合成段落读取故障')"), "segment error");
  assert.equal(await evaluate("document.querySelectorAll('.kwOriginal mark').length"), 0);
  state.failSegments = false; await click("重试定位引用");
  await until(() => evaluate("document.querySelectorAll('.kwOriginal mark').length===2"), "segment retry");
  checks.push("segment failure/retry");
  state.missing = true;
  await navigate(citationUrl("EV-middle"));
  await until(() => evaluate("document.querySelector('.kwCitationNavigation')?.innerText.includes('未在此来源修订')"), "missing target");
  assert.equal(await evaluate("document.querySelectorAll('.kwOriginal mark').length"), 0);
  state.missing = false;
  checks.push("missing target blocks false focus");
  // Preserve a long-document reading position even when a citation uses the
  // same source but a different revision and an unloaded paragraph range.
  await navigate("workspace=knowledge&source=" + sourceId);
  await evaluate(`sessionStorage.setItem('tcm.knowledge.position',JSON.stringify({sourceId:'${sourceId}',revision:2,tab:'sources',focusedSegment:'SEG-550',through:599,structureView:false}))`);
  await page.send("Page.reload");
  await until(() => evaluate("document.querySelector('.kwSegmentRow.selected')?.innerText.includes('逻辑段551')"), "original reading restored");
  await navigate(`workspace=knowledge&source=${sourceId}&evidence=EV-middle&revision=1`);
  await until(() => evaluate("document.querySelector('.drawer .textButton')?.disabled===false"), "knowledge citation");
  await click("打开来源文献");
  await until(() => evaluate("document.querySelectorAll('.kwOriginal mark').length===2"), "knowledge target");
  await click("返回引用处");
  await until(() => evaluate("document.querySelector('.drawer .textButton')?.disabled===false && document.querySelector('.kwSourceTitle select')?.value==='2'"), "knowledge return");
  await until(() => evaluate("document.querySelector('.kwSegmentRow.selected')?.innerText.includes('逻辑段551')"), "reading paragraph preserved");
  checks.push("return original revision and long-document paragraph");
  await navigate("workspace=research");
  await until(() => evaluate("!!document.querySelector('.taskList button')"), "task list");
  await evaluate("document.querySelector('.taskList button').click()");
  await until(() => evaluate("!!document.querySelector('.researchTabs')"), "task selected");
  await click("研究报告");
  await until(() => evaluate("!!document.querySelector('.refChip')"), "report citation");
  await evaluate("document.querySelector('.refChip').click()");
  await until(() => evaluate("document.querySelector('.drawer .textButton')?.disabled===false"), "report evidence");
  await click("打开来源文献");
  await until(() => evaluate("document.querySelectorAll('.kwOriginal mark').length===2"), "report target");
  await click("返回引用处");
  await until(() => evaluate("!!document.querySelector('.drawer .textButton')"), "report return");
  assert.match(await evaluate("location.search"), /workspace=research/);
  assert.equal(await evaluate("document.querySelector('.researchTabs [aria-current=page]').textContent"), "研究报告");
  assert.ok((await evaluate("document.querySelector('.researchWorkspace').innerText")).includes("合成报告结论"));
  checks.push("report citation and return to selected task/tab");
  await writeFile(resolve(import.meta.dirname, "../../docs/acceptance-artifacts/vib89/contracts-result.json"), JSON.stringify({ synthetic: true, checks, model_calls: 0 }, null, 2));
  console.log("PASS: " + checks.join("; "));
} catch (error) {
  console.error("Completed checks:", checks.join("; "));
  if (page) console.error(await evaluate("document.body?.innerText"));
  throw error;
} finally {
  page?.close(); browser.kill(); for (const stream of streams) stream.end(); server.closeAllConnections(); server.close();
}
