import type { EvidenceRef } from "./api";

export type SourceCitation = { source_id: string; source_revision_no: number; evidence: EvidenceRef };

export function sourceCitationFromUrl(params: URLSearchParams): SourceCitation | undefined {
  const source_id = params.get("source"), source_revision_no = Number(params.get("source_revision"));
  const evidence_id = params.get("citation"), revision_no = Number(params.get("citation_revision"));
  return source_id && evidence_id && Number.isSafeInteger(source_revision_no) && source_revision_no > 0 && Number.isSafeInteger(revision_no) && revision_no > 0
    ? { source_id, source_revision_no, evidence: { evidence_id, revision_no } } : undefined;
}

// Show only meaningful document locations. Parser paths and physical-line maps
// remain in the preserved API payload, rather than in the reading interface.
export function citationLocation(value: unknown, physicalPages = false): string {
  if (!value || typeof value !== "object") return "位置未识别";
  const row = value as Record<string, unknown>;
  const labels: Record<string, string> = { book: "卷", chapter: "篇", section: "节", chapter_no: "章", paragraph_no: "逻辑段", paragraph: "逻辑段", sentence_no: "句" };
  if (physicalPages) { labels.page_no = "页"; labels.page = "页"; }
  return Object.entries(labels).flatMap(([key, label]) => {
    const item = row[key];
    return (typeof item === "string" && item.trim() && item !== "None") || (typeof item === "number" && Number.isFinite(item) && item > 0) ? [`${label} ${item}`] : [];
  }).join(" · ") || "位置未识别";
}
