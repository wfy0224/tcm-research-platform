import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Health = {
  state: "READY" | "DEGRADED" | "MAINTENANCE" | "NOT_READY";
  database: string;
  schema: string;
  blob_store: string;
};

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function refresh() {
      try {
        const response = await fetch("/api/v1/system/health");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as Health;
        if (mounted) {
          setHealth(data);
          setError(null);
        }
      } catch (cause) {
        if (mounted) setError(cause instanceof Error ? cause.message : "连接失败");
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 10_000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <main className="shell">
      <header>
        <span className="eyebrow">本地工作台 · 第一阶段</span>
        <h1>中医知识研究平台</h1>
        <p>知识与证据底座正在建设。当前页面展示服务、数据库和文件存储的运行状态。</p>
      </header>
      <section className="panel" aria-live="polite">
        <div className="panelHead">
          <h2>系统状态</h2>
          <span className={`badge ${health?.state === "READY" ? "ready" : "pending"}`}>
            {error ? "连接中断" : (health?.state ?? "检查中")}
          </span>
        </div>
        {error && <p className="error">无法连接本地 API：{error}</p>}
        <dl>
          <div><dt>PostgreSQL</dt><dd>{health?.database ?? "—"}</dd></div>
          <div><dt>数据库结构</dt><dd>{health?.schema ?? "—"}</dd></div>
          <div><dt>文件存储</dt><dd>{health?.blob_store ?? "—"}</dd></div>
        </dl>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>,
);

