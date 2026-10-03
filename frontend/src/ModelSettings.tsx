import { useEffect, useState } from "react";
import { apiErrorText, postJson, requestJson } from "./api";
import "./modelSettings.css";

type Choice = { model_version: string; label: string };
type Config = { retrieval_provider: string; embedding_model: string; rerank_model: string; workspace_id: string; region: string; models: Choice[]; default_model: string; providers: { id: string; label: string; credential_configured: boolean }[] };
const presets: Record<string, string[]> = {
  deepseek: ["deepseek-flash", "deepseek-v4-pro"],
  siliconflow: ["deepseek-ai/DeepSeek-V3.2", "Pro/deepseek-ai/DeepSeek-R1", "Qwen/Qwen3-8B", "Qwen/Qwen3-32B", "Qwen/Qwen3-235B-A22B-Instruct-2507"],
};

export default function ModelSettings({ csrf, onSaved, onClose }: {
  csrf: string; onSaved: () => Promise<void>; onClose: () => void;
}) {
  const [config, setConfig] = useState<Config | null>(null);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [models, setModels] = useState<Choice[]>([]);
  const [defaultModel, setDefaultModel] = useState("");
  const [provider, setProvider] = useState("deepseek");
  const [name, setName] = useState("deepseek-flash");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void requestJson<Config>("/api/v1/research/model-settings").then(value => {
      if (active) { setConfig(value); setModels(value.models); setDefaultModel(value.default_model); }
    }).catch(cause => { if (active) setError(apiErrorText(cause)); });
    return () => { active = false; };
  }, []);

  function add() {
    const model = name.trim();
    const route = `${provider}/${model}`;
    setError(""); setMessage("");
    if (!model || /\s/.test(model) || route.length > 200) { setError("请填写有效的模型名称。"); return; }
    if (models.some(item => item.model_version === route)) { setError("这个模型已在列表中。"); return; }
    if (provider === "deepseek" && !presets.deepseek.includes(model)) { setError("请选择 DeepSeek 官方 Flash 或 V4 Pro 模型。"); return; }
    setModels(items => [...items, { model_version: route, label: `${provider === "deepseek" ? "DeepSeek 官方" : "硅基流动"} · ${model}` }]);
  }
  async function save() {
    setBusy(true); setError(""); setMessage("");
    try {
      const saved = await postJson<Config>("/api/v1/research/model-settings", {
        models: models.map(item => item.model_version), default_model: defaultModel, api_keys: apiKeys,
        retrieval_provider: config!.retrieval_provider, embedding_model: config!.embedding_model,
        rerank_model: config!.rerank_model, workspace_id: config!.workspace_id, region: config!.region,
      }, csrf);
      setApiKeys({}); setConfig(saved); setModels(saved.models); setDefaultModel(saved.default_model);
      await onSaved(); setMessage("已保存到数据库，后续任务使用新配置。");
    } catch (cause) { setError(apiErrorText(cause)); }
    finally { setBusy(false); }
  }
  return <section className="panel modelSettings" aria-labelledby="model-settings-title">
    <div className="panelHead"><div><span className="sectionLabel">研究配置</span><h3 id="model-settings-title">模型设置</h3></div><button type="button" onClick={onClose} disabled={busy}>返回研究</button></div>
    <p className="muted">选择提供商，添加你要用的模型，再保存。这里仅管理模型选项，不执行研究。</p>
    {error && <p className="workspaceAlert error" role="alert">{error}</p>}
    {message && <p className="workspaceAlert" role="status">{message}</p>}
    {!config ? <p>正在读取模型设置…</p> : <>
      <div className="modelProviderStatus">{config.providers.map(item => <p key={item.id}><strong>{item.label}</strong><span>{item.credential_configured ? "已连接现有 API 凭据" : "尚未连接 API 凭据"}</span></p>)}</div>
      <fieldset className="configuredModels"><legend>提供商 API 密钥</legend>
        {config.providers.map(item => <label key={item.id}>{item.label}<input type="password" autoComplete="new-password" disabled={busy} value={apiKeys[item.id] || ""} placeholder={item.credential_configured ? "已配置，留空保留；填写可替换" : "输入 API 密钥"} onChange={event => setApiKeys(keys => ({ ...keys, [item.id]: event.target.value }))} /></label>)}
      </fieldset>
      <fieldset className="configuredModels"><legend>知识检索模型</legend>
        <label>提供商<select disabled={busy} value={config.retrieval_provider} onChange={event => setConfig({ ...config, retrieval_provider: event.target.value })}><option value="siliconflow">硅基流动</option><option value="aliyun">阿里云</option></select></label>
        {([['embedding_model', '向量模型'], ['rerank_model', '重排模型'], ...(config.retrieval_provider === 'aliyun' ? [['workspace_id', '工作空间 ID'], ['region', '区域']] : [])] as ["embedding_model" | "rerank_model" | "workspace_id" | "region", string][]).map(([key, label]) => <label key={key}>{label}<input disabled={busy} value={config[key]} onChange={event => setConfig({ ...config, [key]: event.target.value })} /></label>)}
        <p className="muted">更换向量模型后须重新构建对应向量索引。密钥保存后不回显。</p>
      </fieldset>      <div className="modelAddForm"><label>提供商<select value={provider} disabled={busy} onChange={event => { setProvider(event.target.value); setName(presets[event.target.value][0]); }}><option value="deepseek">DeepSeek 官方</option><option value="siliconflow">硅基流动</option></select></label>
        <label>模型名称<input list="model-presets" value={name} disabled={busy} onChange={event => setName(event.target.value)} placeholder="选择或填写模型名称" /><datalist id="model-presets">{presets[provider].map(model => <option key={model} value={model} />)}</datalist></label>
        <button type="button" disabled={busy || !name.trim()} onClick={add}>添加模型</button></div>
      <fieldset className="configuredModels"><legend>可选模型 · {models.length} 个</legend>
        {!models.length && <p className="muted">列表为空，请先添加模型。</p>}
        {models.map(item => <div key={item.model_version}><label><input type="radio" name="default-research-model" checked={defaultModel === item.model_version} disabled={busy} onChange={() => setDefaultModel(item.model_version)} /><span>{item.label}<small>{defaultModel === item.model_version ? "默认模型" : "点击设为默认"}</small></span></label><button type="button" disabled={busy} onClick={() => { setModels(items => items.filter(model => model.model_version !== item.model_version)); if (defaultModel === item.model_version) setDefaultModel(""); setMessage(""); }}>移除</button></div>)}
      </fieldset>
      <div className="modelSettingsActions"><button type="button" disabled={busy || !csrf} onClick={() => void save()}>{busy ? "保存中…" : "保存模型设置"}</button><button type="button" disabled={busy || !defaultModel} onClick={() => setDefaultModel("")}>每次手动选择</button></div>
      <p className="muted">列表为可编辑候选项；模型调用与账户可用性未测试。已有任务的模型选择不会随默认项改变。</p>
    </>}
  </section>;
}
