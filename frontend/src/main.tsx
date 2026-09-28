import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Health = {
  state: "READY" | "DEGRADED" | "MAINTENANCE" | "NOT_READY";
  database: string;
  schema: string;
  blob_store: string;
  preview_corpus: "none" | "shanghanlun_taiyang_upper";
};

type Evidence = {
  evidence_id: string;
  evidence_revision_no: number;
  source_title: string;
  source_revision_no: number;
  quote_text: string;
  context_before: string;
  context_after: string;
  citation_locator: Record<string, unknown>;
  segment_ids: string[];
  matched_channels: string[];
  rerank_score: number | null;
};

const channelNames: Record<string, string> = {
  exact: "原文匹配", fts: "全文检索", vector: "语义检索",
};

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Evidence[]>([]);
  const [selected, setSelected] = useState<Evidence | null>(null);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function refresh() {
      try {
        const response = await fetch("/api/v1/system/health");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as Health;
        if (mounted) {
          setHealth(data);
          setHealthError(null);
        }
      } catch (cause) {
        if (mounted) setHealthError(cause instanceof Error ? cause.message : "连接失败");
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 10_000);
    return () => { mounted = false; window.clearInterval(timer); };
  }, []);

  async function search(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = query.trim();
    if (!value || searching) return;
    setSearching(true);
    setSearchError(null);
    setSelected(null);
    try {
      const params = new URLSearchParams({ query: value, limit: "10" });
      const response = await fetch(`/api/v1/retrieval/search?${params}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
      setResults(data as Evidence[]);
      setSearched(true);
    } catch (cause) {
      setResults([]);
      setSearched(true);
      setSearchError(cause instanceof Error ? cause.message : "检索失败");
    } finally {
      setSearching(false);
    }
  }

  return (
    <main className="shell">
      <header className="intro">
        <span className="eyebrow">中医知识研究 · 第一阶段</span>
        <h1>从原文追溯每一条证据</h1>
        <p>检索已审核、已发布的知识证据。结果融合原文、全文和语义匹配，并显示来源与精确引用位置。</p>
        {health?.preview_corpus === "shanghanlun_taiyang_upper" && <p className="demoNotice" role="note">
          真实模型检索预览：当前收录公版《傷寒論》太阳病上篇 29 条原文；来源转写与自动审核尚未经本项目专家复核。无关问题也可能返回候选，请核对原文。
        </p>}
      </header>

      <section className="panel searchPanel" aria-labelledby="search-title">
        <div className="panelHead">
          <div><span className="sectionLabel">知识检索</span><h2 id="search-title">寻找相关原文</h2></div>
          <span className="modelNote">云端向量 · 云端重排</span>
        </div>
        <form className="searchForm" onSubmit={(event) => void search(event)}>
          <label className="srOnly" htmlFor="knowledge-query">检索问题或关键词</label>
          <input id="knowledge-query" value={query} onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：太阳病的脉象" maxLength={2000} />
          <button type="submit" disabled={searching || !query.trim()}>
            {searching ? "检索中…" : "检索证据"}
          </button>
        </form>
        <p className="hint">检索词会发送给已配置的云端模型，用于语义匹配与重排。</p>
        {searchError && <p className="error" role="alert">{searchError}</p>}
      </section>

      {searched && !searchError && (
        <section className="results" aria-live="polite">
          <div className="resultsHead"><h2>检索结果</h2><span>{results.length} 条已发布证据</span></div>
          {results.length === 0 ? <p className="empty">当前知识版本中没有找到匹配证据。</p> : (
            <div className="resultList">
              {results.map((item) => (
                <article className="resultCard" key={`${item.evidence_id}:${item.evidence_revision_no}`}>
                  <div className="resultMeta">
                    <strong>{item.source_title}</strong><span>来源修订 {item.source_revision_no}</span>
                  </div>
                  <blockquote>{item.quote_text}</blockquote>
                  <div className="resultFoot">
                    <div className="channels">
                      {item.matched_channels.map((name) => <span key={name}>{channelNames[name] ?? name}</span>)}
                    </div>
                    <button className="textButton" type="button" onClick={() => setSelected(item)}>
                      查看证据详情
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="panel statusPanel" aria-live="polite">
        <div className="panelHead">
          <h2>本地服务状态</h2>
          <span className={`badge ${health?.state === "READY" ? "ready" : "pending"}`}>
            {healthError ? "连接中断" : (health?.state ?? "检查中")}
          </span>
        </div>
        {healthError && <p className="error">无法连接本地 API：{healthError}</p>}
        <dl>
          <div><dt>PostgreSQL</dt><dd>{health?.database ?? "—"}</dd></div>
          <div><dt>数据库结构</dt><dd>{health?.schema ?? "—"}</dd></div>
          <div><dt>文件存储</dt><dd>{health?.blob_store ?? "—"}</dd></div>
        </dl>
      </section>

      {selected && (
        <div className="drawerBackdrop" onClick={() => setSelected(null)}>
          <aside className="drawer" role="dialog" aria-modal="true" aria-label="证据详情"
            onClick={(event) => event.stopPropagation()}>
            <div className="drawerHead">
              <div><span className="sectionLabel">Evidence</span><h2>证据详情</h2></div>
              <button className="closeButton" type="button" aria-label="关闭证据详情"
                onClick={() => setSelected(null)}>×</button>
            </div>
            <div className="drawerBody">
              <h3>{selected.source_title}</h3>
              <p className="muted">来源修订 {selected.source_revision_no}</p>
              <blockquote className="drawerQuote">{selected.quote_text}</blockquote>
              <h4>原文上下文</h4>
              <p className="contextText">{selected.context_before || "无前文"}</p>
              <p className="contextText">{selected.context_after || "无后文"}</p>
              <h4>引用定位</h4>
              <pre>{JSON.stringify(selected.citation_locator, null, 2)}</pre>
              <h4>精确修订</h4>
              <p className="idText">证据：{selected.evidence_id} · 修订 {selected.evidence_revision_no}</p>
              {selected.segment_ids.map((id) => <p className="idText" key={id}>段落：{id}</p>)}
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>,
);
