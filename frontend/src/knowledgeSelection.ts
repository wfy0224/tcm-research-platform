export type RangeSegment = { segment_id: string; sequence_no: number; segment_type: string; parent_segment_id: string | null };
const bodyTypes = new Set(["PARAGRAPH", "CLAUSE", "COMMENTARY", "NOTE", "CASE_NOTE", "FORMULA_TEXT"]);

// Compare all siblings, including headings: omitting a different body type must
// not silently create a quote that skips source content.
export function invalidEvidenceRange(loaded: RangeSegment[], selected: RangeSegment[]): boolean {
  if (!selected.length) return false;
  const rows = [...selected].sort((a, b) => a.sequence_no - b.sequence_no);
  const first = rows[0], last = rows.at(-1)!;
  const compatible = (row: RangeSegment) => bodyTypes.has(first.segment_type) ? bodyTypes.has(row.segment_type) : row.segment_type === "SENTENCE" && first.segment_type === "SENTENCE";
  if (rows.some(row => row.parent_segment_id !== first.parent_segment_id || !compatible(row))) return true;
  const siblings = loaded.filter(row => row.parent_segment_id === first.parent_segment_id && row.sequence_no >= first.sequence_no && row.sequence_no <= last.sequence_no);
  return siblings.length !== rows.length;
}

export function readingText(text: string): string {
  return text.replace(/([\u3400-\u9fff，、：；])\n+(?=[\u3400-\u9fff])/g, "$1");
}
