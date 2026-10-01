/** No model calls: verify the running workspace offers a configured research route. */
import assert from "node:assert/strict";
const origin = process.env.TCM_WORKSPACE_ORIGIN || "http://127.0.0.1:18067";
try {
const issued = await fetch(`${origin}/api/v1/local-session/development`, {
  method: "POST", headers: { Origin: origin },
});
assert.equal(issued.status, 200, "development workspace session must be available");
const cookie = issued.headers.getSetCookie().map(value => value.split(";")[0]).join("; ");
const response = await fetch(`${origin}/api/v1/research/capabilities`, { headers: { Cookie: cookie } });
assert.equal(response.status, 200);
const result = await response.json();
console.log(JSON.stringify({ models: result.models, unavailable_reason: result.unavailable_reason, real_model_calls: 0 }));
assert.ok(result.models.length > 0, result.unavailable_reason || "no configured research route");
assert.equal(result.unavailable_reason, null);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
