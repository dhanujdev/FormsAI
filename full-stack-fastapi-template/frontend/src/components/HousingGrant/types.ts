// Housing Grant Form AI Copilot – shared types

export interface Citation {
    doc: string
    docType: string
    page: string
    chunk: string
    quote: string
}

export interface Flag {
    code: string
    severity: "info" | "warning" | "error"
    message: string
}

export interface FieldSuggestion {
    field_id: string
    suggested_value: string
    confidence: number
    confidenceLabel: string
    rationale: string
    citations: Citation[]
    flags: Flag[]
    model: string
    usage: { input_tokens: number; output_tokens: number }
}

export interface FormField {
    id: string
    label: string
    type: "text" | "date" | "email" | "number" | "textarea"
    required: boolean
    evidence: boolean
    docTypes?: string[]
    verifier?: string
}

export interface MockDoc {
    name: string
    docType: string
    status: string
    badge: "good" | "warn" | "bad" | "info"
    pages: number
    content?: string  // Actual text or base64
}

export interface AuditFlag {
    severity: "BLOCKER" | "WARNING" | "INFO"
    code: string
    field_id: string
    message: string
    fix: string
}

export interface AuditResult {
    flags: AuditFlag[]
    blockers: number
    warnings: number
    infos: number
    risk: number
    coveragePct: number
}
