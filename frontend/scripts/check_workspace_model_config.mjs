import assert from "node:assert/strict";
import { workspaceModelConfig } from "./workspace_model_config.mjs";

const inherited = { SILICONFLOW_API_KEY: "test-only-secret" };
const silicon = workspaceModelConfig(inherited);
assert.equal(silicon.modelVersion, "siliconflow/Qwen/Qwen3-8B");
assert.equal(silicon.env.TCM_RESEARCH_MODEL, "Qwen/Qwen3-8B");
assert.equal(silicon.env.TCM_ALLOW_ENV_API_KEYS, "1");
assert.equal(silicon.env.TCM_OUTBOUND_MODE, "LOCAL_ONLY");
assert.ok(silicon.args.includes("SILICONFLOW_API_KEY"));
assert.ok(!silicon.args.includes("DEEPSEEK_API_KEY"));
assert.ok(!JSON.stringify(silicon.args).includes(inherited.SILICONFLOW_API_KEY));
assert.equal(inherited.TCM_RESEARCH_MODEL, undefined);
const deepseek = workspaceModelConfig({ ...inherited, DEEPSEEK_API_KEY: "other-test-secret", TCM_RESEARCH_PROVIDER: "deepseek",
  TCM_OUTBOUND_MODE: "CLOUD_ALLOWED", TCM_ALLOW_ENV_API_KEYS: "0" });
assert.equal(deepseek.modelVersion, "deepseek/deepseek-flash");
assert.ok(deepseek.args.includes("DEEPSEEK_API_KEY"));
assert.ok(!deepseek.args.includes("SILICONFLOW_API_KEY"));
assert.equal(deepseek.env.TCM_OUTBOUND_MODE, "CLOUD_ALLOWED");
assert.equal(deepseek.env.TCM_ALLOW_ENV_API_KEYS, "0");
assert.equal(workspaceModelConfig({}).modelVersion, null);
assert.equal(workspaceModelConfig({ ...inherited, TCM_RESEARCH_MODEL: "Qwen/Qwen3-32B" }).env.TCM_RESEARCH_MODEL, "Qwen/Qwen3-32B");
assert.throws(() => workspaceModelConfig({ TCM_RESEARCH_PROVIDER: "unknown" }));
console.log("workspace model defaults, provider credentials, explicit overrides and local policy: passed");
