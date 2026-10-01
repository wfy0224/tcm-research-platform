/** Shared error contract: field validation stays useful at the workflow step. */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const code = ts.transpileModule(await readFile(new URL("../src/api.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { requestJson, apiErrorText } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
async function rejects(status, body, pattern) {
  globalThis.fetch = async () => Response.json(body, { status });
  await assert.rejects(() => requestJson("/test"), error => error.status === status && pattern.test(error.message));
}
await rejects(422, { detail: [{ loc: ["body", "metadata", "title"], msg: "Field required" }] }, /文献标题.*缺失/);
await rejects(400, { code: "INVALID_KNOWLEDGE_COMMAND", detail: "evidence range must be contiguous" }, /连续原文段落/);
await rejects(403, { code: "CSRF_INVALID" }, /会话校验失效/);
await rejects(409, { detail: "reviewed knowledge is immutable" }, /reviewed knowledge is immutable/);
await rejects(503, {}, /503/);
assert.match(apiErrorText(new TypeError("Failed to fetch")), /服务连接中断/);
console.log("API errors passed: field location, evidence range, session, conflict, server failure, connection failure.");
