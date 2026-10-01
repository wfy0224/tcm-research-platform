import { useEffect, useState } from "react";
import { apiErrorText, postJson, requestJson } from "./api";
import "./modelSettings.css";

type Choice = { model_version: string; label: string };
type Config = { models: Choice[]; default_model: string; providers: { id: string; label: string; credential_configured: boolean }[] };
const presets: Record<string, string[]> = {
  deepseek: ["deepseek-flash", "deepseek-v4-pro"],
  siliconflow: ["deepseek-ai/DeepSeek-V3.2", "Pro/deepseek-ai/DeepSeek-R1", "Qwen/Qwen3-8B", "Qwen/Qwen3-32B", "Qwen/Qwen3-235B-A22B-Instruct-2507"],
};

export default function ModelSettings({ csrf, onSaved, onClose }: {
  csrf: string; onSaved: () => Promise<void>; onClose: () => void;
}) {
  const [config, setConfig] = useState<Config | null>(null);
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
        models: models.map(item => item.model_version), default_model: defaultModel,
      }, csrf);
      setConfig(saved); setModels(saved.models); setDefaultModel(saved.default_model);
      await onSaved(); setMessage("已保存。研究模型列表已更新，重启后保留。");
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
      <div className="modelAddForm"><label>提供商<select value={provider} disabled={busy} onChange={event => { setProvider(event.target.value); setName(presets[event.target.value][0]); }}><option value="deepseek">DeepSeek 官方</option><option value="siliconflow">硅基流动</option></select></label>
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
