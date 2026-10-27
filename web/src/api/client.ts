export type CaseStatus = "draft" | "analyzing" | "analyzed" | "failed";
export type Severity = "high" | "medium" | "low" | null;
export type GeoPoint = { latitude: number; longitude: number };
export type Attachment = {
  id: number;
  file_name: string;
  mime_type: string;
  size: number;
  kind: string;
  description?: string | null;
  transcript?: string | null;
  read_status?: "read" | "will_read" | "unread";
};
export type CaseSummary = {
  id: number;
  case_name: string | null;
  case_number: string | null;
  case_type: string;
  status: CaseStatus;
  severity: Severity;
  location: string | null;
  latitude: number | null;
  longitude: number | null;
  date: string | null;
  timestamp: string;
  attachment_count?: number;
  attachment_bytes?: number;
};
export type CaseDetail = CaseSummary & {
  case_text: string;
  report: Record<string, unknown> | null;
  report_raw: string;
  versions: { id: number; timestamp: string; report_text: string }[];
  attachments: Attachment[];
  message_count: number;
};
export type ChatMessage = {
  id: number;
  case_id: number;
  role: "user" | "assistant";
  content: string;
  status: "ok" | "pending" | "failed";
  error: string | null;
  reply_to: number | null;
  attachments: Attachment[];
};
export type CaseListResponse = { cases: CaseSummary[]; stats: Record<string, unknown>; count: number };
export type APIError = { error?: { code?: string; message?: string } };

async function request<T>(path: string, language: string, init?: RequestInit): Promise<T> {
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`${path}${separator}lang=${language}`, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as APIError;
    throw new Error(body.error?.message ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function normalizeCaseDetail(detail: CaseDetail): CaseDetail {
  return {
    ...detail,
    case_text: typeof detail.case_text === "string" ? detail.case_text : "",
    versions: Array.isArray(detail.versions) ? detail.versions : [],
    attachments: Array.isArray(detail.attachments) ? detail.attachments : [],
    message_count: detail.message_count ?? 0,
  };
}

export const api = {
  cases: (query: URLSearchParams, language: string) =>
    request<CaseListResponse>(`/api/cases?${query.toString()}`, language),
  case: async (id: string | number, language: string) =>
    normalizeCaseDetail(await request<CaseDetail>(`/api/cases/${id}`, language)),
  messages: (id: string | number, language: string) =>
    request<ChatMessage[]>(`/api/cases/${id}/messages`, language),
  attachments: (id: string | number, language: string) =>
    request<Attachment[]>(`/api/cases/${id}/attachments`, language),
  createCase: async (case_text: string, language: string) =>
    normalizeCaseDetail(await request<CaseDetail>("/api/cases", language, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_text }),
    })),
  patchCase: async (id: number, patch: Partial<CaseDetail>, language: string) => {
    const result = await request<{ case: CaseDetail; duplicate_case_number: boolean }>(`/api/cases/${id}`, language, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    return { ...result, case: normalizeCaseDetail(result.case) };
  },
  suggest: (id: number, language: string) =>
    request<Partial<CaseDetail>>(`/api/cases/${id}/suggest`, language, { method: "POST" }),
  analyze: (id: number, language: string) =>
    request<{ status: string }>(`/api/cases/${id}/analyze`, language, { method: "POST" }),
  removeCase: (id: number, language: string) =>
    request<void>(`/api/cases/${id}`, language, { method: "DELETE" }),
  sendMessage: (id: number, form: FormData, language: string) =>
    request<{ message_id: number; reply_id: number }>(`/api/cases/${id}/messages`, language, {
      method: "POST",
      body: form,
    }),
  clearMessages: (id: number, language: string) =>
    request<void>(`/api/cases/${id}/messages`, language, { method: "DELETE" }),
  retry: (id: number, language: string) =>
    request<{ status: string }>(`/api/messages/${id}/retry`, language, { method: "POST" }),
  updateReport: (id: number, language: string) =>
    request<{ status: string }>(`/api/messages/${id}/update-report`, language, { method: "POST" }),
  upload: (id: number, files: FileList | File[], language: string,
    options: { reanalyze?: boolean } = {}) => {
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    const query = options.reanalyze === false ? "?reanalyze=false" : "";
    return request<{ uploaded: number; errors: { name: string; error: string }[] }>(
      `/api/cases/${id}/attachments${query}`,
      language,
      { method: "POST", body: form },
    );
  },
  previewRead: (id: number, language: string) =>
    request<{ text: string; errors: string[] }>(
      `/api/cases/${id}/attachments/read-preview`,
      language,
      { method: "POST" },
    ),
  geocode: (query: string, language: string) =>
    request<GeoPoint | null>(`/api/geocode?q=${encodeURIComponent(query)}`, language),
};
