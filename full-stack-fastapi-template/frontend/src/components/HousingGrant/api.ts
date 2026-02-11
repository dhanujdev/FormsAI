/**
 * Housing Grant API Client
 *
 * Calls the FastAPI backend at /api/v1/housing-grant/*.
 * Falls back gracefully if the backend is unreachable.
 */

const API_BASE = "/api/v1/housing-grant"

// If frontend and backend are on different ports during dev, proxy or use full URL
function apiUrl(path: string): string {
    // In dev the Vite proxy will forward /api/* to the backend
    return `${API_BASE}${path}`
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const res = await fetch(apiUrl(path), {
        headers: { "Content-Type": "application/json", ...options.headers },
        ...options,
    })
    if (!res.ok) {
        const text = await res.text()
        throw new Error(`API ${res.status}: ${text}`)
    }
    return res.json() as Promise<T>
}

// ─── Types (match backend response schemas) ─────────────────────

export interface ApiDocContent {
    filename: string
    doc_type: string
    content: string
}

export interface ApiCitation {
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
    status: string
    pages: number | null
    badge: string
    created_at: string | null
}

// ─── API Functions ──────────────────────────────────────────────

export async function suggestField(
    fieldId: string,
    formData: Record<string, string> = {},
    docIds: string[] = [],
    docContents: ApiDocContent[] = [],
): Promise<ApiSuggestResponse> {
    return apiFetch<ApiSuggestResponse>("/suggest", {
        method: "POST",
        body: JSON.stringify({
            field_id: fieldId,
            form_data: formData,
            doc_ids: docIds,
            doc_contents: docContents
        }),
    })
}

export async function suggestAllFields(
    formData: Record<string, string> = {},
    docIds: string[] = [],
    docContents: ApiDocContent[] = [],
): Promise<ApiSuggestAllResponse> {
    return apiFetch<ApiSuggestAllResponse>("/suggest-all", {
        method: "POST",
        body: JSON.stringify({
            form_data: formData,
            doc_ids: docIds,
            doc_contents: docContents
        }),
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

export async function uploadDocument(
    filename: string,
    docType: string,
): Promise<ApiDocumentPublic> {
    return apiFetch<ApiDocumentPublic>("/documents/upload", {
        method: "POST",
        body: JSON.stringify({ filename, doc_type: docType }),
    })
}

export async function listDocuments(): Promise<{ data: ApiDocumentPublic[]; count: number }> {
    return apiFetch("/documents")
}

export async function deleteDocument(docId: string): Promise<void> {
    await apiFetch(`/documents/${docId}`, { method: "DELETE" })
}
