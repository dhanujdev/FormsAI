const API_BASE = "/api/v1/housing-grant"

function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(apiUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }

  return res.json() as Promise<T>
}

export interface ApiCitation {
  docId: string
  doc: string
  docType: string
  page: string
  chunk: string
  quote: string
}

export interface ApiFlag {
  code: string
  severity: string
  message: string
}

export interface ApiSuggestResponse {
  field_id: string
  suggested_value: string
  confidence: number
  confidenceLabel: string
  rationale: string
  citations: ApiCitation[]
  flags: ApiFlag[]
  model: string
  usage: { input_tokens: number; output_tokens: number }
}

export interface ApiSuggestAllResponse {
  suggestions: ApiSuggestResponse[]
}

export interface ApiAuditFlag {
  severity: string
  code: string
  field_id: string
  message: string
  fix: string
}

export interface ApiAuditResponse {
  flags: ApiAuditFlag[]
  blockers: number
  warnings: number
  infos: number
  risk: number
  coveragePct: number
}

export interface ApiDocumentPublic {
  id: string
  filename: string
  doc_type: string
  status: "pending" | "uploaded" | "processing" | "ready" | "error"
  pages: number | null
  badge: "good" | "warn" | "bad" | "info"
  created_at: string
  updated_at: string
}

export interface ApiUploadInitRequest {
  filename: string
  doc_type: string
  content_type: string
  size_bytes: number
}

export interface ApiUploadInitResponse {
  document_id: string
  object_key: string
  upload_url: string
  required_headers: Record<string, string>
  expires_at: string
}

export interface ApiUploadCompleteResponse {
  document_id: string
  status: string
}

export interface ApiSubmissionResponse {
  submission_id: string
  audit_report_id: string | null
  status: string
}

export async function createUploadUrl(body: ApiUploadInitRequest): Promise<ApiUploadInitResponse> {
  return apiFetch<ApiUploadInitResponse>("/documents/upload-url", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function completeUpload(documentId: string, etag?: string): Promise<ApiUploadCompleteResponse> {
  return apiFetch<ApiUploadCompleteResponse>(`/documents/${documentId}/complete`, {
    method: "POST",
    body: JSON.stringify({ etag: etag || null }),
  })
}

export async function listDocuments(): Promise<{ data: ApiDocumentPublic[]; count: number }> {
  return apiFetch<{ data: ApiDocumentPublic[]; count: number }>("/documents")
}

export async function deleteDocument(docId: string): Promise<void> {
  await apiFetch(`/documents/${docId}`, { method: "DELETE" })
}

export async function suggestField(
  fieldId: string,
  formData: Record<string, string> = {},
  docIds: string[] = [],
): Promise<ApiSuggestResponse> {
  return apiFetch<ApiSuggestResponse>("/suggest", {
    method: "POST",
    body: JSON.stringify({ field_id: fieldId, form_data: formData, doc_ids: docIds }),
  })
}

export async function suggestAllFields(
  formData: Record<string, string> = {},
  docIds: string[] = [],
): Promise<ApiSuggestAllResponse> {
  return apiFetch<ApiSuggestAllResponse>("/suggest-all", {
    method: "POST",
    body: JSON.stringify({ form_data: formData, doc_ids: docIds }),
  })
}

export async function previewAudit(
  formData: Record<string, string>,
  docIds: string[],
  fieldMeta: Record<string, unknown>,
): Promise<ApiAuditResponse> {
  return apiFetch<ApiAuditResponse>("/preview-audit", {
    method: "POST",
    body: JSON.stringify({ form_data: formData, doc_ids: docIds, field_meta: fieldMeta }),
  })
}

export async function submitApplication(
  formData: Record<string, string>,
  fieldMeta: Record<string, unknown>,
  audit: ApiAuditResponse | null,
): Promise<ApiSubmissionResponse> {
  return apiFetch<ApiSubmissionResponse>("/submissions", {
    method: "POST",
    body: JSON.stringify({ form_data: formData, field_meta: fieldMeta, audit }),
  })
}
