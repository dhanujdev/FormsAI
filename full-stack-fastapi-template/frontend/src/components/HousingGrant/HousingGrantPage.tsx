import { useState, useCallback } from "react"
import { Loader2 } from "lucide-react"
import DocumentsPanel from "./DocumentsPanel"
import FormPanel from "./FormPanel"
import AuditPanel from "./AuditPanel"
import EvidenceModal from "./EvidenceModal"
import type { MockDoc, FieldSuggestion, AuditResult, Citation } from "./types"
import { previewAudit } from "./api"
import { toast } from "sonner"

export default function HousingGrantPage() {
    // ── State ──
    const [docs, setDocs] = useState<MockDoc[]>([])
    const [formValues, setFormValues] = useState<Record<string, string>>({})
    const [fieldMeta, setFieldMeta] = useState<Record<string, FieldSuggestion>>({})
    const [audit, setAudit] = useState<AuditResult | null>(null)
    const [auditLoading, setAuditLoading] = useState(false)

    // ── Modal state ──
    const [modal, setModal] = useState<{
        open: boolean
        fieldId: string
        value: string
        rationale: string
        citations: Citation[]
        json: FieldSuggestion | Record<string, unknown> | null
    }>({ open: false, fieldId: "", value: "", rationale: "", citations: [], json: null })

    const closeModal = useCallback(() => setModal((m) => ({ ...m, open: false })), [])

    // ── Evidence / Doc Meta handlers ──
    function onShowEvidence(fieldId: string) {
        const meta = fieldMeta[fieldId]
        if (!meta) {
            toast.info("No evidence", { description: "Run Suggest first to generate citations." })
            return
        }
        setModal({
            open: true,
            fieldId,
            value: formValues[fieldId] ?? "",
            rationale: meta.rationale,
            citations: meta.citations,
            json: meta,
        })
    }

    function onViewMeta(doc: MockDoc, index: number) {
        setModal({
            open: true,
            fieldId: "document_meta",
            value: doc.name,
            rationale:
                "Document metadata. In production this would show doc_type, ingestion status, page count, and safe extracted signals—not raw text.",
            citations: [],
            json: {
                doc_id: `doc_${String(index).padStart(3, "0")}`,
                filename: doc.name,
                doc_type: doc.docType,
                status: doc.status.toLowerCase(),
                pages: doc.pages || null,
                storage: { provider: "gcs", path: `gs://bucket/ws_123/user_456/${doc.name}` },
            } as Record<string, unknown>,
        })
    }

    // ── Audit via API ──
    async function runAudit() {
        setAuditLoading(true)
        try {
            const docIds = docs.map((_, i) => `doc_${String(i).padStart(3, "0")}`)

            // Pass field meta so backend can check for evidence
            const metaForApi: Record<string, Record<string, unknown>> = {}
            for (const [fid, m] of Object.entries(fieldMeta)) {
                metaForApi[fid] = {
                    citations: m.citations,
                    confidence: m.confidence,
                }
            }

            const res = await previewAudit(formValues, docIds, metaForApi)

            setAudit({
                flags: res.flags.map(f => ({ ...f, severity: f.severity as "BLOCKER" | "WARNING" | "INFO" })),
                blockers: res.blockers,
                warnings: res.warnings,
                infos: res.infos,
                risk: res.risk,
                coveragePct: res.coveragePct,
            })

            toast.success("Preview Audit complete", {
                description: `${res.blockers} blocker(s), ${res.warnings} warning(s).`,
            })
        } catch (err) {
            toast.error("Audit failed", {
                description: err instanceof Error ? err.message : "Unknown error",
            })
        } finally {
            setAuditLoading(false)
        }
    }

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-3">
                    <div
                        className="w-9 h-9 rounded-[10px] shrink-0"
                        style={{
                            background: "linear-gradient(135deg, rgba(110,231,255,0.9), rgba(46,229,157,0.9))",
                            boxShadow: "0 10px 30px rgba(110,231,255,0.18)",
                        }}
                    />
                    <div>
                        <div className="font-bold">
                            Form AI Copilot{" "}
                            <span className="text-xs text-slate-400 font-medium">
                                — Housing Grant + Reasonable Accommodation
                            </span>
                        </div>
                        <div className="text-xs text-slate-400">
                            Connected to FastAPI backend. Suggest & Audit call real API endpoints.
                        </div>
                    </div>
                </div>
                <div className="flex gap-2.5 text-xs text-slate-400">
                    <span className="rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5">
                        UI: <strong className="text-white">React</strong>
                    </span>
                    <span className="rounded-full border border-emerald-400/25 bg-emerald-400/[0.08] px-2.5 py-1.5">
                        Backend: <strong className="text-emerald-400">FastAPI ✓</strong>
                    </span>
                    <span className="rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5">
                        LLM: <strong className="text-white">Claude</strong> (planned)
                    </span>
                </div>
            </div>

            {/* 3-column grid */}
            <div className="grid grid-cols-1 lg:grid-cols-[330px_1fr_380px] gap-4 items-start">
                <DocumentsPanel docs={docs} setDocs={setDocs} onViewMeta={onViewMeta} />
                <FormPanel
                    docs={docs}
                    formValues={formValues}
                    setFormValues={setFormValues}
                    fieldMeta={fieldMeta}
                    setFieldMeta={setFieldMeta}
                    onShowEvidence={onShowEvidence}
                    onRunAudit={runAudit}
                />
                <AuditPanel audit={audit} />
            </div>

            {/* Audit loading overlay */}
            {auditLoading && (
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
                    <div className="bg-[#121a33] border border-white/[0.08] rounded-2xl p-6 flex items-center gap-3">
                        <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
                        <span className="text-sm">Running audit via API…</span>
                    </div>
                </div>
            )}

            {/* Evidence Modal */}
            <EvidenceModal
                open={modal.open}
                onClose={closeModal}
                fieldId={modal.fieldId}
                value={modal.value}
                rationale={modal.rationale}
                citations={modal.citations}
                json={modal.json}
            />
        </div>
    )
}
