import { useEffect, useState } from "react";
import { apiErrorText, requestJson } from "./api";

type Ingredient = { original_name: string; amount_original: string; unit: string; processing: string };
type Row = { segment_id: string; sequence_no: number; original_text: string };
type Evidence = { evidence_id: string; revision_no: number; source_id: string; source_revision_no: number; segment_ids: string[] };
export type FormulaInput = { original_name: string; ingredients: Ingredient[]; method: string; indications: string; effects: string; preparation: string; cautions: string; formula_id?: string };
const emptyIngredient = (): Ingredient => ({ original_name: "", amount_original: "", unit: "", processing: "" });
const emptyFormula = (): FormulaInput => ({ original_name: "", ingredients: [emptyIngredient()], method: "", indications: "", effects: "", preparation: "", cautions: "" });
const labels = { original_name: "方剂原名", amount_original: "原文剂量", unit: "原文单位", processing: "炮制", method: "煎服方法", indications: "主治", effects: "功效", preparation: "制备", cautions: "禁忌" };

export default function FormulaEditor({ evidence, initial, busy, onSave }: { evidence?: Evidence; initial?: FormulaInput; busy: boolean; onSave: (body: Record<string, unknown>) => Promise<void> }) {
  const [value, setValue] = useState<FormulaInput>(() => initial ?? emptyFormula());
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(false);
  const [choices, setChoices] = useState<Record<string, string>>({});
  useEffect(() => {
    setRows([]); setChoices({}); setError("");
    if (!evidence) return;
    const controller = new AbortController();
    const target = evidence;
    setLoading(true);
    void (async () => {
      const found: Row[] = [];
      let after = -1;
      while (found.length < target.segment_ids.length) {
        const page = await requestJson<Row[]>(`/api/v1/knowledge/sources/${encodeURIComponent(target.source_id)}/revisions/${target.source_revision_no}/segments?limit=500&after=${after}`, { signal: controller.signal });
        if (!page.length) break;
        found.push(...page.filter(row => target.segment_ids.includes(row.segment_id)));
        after = page.at(-1)!.sequence_no;
      }
      if (found.length !== target.segment_ids.length) throw new Error("证据原文未完整加载，请重试。");
      if (!controller.signal.aborted) setRows(found);
    })().catch(cause => { if (!controller.signal.aborted) setError(apiErrorText(cause)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [evidence?.evidence_id, evidence?.revision_no, retry]);

  const fields = [
    ...(["original_name", "method", "indications", "effects", "preparation", "cautions"] as const).map(key => ({ key, text: value[key], label: labels[key] })),
    ...value.ingredients.flatMap((item, index) => (Object.keys(item) as (keyof Ingredient)[]).map(key => ({ key: `ingredients.${index}.${key}`, text: item[key], label: `药味 ${index + 1} · ${key === "original_name" ? "药名" : labels[key]}` }))),
  ].filter(field => field.text.trim());
  function spans(text: string) {
    return rows.flatMap(row => {
      const matches = [];
      let start = row.original_text.indexOf(text);
      while (start >= 0) {
        const offset = Array.from(row.original_text.slice(0, start)).length;
        matches.push({ segment_ref: `${row.segment_id}@${evidence!.source_revision_no}`, start_offset: offset, end_offset: offset + Array.from(text).length, token: `${row.segment_id}:${offset}`, label: `段 ${row.sequence_no + 1}：${row.original_text.slice(Math.max(0, start - 12), start + text.length + 12)}` });
        start = row.original_text.indexOf(text, start + 1);
      }
      return matches;
    });
  }
  const cited = fields.map(field => {
    const options = spans(field.text.trim());
    const selected = options.find(option => option.token === choices[field.key]) ?? (options.length === 1 ? options[0] : undefined);
    return { ...field, options, selected };
  });
  const reason = busy ? "正在保存，请稍候。" : !evidence ? "请先选择已核对的原文证据。" : loading ? "正在加载精确原文。" : error || (!value.original_name.trim() ? "请填写方剂原名。" : value.ingredients.some(row => !row.original_name.trim()) ? "每味药须填写原文药名。" : cited.some(field => !field.selected) ? "请为每个已填字段选择准确原文依据；不明字段留空。" : "");
  async function save() {
    if (reason || !evidence) return;
    const nullable = (text: string) => text.trim() || null;
    const body = {
      ...Object.fromEntries(Object.entries(value).filter(([key]) => key !== "ingredients").map(([key, item]) => [key, nullable(item as string)])),
      evidence_id: evidence.evidence_id, evidence_revision_no: evidence.revision_no,
      ingredients: value.ingredients.map(row => Object.fromEntries(Object.entries(row).map(([key, item]) => [key, nullable(item)]))),
      field_sources: cited.map(field => ({ field_key: field.key, segment_ref: field.selected!.segment_ref, start_offset: field.selected!.start_offset, end_offset: field.selected!.end_offset })),
    };
    await onSave(body);
  }
  return <section className="kwFormulaEditor" aria-label="手工方剂整理">
    <p className="kwHint">逐字段保留原文；原文剂量、现代克数不换算。不明字段留空。{value.formula_id && "保存为新的待审修订，旧修订保留。"}</p>
    <label>方剂原名（必填）<input value={value.original_name} maxLength={300} onChange={event => setValue({ ...value, original_name: event.target.value })} /></label>
    {value.ingredients.map((row, index) => <fieldset key={index}><legend>药味 {index + 1}</legend>{(Object.keys(row) as (keyof Ingredient)[]).map(key => <label key={key}>{key === "original_name" ? "药名（必填）" : `${labels[key]}（选填）`}<input value={row[key]} onChange={event => setValue({ ...value, ingredients: value.ingredients.map((item, i) => i === index ? { ...item, [key]: event.target.value } : item) })} /></label>)}<button type="button" disabled={busy || value.ingredients.length === 1} onClick={() => setValue({ ...value, ingredients: value.ingredients.filter((_, i) => i !== index) })}>移除此药味</button></fieldset>)}
    <button type="button" disabled={busy || value.ingredients.length >= 100} onClick={() => setValue({ ...value, ingredients: [...value.ingredients, emptyIngredient()] })}>增加药味</button>
    {(["method", "indications", "effects", "preparation", "cautions"] as const).map(key => <label key={key}>{labels[key]}（选填）<textarea value={value[key]} onChange={event => setValue({ ...value, [key]: event.target.value })} /></label>)}
    <details open><summary>逐字段原文依据</summary>{cited.map(field => <label key={field.key}>{field.label}：{field.text}<select value={field.selected?.token ?? ""} onChange={event => setChoices({ ...choices, [field.key]: event.target.value })}><option value="">{field.options.length ? "请选择原文位置" : "此字段不在所选证据中，请核对或留空"}</option>{field.options.map(option => <option key={option.token} value={option.token}>{option.label}</option>)}</select></label>)}</details>
    {error && <button type="button" onClick={() => setRetry(retry + 1)}>重试读取方剂原文</button>}
    <button className="kwPrimary" type="button" disabled={!!reason} onClick={() => void save()}>保存方剂待审草稿</button>{reason && <p className="kwHint" role="status">{reason}</p>}
  </section>;
}
