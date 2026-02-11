import { useCallback, useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"

import AuditPanel from "./AuditPanel"
import DocumentsPanel from "./DocumentsPanel"
import EvidenceModal from "./EvidenceModal"
import FormPanel from "./FormPanel"
import { listDocuments, previewAudit, submitApplication } from "./api"
import type { AuditResult, Citation, FieldSuggestion, HousingDocument } from "./types"

export default function HousingGrantPage() {
  const [docs, setDocs] = useState<HousingDocument[]>([])
  const [formValues, setFormValues] = useState<Record<string, string>>({})
  const [fieldMeta, setFieldMeta] = useState<Record<string, FieldSuggestion>>({})
  const [audit, setAudit] = useState<AuditResult | null>(null)
  const [auditLoading, setAuditLoading] = useState(false)

  const [modal, setModal] = useState<{
    open: boolean
    fieldId: string
    value: string
    rationale: string
    citations: Citation[]
    json: FieldSuggestion | Record<string, unknown> | null
  }>({ open: false, fieldId: "", value: "", rationale: "", citations: [], json: null })

  const closeModal = useCallback(() => setModal((prev) => ({ ...prev, open: false })), [])

  const refreshDocuments = useCallback(async () => {
    try {
      const response = await listDocuments()
      setDocs(response.data)
    } catch (err) {
      toast.error("Failed to load documents", { description: err instanceof Error ? err.message : "Unknown error" })
    }
  }, [])

  useEffect(() => {
    void refreshDocuments()
  }, [refreshDocuments])

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

  function onViewMeta(doc: HousingDocument) {
    setModal({
      open: true,
      fieldId: "document_meta",
      value: doc.filename,
      rationale: "Persisted document metadata and ingestion status.",
      citations: [],
      json: doc as unknown as Record<string, unknown>,
    })
  }

  async function runAudit() {
    setAuditLoading(true)
    try {
      const docIds = docs.filter((doc) => doc.status === "ready").map((doc) => doc.id)

      const metaForApi: Record<string, Record<string, unknown>> = {}
      for (const [fieldId, meta] of Object.entries(fieldMeta)) {
        metaForApi[fieldId] = {
          citations: meta.citations,
          confidence: meta.confidence,
        }
      }

      const response = await previewAudit(formValues, docIds, metaForApi)
      setAudit({
        flags: response.flags.map((flag) => ({ ...flag, severity: flag.severity as "BLOCKER" | "WARNING" | "INFO" })),
        blockers: response.blockers,
        warnings: response.warnings,
        infos: response.infos,
        risk: response.risk,
        coveragePct: response.coveragePct,
      })

      toast.success("Preview Audit complete", {
        description: `${response.blockers} blocker(s), ${response.warnings} warning(s).`,
      })
    } catch (err) {
      toast.error("Audit failed", { description: err instanceof Error ? err.message : "Unknown error" })
    } finally {
      setAuditLoading(false)
    }
  }

  async function saveSubmission() {
    try {
      const payloadMeta: Record<string, Record<string, unknown>> = {}
      for (const [fieldId, meta] of Object.entries(fieldMeta)) {
        payloadMeta[fieldId] = {
          suggested_value: meta.suggested_value,
          confidence: meta.confidence,
          citations: meta.citations,
          flags: meta.flags,
          model: meta.model,
        }
      }
      const result = await submitApplication(formValues, payloadMeta, audit)
      toast.success("Submission saved", {
        description: `Submission ${result.submission_id} stored with status ${result.status}.`,
      })
    } catch (err) {
      toast.error("Submission failed", { description: err instanceof Error ? err.message : "Unknown error" })
    }
  }

  return (
    <div className="space-y-4">
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
              Form AI Copilot <span className="text-xs text-slate-400 font-medium">— Housing Grant + Reasonable Accommodation</span>
            </div>
            <div className="text-xs text-slate-400">Authenticated API mode with persisted document ingestion and citation-backed suggestions.</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[330px_1fr_380px] gap-4 items-start">
        <DocumentsPanel docs={docs} setDocs={setDocs} onViewMeta={onViewMeta} refreshDocuments={refreshDocuments} />
        <FormPanel
          docs={docs}
          formValues={formValues}
          setFormValues={setFormValues}
          fieldMeta={fieldMeta}
          setFieldMeta={setFieldMeta}
          onShowEvidence={onShowEvidence}
          onRunAudit={runAudit}
          onSaveSubmission={saveSubmission}
        />
        <AuditPanel audit={audit} />
      </div>

      {auditLoading && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-[#121a33] border border-white/[0.08] rounded-2xl p-6 flex items-center gap-3">
            <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
            <span className="text-sm">Running audit via API…</span>
          </div>
        </div>
      )}

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
