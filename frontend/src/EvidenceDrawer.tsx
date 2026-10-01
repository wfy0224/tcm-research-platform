import { useEffect, useRef, useState } from "react";
import { apiErrorText, requestJson } from "./api";
import type { EvidenceRef } from "./api";
import { citationLocation } from "./citation";
import type { SourceCitation } from "./citation";
import { readingText } from "./knowledgeSelection";

export type EvidenceDetail = {
  evidence_id: string; revision_no?: number; evidence_revision_no?: number;
  source_id?: string; source_title: string; source_revision_no: number;
  quote_text: string; context_before: string; context_after: string;
  full_context_before?: string; full_context_after?: string; context_complete?: boolean;
  citation_locator: Record<string, unknown>; segment_ids: string[]; status?: string;
};

function locatorText(value: unknown): string {
  if (!value || typeof value !== "object") return String(value ?? "未记录");
  const row = value as Record<string, unknown>;
  const labels: Record<string, string> = { page_no: "页", chapter_no: "章", paragraph_no: "段", sentence_no: "句", start_offset: "起始字符", end_offset: "结束字符", sequence_no: "片段序号", book: "卷", chapter: "篇", section: "节", paragraph: "段", page: "页" };
  return Object.entries(row).filter(([, item]) => item != null).map(([key, item]) =>
    `${labels[key] || key}：${typeof item === "object" ? locatorText(item) : String(item)}`).join(" · ") || "未记录";
}

export default function EvidenceDrawer({ reference, fallback, onClose, onSource }: {
  reference: EvidenceRef; fallback?: EvidenceDetail; onClose: () => void;
  onSource?: (target: SourceCitation) => void;
}) {
  const [detail, setDetail] = useState<EvidenceDetail | null>(fallback ?? null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(!fallback);
  const [retry, setRetry] = useState(0);
  const [physicalPages, setPhysicalPages] = useState(false);
  const close = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(fallback ?? null); setError(""); setLoading(true); setPhysicalPages(false);
    void requestJson<EvidenceDetail>(`/api/v1/knowledge/evidence/${encodeURIComponent(reference.evidence_id)}?revision_no=${reference.revision_no}`, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setDetail(value); }).catch((cause) => { if (!controller.signal.aborted) setError(apiErrorText(cause)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reference.evidence_id, reference.revision_no, fallback, retry]);

  useEffect(() => {
    if (!detail?.source_id) return;
    const controller = new AbortController();
    void requestJson<{ revisions: { revision_no: number; file_format: string }[] }>(`/api/v1/knowledge/sources/${encodeURIComponent(detail.source_id)}`, { signal: controller.signal })
      .then(source => { if (!controller.signal.aborted) setPhysicalPages(source.revisions.find(row => row.revision_no === detail.source_revision_no)?.file_format === "pdf"); })
      .catch(() => { /* Logical locations remain available if metadata fails. */ });
    return () => controller.abort();
  }, [detail?.source_id, detail?.source_revision_no]);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden"; close.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const nodes = panel.current?.querySelectorAll<HTMLElement>("button:not(:disabled),a[href],summary,[tabindex='0']");
      if (!nodes?.length) return;
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); document.body.style.overflow = oldOverflow; previous?.focus(); };
  }, [onClose]);

  return <div className="drawerBackdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside className="drawer" ref={panel} role="dialog" aria-modal="true" aria-labelledby="evidence-title">
      <div className="drawerHead"><div><span className="sectionLabel">原文溯源</span><h2 id="evidence-title">证据详情</h2></div>
        <button ref={close} className="closeButton" type="button" aria-label="关闭证据详情" onClick={onClose}>×</button></div>
      <div className="drawerBody" aria-live="polite">
        {loading && <p className="muted">正在读取精确修订…</p>}
        {error && <div className="error" role="alert"><p>精确证据读取失败：{error}</p><button onClick={() => setRetry(value => value + 1)}>重试读取证据</button></div>}
        {detail && <><h3>{detail.source_title}</h3><p className="muted">来源修订 {detail.source_revision_no} · 证据修订 {reference.revision_no}</p>
          <blockquote className="drawerQuote">{readingText(detail.quote_text)}</blockquote>
          <h4>{detail.context_complete ? "原文上下文" : "上下文摘要"}</h4>{!loading && !error ? <><p className="contextText">上文：{readingText(detail.full_context_before ?? detail.context_before) || "已读取，此范围没有上文"}</p>
          <p className="contextText">下文：{readingText(detail.full_context_after ?? detail.context_after) || "已读取，此范围没有下文"}</p></> : <p className="contextText">上下文{error ? "读取失败，请重试" : "正在核对"}。</p>}
          <h4>引用位置</h4><p className="contextText">起点：{citationLocation(detail.citation_locator.start ?? detail.citation_locator, physicalPages)}</p>
          {detail.citation_locator.end != null && <p className="contextText">终点：{citationLocation(detail.citation_locator.end, physicalPages)}</p>}
          {detail.source_id && onSource && <button className="textButton" disabled={loading || !!error} onClick={() => onSource({ source_id: detail.source_id!, source_revision_no: detail.source_revision_no, evidence: reference })}>打开来源文献</button>}
          <details className="referenceDetails"><summary>查看精确引用编号</summary><p className="idText">{reference.evidence_id} · 修订 {reference.revision_no}</p>
            <p>{locatorText(detail.citation_locator)}</p><pre>{detail.quote_text}</pre>
            {detail.segment_ids.map((id) => <p className="idText" key={id}>{id}</p>)}</details>
        </>}
      </div>
    </aside>
  </div>;
}
