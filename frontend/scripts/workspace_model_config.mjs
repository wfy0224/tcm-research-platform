/** Development-container configuration. Secrets remain in the inherited environment. */
export function workspaceModelConfig(environment) {
  const env = { ...environment };
  const provider = (env.TCM_RESEARCH_PROVIDER || (env.DEEPSEEK_API_KEY ? "deepseek" : "siliconflow")).trim().toLowerCase();
  if (!["siliconflow", "deepseek"].includes(provider)) throw new Error("Unsupported research model provider");
  const keyName = provider === "deepseek" ? "DEEPSEEK_API_KEY" : "SILICONFLOW_API_KEY";
  const model = (env.TCM_RESEARCH_MODEL || (env[keyName]?.trim()
    ? (provider === "deepseek" ? "deepseek-flash" : "Qwen/Qwen3-8B") : "")).trim();
  if (!model) return { env, args: [], modelVersion: null };
  if (model.length >= 200 || (provider === "deepseek" && !["deepseek-flash", "deepseek-v4-pro"].includes(model))) {
    throw new Error("Invalid research model route");
  }
  env.TCM_RESEARCH_PROVIDER = provider;
  env.TCM_RESEARCH_MODEL = model;
  // This Linux development container has no OS credential manager.
  env.TCM_ALLOW_ENV_API_KEYS = env.TCM_ALLOW_ENV_API_KEYS || "1";
  env.TCM_OUTBOUND_MODE = env.TCM_OUTBOUND_MODE || "LOCAL_ONLY";
  const names = ["TCM_RESEARCH_MODEL", "TCM_RESEARCH_PROVIDER", "TCM_OUTBOUND_MODE",
    "TCM_ALLOW_ENV_API_KEYS", keyName, ...["TCM_PUBLICATION_STRATEGY", "TCM_MODEL_PROVIDER",
      "TCM_EMBEDDING_MODEL", "TCM_RERANK_MODEL", "TCM_DASHSCOPE_WORKSPACE_ID",
      "TCM_DASHSCOPE_REGION", "TCM_MODEL_COMPLETION_TIMEOUT_SECONDS"].filter(name => env[name])];
  return { env, args: names.flatMap(name => ["-e", name]), modelVersion: `${provider}/${model}` };
}
