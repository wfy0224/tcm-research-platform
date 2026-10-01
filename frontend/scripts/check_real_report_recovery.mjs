/** Capture the real user's saved report revision and exports; never create a study. */
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const origin = "http://127.0.0.1:18067";
const taskId = "RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940";
const directory = resolve(import.meta.dirname, process.env.TCM_REPORT_CAPTURE_DIR
  || "../../docs/acceptance-artifacts/report-recovery");
await mkdir(directory, { recursive: true });
const sessionResponse = await fetch(origin + "/api/v1/local-session/development", {
  method: "POST", headers: { Origin: origin },
});
assert.ok(sessionResponse.ok);
const cookie = sessionResponse.headers.get("set-cookie").split(";")[0];
const { csrf_token: csrf } = await sessionResponse.json();
async function api(path, body) {
  const response = await fetch(origin + path, {
    method: body === undefined ? "GET" : "POST",
    headers: { Cookie: cookie, Origin: origin, ...(body === undefined ? {} : {
      "Content-Type": "application/json", "X-CSRF-Token": csrf,
      "Idempotency-Key": crypto.randomUUID(),
    }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(30000),
  });
  const value = await response.json();
  assert.ok(response.ok, JSON.stringify(value));
  return value;
}
const base = `/api/v1/research/tasks/${taskId}`;
const task = await api(base);
const report = await api(base + "/report");
const details = await api(base + "/details");
assert.equal(report.schema_version, "research-report/v3");
assert.equal(details.debate.critiques.length, 5);
assert.equal(details.debate.rebuttals.length, 5);
assert.equal(details.claims.length, 9);
assert.ok(task.report_available && task.allowed_actions.includes("export"));
assert.equal(report.counts.UNRESOLVED, 2);
if (report.review_status === "NEEDS_REVISION") {
  assert.ok(report.answer.review_issues.length > 0);
  assert.ok(task.allowed_actions.includes("revise_report"));
} else {
  assert.equal(report.review_status, "ACCEPTED");
  assert.deepEqual(report.answer.review_issues, []);
}
const prefix = `revision-${report.revision_no}`;
await writeFile(resolve(directory, `${prefix}.json`), JSON.stringify({ task, report, details }, null, 2));
for (const format of ["markdown", "docx"]) {
  await api(base + `/exports/${format}`, {});
  let exported;
  do {
    exported = await api(base + `/exports/${format}`);
    assert.notEqual(exported.status, "FAILED");
    if (!exported.download_url) await new Promise(r => setTimeout(r, 1000));
  } while (!exported.download_url);
  const download = await fetch(origin + exported.download_url, { headers: { Cookie: cookie } });
  assert.ok(download.ok);
  const bytes = Buffer.from(await download.arrayBuffer());
  if (format === "markdown") {
    const text = bytes.toString("utf8");
    assert.ok(text.includes(report.question));
    if (report.review_status === "NEEDS_REVISION") assert.ok(text.includes("草稿未通过复核"));
  } else assert.equal(bytes.subarray(0, 2).toString(), "PK");
  await writeFile(resolve(directory, `${prefix}.${format === "markdown" ? "md" : format}`), bytes);
}
console.log(JSON.stringify({ task_id: taskId, revision_no: report.revision_no,
  review_status: report.review_status, critiques: 5, rebuttals: 5,
  model: details.agent_runs[0].model_version, content_hash: report.content_hash }));
