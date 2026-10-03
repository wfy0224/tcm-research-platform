import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import ResearchWorkspace from "./ResearchWorkspace";
import KnowledgeWorkspace from "./KnowledgeWorkspace";
import EvidenceDrawer from "./EvidenceDrawer";
import { apiErrorText, postJson, requestJson } from "./api";
import type { EvidenceRef } from "./api";
import { sourceCitationFromUrl } from "./citation";
import type { SourceCitation } from "./citation";
import { readingText } from "./knowledgeSelection";
import "./theme.css";

type Health = {
  state: "READY" | "DEGRADED" | "MAINTENANCE" | "NOT_READY";
  database: string;
  schema: string;
  blob_store: string;
  preview_corpus: "none" | "shanghanlun_taiyang_upper";
};

type Evidence = {
  source_id: string;
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
  structured: "结构检索", relation: "关系检索", rerank: "云端重排",
};

type SearchResponse = {
  query_text: string;
  normalized_query: string;
  mode: "LOCAL" | "HYBRID" | "DEGRADED";
  reasons: string[];
  channels: string[];
  results: Evidence[];
};

const reasonNames: Record<string, string> = {
  local_requested: "已选择本地检索。",
  remote_query_not_authorized: "本次查询未授权云端外发，使用本地检索。",
  model_not_configured: "未配置模型密钥，已降级为本地检索。",
  credential_unavailable: "无法读取模型密钥，已降级为本地检索。",
  model_configuration_error: "云模型配置不可用，已降级为本地检索。",
  outbound_policy_blocked: "外发策略禁止本次云调用，使用已完成的检索通道。",
  embedding_unavailable: "云端语义检索失败，已降级为本地检索。",
  rerank_unavailable: "云端重排失败，按已完成通道的融合得分排序。",
};

function NavigationIcon({ kind }: { kind: "knowledge" | "search" | "research" }) {
  const paths = { knowledge: "M4 4h12a2 2 0 0 1 2 2v14H6a2 2 0 0 1-2-2V4zm0 12h14M8 8h6M8 11h6", search: "M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0", research: "M4 20V9m7 11V4m7 16v-7M2 20h20" };
  return <svg className="navIcon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[kind]} /></svg>;
}

function App() {
  const [workspace, setWorkspace] = useState<"knowledge" | "search" | "research">(() => {
    const page = new URLSearchParams(location.search).get("workspace");
    return page === "search" || page === "research" ? page : "knowledge";
  });
  const [sessionActive, setSessionActive] = useState(false);
  const [csrf, setCsrf] = useState(() => sessionStorage.getItem("tcm.local.csrf") || "");
  const [sourceId, setSourceId] = useState(() => new URLSearchParams(location.search).get("source") || "");
  const [sourceCitation, setSourceCitation] = useState(() => sourceCitationFromUrl(new URLSearchParams(location.search)));
  const [researchVisited, setResearchVisited] = useState(workspace === "research");
  const [researchSourceId, setResearchSourceId] = useState(sourceId);
  const citationScroll = useRef(0);
  const [selectedRef, setSelectedRef] = useState<EvidenceRef | null>(() => {
    const params = new URLSearchParams(location.search), revision = Number(params.get("revision"));
    return params.get("evidence") && Number.isInteger(revision) && revision > 0
      ? { evidence_id: params.get("evidence")!, revision_no: revision } : null;
  });
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Evidence[]>([]);
  const [selected, setSelected] = useState<Evidence | null>(null);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [allowRemoteQuery, setAllowRemoteQuery] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchStatus, setSearchStatus] = useState<SearchResponse | null>(null);
  const [retrievalCapability, setRetrievalCapability] = useState<{ cloud_ready: boolean; reason: string | null; embedding_model: string | null; rerank_model: string | null } | null>(null);
  useEffect(() => { if (workspace !== "search") return; const controller = new AbortController(); void requestJson<typeof retrievalCapability>("/api/v1/retrieval/capabilities", { signal: controller.signal }).then(setRetrievalCapability).catch(() => { if (!controller.signal.aborted) setRetrievalCapability(null); }); return () => controller.abort(); }, [workspace, sessionActive]);

  const navigate = useCallback((page: "knowledge" | "search" | "research", source?: string) => {
    setWorkspace(page);
    setSourceCitation(undefined);
    if (page === "research") { setResearchVisited(true); if (source !== undefined) setResearchSourceId(source); }
    if (source !== undefined) setSourceId(source);
    const url = new URL(location.href); url.searchParams.set("workspace", page);
    for (const key of ["citation", "citation_revision", "source_revision"]) url.searchParams.delete(key);
    if (source) url.searchParams.set("source", source);
    else if (source === "") url.searchParams.delete("source");
    history.pushState({}, "", url);
  }, []);
  const openSourceCitation = useCallback((target: SourceCitation) => {
    citationScroll.current = window.scrollY;
    setSourceCitation(target); setSourceId(target.source_id); setWorkspace("knowledge");
    setSelectedRef(null); setSelected(null);
    const url = new URL(location.href);
    url.searchParams.set("workspace", "knowledge"); url.searchParams.set("source", target.source_id);
    url.searchParams.set("source_revision", String(target.source_revision_no));
    url.searchParams.set("citation", target.evidence.evidence_id); url.searchParams.set("citation_revision", String(target.evidence.revision_no));
    url.searchParams.delete("evidence"); url.searchParams.delete("revision");
    history.pushState({ citationReturn: true }, "", url);
  }, []);
  const returnFromCitation = useCallback(() => {
    if (history.state?.citationReturn) history.back();
    else navigate("search");
  }, [navigate]);
  const openEvidence = useCallback((ref: EvidenceRef) => {
    setSelected(null); setSelectedRef(ref);
    const url = new URL(location.href); url.searchParams.set("evidence", ref.evidence_id);
    url.searchParams.set("revision", String(ref.revision_no)); history.replaceState({}, "", url);
  }, []);
  const closeEvidence = useCallback(() => {
    setSelected(null); setSelectedRef(null);
    const url = new URL(location.href); url.searchParams.delete("evidence"); url.searchParams.delete("revision");
    history.replaceState({}, "", url);
  }, []);
  useEffect(() => {
    const popstate = () => {
      const params = new URLSearchParams(location.search), page = params.get("workspace"), revision = Number(params.get("revision"));
      setWorkspace(page === "search" || page === "research" ? page : "knowledge");
      const citation = sourceCitationFromUrl(params);
      setSourceCitation(citation);
      if (page === "research") { setResearchVisited(true); setResearchSourceId(params.get("source") || ""); }
      setSourceId(params.get("source") || ""); setSelected(null);
      setSelectedRef(params.get("evidence") && revision > 0 ? { evidence_id: params.get("evidence")!, revision_no: revision } : null);
      if (!citation) requestAnimationFrame(() => window.scrollTo({ top: citationScroll.current }));
    };
    window.addEventListener("popstate", popstate);
    return () => window.removeEventListener("popstate", popstate);
  }, []);

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
    const value = query;
    if (!value.trim() || searching) return;
    setSearching(true);
    setSearchError(null);
    closeEvidence();
    setSearchStatus(null);
    try {
      const params = new URLSearchParams({ query: value, limit: "10",
        allow_remote_query: String(allowRemoteQuery) });
      const response = await fetch(`/api/v1/retrieval/query?${params}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
      const result = data as SearchResponse;
      setResults(result.results);
      setSearchStatus(result);
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
    <main className="shell appShell">
      <aside className="appSidebar">
      <div className="appHeader"><span className="brand"><span className="brandMark" aria-hidden="true">本</span><span>中医文献研究<span className="brandSub">文献与理论研究空间</span></span></span></div>
      <p className="navSectionLabel">研究空间</p>
      <nav className="workspaceNav" aria-label="工作区">
        <button aria-current={workspace === "knowledge" ? "page" : undefined} onClick={() => navigate("knowledge")}><NavigationIcon kind="knowledge" />知识库</button>
        <button aria-current={workspace === "search" ? "page" : undefined} onClick={() => navigate("search")}><NavigationIcon kind="search" />证据检索</button>
        <button aria-current={workspace === "research" ? "page" : undefined} onClick={() => navigate("research")}><NavigationIcon kind="research" />理论研究</button>
      </nav>
      <div className="sidebarFooter"><span className="sidebarMode">本地工作空间</span>
        <span className={`badge ${(health?.state === "READY" || health?.state === "DEGRADED") && !healthError ? "ready" : "pending"}`}>{healthError ? "服务连接中断" : health?.state === "READY" ? "本地服务已就绪" : health?.state === "DEGRADED" ? "本地服务可用" : "检查本地服务"}</span></div>
      </aside>
      <div className="appContent">
      <header className="pageHeader">
        <div><span className="pageBreadcrumb">研究空间 / {workspace === "knowledge" ? "文献管理" : workspace === "search" ? "证据检索" : "理论研究"}</span>
        <h1>{workspace === "knowledge" ? "知识库" : workspace === "search" ? "证据检索" : "理论研究"}</h1>
        <p>{workspace === "knowledge" ? "阅读原文，核对证据，整理可追溯的知识。" : workspace === "search" ? "查找已入库的证据，回到文献核对依据。" : "提出问题，选择资料，查看研究过程与报告。"}</p></div>
        <div className="pageConnection"><SessionConnection onConnected={(token) => { setCsrf(token); setSessionActive(true); }} onSession={(active) => setSessionActive(active)} /></div>
      </header>
        {health?.preview_corpus === "shanghanlun_taiyang_upper" && <p className="demoNotice" role="note">
          真实模型检索预览：当前收录公版《傷寒論》太阳病上篇 29 条原文；来源转写与自动审核尚未经本项目专家复核。无关问题也可能返回候选，请核对原文。
        </p>}
      {workspace === "knowledge" && <KnowledgeWorkspace sessionActive={sessionActive && !!csrf} csrf={csrf} initialSourceId={sourceId || undefined} initialCitation={sourceCitation} onReturnCitation={returnFromCitation} onEvidence={openEvidence} onResearch={(id) => navigate("research", id)} onPublished={() => { setSearchStatus(null); setSearched(false); navigate("search"); }} />}
      {researchVisited && <div hidden={workspace !== "research"}><ResearchWorkspace sessionActive={sessionActive} csrf={csrf} initialSourceId={researchSourceId || undefined} onEvidence={openEvidence} /></div>}

      {workspace === "search" && <section className="panel searchPanel" aria-labelledby="search-title">
        <div className="panelHead">
          <div><span className="sectionLabel">知识检索</span><h2 id="search-title">寻找相关原文</h2></div>
          <span className="modelNote">{retrievalCapability?.cloud_ready ? "云端语义检索与重排已就绪" : "云端检索尚未就绪"}</span>
        </div>
        <form className="searchForm" onSubmit={(event) => void search(event)}>
          <label className="srOnly" htmlFor="knowledge-query">检索问题或关键词</label>
          <input id="knowledge-query" value={query} onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：太阳病的脉象" maxLength={2000} />
          <button type="submit" disabled={searching || !query.trim()}>
            {searching ? "检索中…" : "检索证据"}
          </button>
        </form>
        {retrievalCapability && <p className="hint" role="status">{retrievalCapability.reason || `向量：${retrievalCapability.embedding_model} · 重排：${retrievalCapability.rerank_model}。勾选下方授权后使用云端检索。`}</p>}<label className="hint"><input type="checkbox" checked={allowRemoteQuery}
          onChange={(event) => setAllowRemoteQuery(event.target.checked)} />
          同意将本次检索词发送给已配置的云端向量与重排模型。请勿输入私人或敏感信息。</label>
        {searchError && <p className="error" role="alert">{searchError}</p>}
        {searchStatus && <div className="demoNotice retrievalStatus" role="status">
          <strong>{searchStatus.mode === "LOCAL" ? "本地检索" : searchStatus.mode === "DEGRADED" ? "检索已降级" : "混合检索"}</strong>
          <p>{searchStatus.reasons.map((reason) => reasonNames[reason] ?? "部分检索通道不可用。").join(" ")}</p>
          <p>本次通道：{searchStatus.channels.map((name) => channelNames[name] ?? name).join("、")}。证据详情可在本地查看。</p>
        </div>}
      </section>}

      {workspace === "search" && searched && !searchError && (
        <section className="results" aria-live="polite">
          <div className="resultsHead"><h2>检索结果</h2><span>{results.length} 条已发布证据</span></div>
          {results.length === 0 ? <p className="empty">当前知识版本中没有找到匹配证据。</p> : (
            <div className="resultList">
              {results.map((item) => (
                <article className="resultCard" key={`${item.evidence_id}:${item.evidence_revision_no}`}>
                  <div className="resultMeta">
                    <strong>{item.source_title}</strong><span>来源修订 {item.source_revision_no}</span>
                  </div>
                  <blockquote>{readingText(item.quote_text)}</blockquote>
                  <div className="resultFoot">
                    <div className="channels">
                      {item.matched_channels.map((name) => <span key={name}>{channelNames[name] ?? name}</span>)}
                    </div>
                    <button className="textButton" type="button" onClick={() => { openEvidence({ evidence_id: item.evidence_id, revision_no: item.evidence_revision_no }); setSelected(item); }}>
                      查看证据详情
                    </button>
                    <button className="textButton" type="button" onClick={() => navigate("research", item.source_id)}>以此来源开展研究</button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      <details className="serviceDetails"><summary>本地服务详情</summary><section className="panel statusPanel" aria-live="polite">
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
      </section></details>
      </div>

      {selectedRef && <EvidenceDrawer reference={selectedRef} fallback={selected || undefined} onClose={closeEvidence} onSource={openSourceCitation} />}
    </main>
  );
}

function SessionConnection({ onConnected, onSession }: { onConnected: (csrf: string) => void; onSession: (active: boolean) => void }) {
  const [active, setActive] = useState(false);
  const [checking, setChecking] = useState(true);
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [development, setDevelopment] = useState<boolean | null>(null);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  useEffect(() => {
    let mounted = true;
    setChecking(true); setError("");
    async function restore() {
      try {
        const config = await requestJson<{ development_auto_session: boolean }>("/api/v1/local-session/config");
        if (!mounted) return;
        setDevelopment(config.development_auto_session);
        if (config.development_auto_session) {
          const result = await postJson<{ csrf_token: string }>("/api/v1/local-session/development");
          if (mounted) {
            sessionStorage.setItem("tcm.local.csrf", result.csrf_token);
            setActive(true); onConnected(result.csrf_token);
          }
          return;
        }
        const saved = sessionStorage.getItem("tcm.local.csrf");
        try {
          await requestJson("/api/v1/local-session");
          if (saved) {
            if (mounted) { setActive(true); onConnected(saved); }
            return;
          }
        } catch (cause) {
          if ((cause as { status?: number }).status !== 401) throw cause;
        }
        if (!mounted) return;
        setActive(false); onSession(false); sessionStorage.removeItem("tcm.local.csrf");
      } catch (cause) {
        if (mounted) { setActive(false); onSession(false); setError(apiErrorText(cause)); }
      } finally { if (mounted) setChecking(false); }
    }
    void restore();
    return () => { mounted = false; };
  }, [connectionAttempt]);
  async function connect(event: React.FormEvent) {
    event.preventDefault(); if (!secret.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const result = await postJson<{ csrf_token: string }>("/api/v1/local-session/bootstrap", { bootstrap_secret: secret.trim() });
      sessionStorage.setItem("tcm.local.csrf", result.csrf_token); setSecret(""); setActive(true); onConnected(result.csrf_token);
    } catch (cause) { setError(apiErrorText(cause)); } finally { setBusy(false); }
  }
  if (checking) return <p className="sessionStatus">正在连接本机工作区…</p>;
  if (active && sessionStorage.getItem("tcm.local.csrf")) return <div className="sessionStatus"><span className="connectionDot" /> 本机工作区已连接<span>修改将保存到本地服务</span></div>;
  if (development !== false) return <section className="panel connectionPanel"><div><h2>连接本机工作区</h2><p className="muted">{development ? "开发环境自动连接，无需访问码。" : "本地服务尚未就绪，请稍后重新连接。"}</p>{error && <p className="error" role="alert">{error}</p>}</div><button onClick={() => setConnectionAttempt(value => value + 1)}>重新连接</button></section>;
  return <section className="panel connectionPanel"><div><h2>连接本机工作区</h2><p className="muted">使用本机启动时提供的访问码，连接后可导入、审核文献并创建研究。</p></div><form className="inlineForm connectionForm" onSubmit={(event) => void connect(event)}><label className="srOnly" htmlFor="bootstrap-secret">本机访问码</label><input id="bootstrap-secret" type="password" autoComplete="off" placeholder="本机访问码" value={secret} onChange={(event) => setSecret(event.target.value)} required /><button disabled={busy || !secret.trim()}>{busy ? "连接中…" : "连接"}</button></form>{error && <p className="error" role="alert">{error}</p>}</section>;
}

createRoot(document.getElementById("root")!).render(
  <App />,
);
