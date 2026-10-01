/** Local candidate catalog; loading the list never contacts a provider. */
export function loadWorkspaceModelCatalog(config) {
  const routes = [];
  if (config.env.DEEPSEEK_API_KEY) {
    routes.push("deepseek/deepseek-flash", "deepseek/deepseek-v4-pro");
  }
  if (config.env.SILICONFLOW_API_KEY) {
    for (const name of ["deepseek-ai/DeepSeek-V3.2", "Pro/deepseek-ai/DeepSeek-R1",
      "Qwen/Qwen3-8B", "Qwen/Qwen3-32B", "Qwen/Qwen3-235B-A22B-Instruct-2507"]) {
      routes.push(`siliconflow/${name}`);
    }
  }
  if (config.modelVersion) routes.push(config.modelVersion);
  config.env.TCM_RESEARCH_MODELS = JSON.stringify([...new Set(routes)]);
  if (routes.length) {
    config.args.push("-e", "TCM_RESEARCH_MODELS");
    for (const name of ["SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY"]) {
      if (config.env[name] && !config.args.includes(name)) config.args.push("-e", name);
    }
  }
  return config;
}
