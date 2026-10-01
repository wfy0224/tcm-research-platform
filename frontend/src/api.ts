export type EvidenceRef = { evidence_id: string; revision_no: number };

const errors: Record<string, string> = {
  SESSION_REQUIRED: "请先连接本机工作区。",
  SESSION_EXPIRED: "本机会话已过期，请重新连接。",
  CSRF_INVALID: "会话校验失效，请重新连接本机工作区。",
  RESOURCE_NOT_FOUND: "该记录不存在，或已不在当前可见范围中。",
  FILE_TOO_LARGE: "文件超过允许的大小，请缩小后重试。",
  SOURCE_TYPE_UNAVAILABLE: "当前阶段支持文献研究，暂不接收现代患者病例。",
  IDEMPOTENCY_CONFLICT: "该请求已使用不同内容提交，请刷新后重试。",
};

export function apiErrorText(error: unknown): string {
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) return "本地服务连接中断，请检查服务连接后重试。";
  return error instanceof Error ? error.message : "操作未完成，请稍后重试。";
}

const fields: Record<string, string> = { title: "文献标题", file_format: "文件格式", content_base64: "来源文件", outbound_reason: "外发授权理由", canonical_name: "规范名称", evidence_id: "原文证据", evidence_revision_no: "证据修订", note: "核对说明", segment_ids: "原文段落" };
const commandErrors: Record<string, string> = {
  "evidence range must be contiguous": "请勾选同一层级的连续原文段落后重试。",
  "evidence range must share a source revision, parent, and type": "请选同一来源修订、同一层级和类型的段落后重试。",
  "evidence range must share a source revision, parent, and level": "请选同一来源修订、同一层级的连续正文；正文与子句不能混选。",
  "structural headings cannot be cited as evidence": "标题不能单独作为证据，请选择正文段落。",
  "source revision has not completed segmentation": "来源解析尚未完成，请等待解析后重试。",
};

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const validation = Array.isArray(detail) ? [...new Set(detail.map((item: { loc?: string[] }) => {
      const key = item.loc?.at(-1) ?? "";
      return `${fields[key] || "填写内容"}缺失或格式不正确`;
    }))].join("；") : "";
    const message = errors[data.code] || validation || (typeof detail === "string" ? commandErrors[detail] || detail : "");
    throw Object.assign(new Error(message || (response.status === 401 ? "请先连接本机工作区。" :
      response.status === 422 ? "请检查必填字段及填写格式。" : `操作未完成（${response.status}）。`)),
    { code: typeof data.code === "string" ? data.code : "HTTP_ERROR", status: response.status });
  }
  return data as T;
}

export function postJson<T>(url: string, body?: unknown, csrf?: string): Promise<T> {
  return requestJson<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf ?? sessionStorage.getItem("tcm.local.csrf") ?? "",
      "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(body ?? {}),
  });
}
