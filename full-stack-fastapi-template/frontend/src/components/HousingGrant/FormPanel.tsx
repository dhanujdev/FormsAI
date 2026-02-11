import { useState } from "react"
import { AlertTriangle, Eye, Loader2, Sparkles, UploadCloud } from "lucide-react"
import { toast } from "sonner"

import { suggestAllFields as apiSuggestAll, suggestField as apiSuggestField } from "./api"
import { formSchema, labelConfidence } from "./mockData"
import type { Citation, FieldSuggestion, FormField, HousingDocument } from "./types"

const badgeCls = {
  required: "bg-red-400/10 border-red-400/26 text-red-400",
  optional: "bg-cyan-400/10 border-cyan-400/26 text-cyan-300",
  evidence: "bg-amber-400/10 border-amber-400/28 text-amber-300",
}

interface Props {
  docs: HousingDocument[]
  formValues: Record<string, string>
  setFormValues: React.Dispatch<React.SetStateAction<Record<string, string>>>
  fieldMeta: Record<string, FieldSuggestion>
  setFieldMeta: React.Dispatch<React.SetStateAction<Record<string, FieldSuggestion>>>
  onShowEvidence: (fieldId: string) => void
  onRunAudit: () => void
  onSaveSubmission: () => void
}

export default function FormPanel({
  docs,
  formValues,
  setFormValues,
  fieldMeta,
  setFieldMeta,
  onShowEvidence,
  onRunAudit,
  onSaveSubmission,
}: Props) {
  const [loading, setLoading] = useState<Record<string, boolean>>({})
  const [batchLoading, setBatchLoading] = useState(false)

  const filledCount = formSchema.filter((f) => (formValues[f.id] ?? "").trim().length > 0).length
  const readyDocs = docs.filter((doc) => doc.status === "ready")

  const hasSensitive = (() => {
    const joined = Object.values(formValues).join(" ")
    const patterns = [
      /AKIA[0-9A-Z]{16}/,
      /sk-[A-Za-z0-9]{20,}/,
      /password\s*=/i,
      /apikey\s*=/i,
      /\b\d{3}-\d{2}-\d{4}\b/,
      /\b(?:\d[ -]*?){13,16}\b/,
    ]
    return patterns.some((re) => re.test(joined))
  })()

  async function suggestField(fieldId: string) {
    const field = formSchema.find((f) => f.id === fieldId)
    if (!field) return
    if (readyDocs.length === 0) {
      toast.error("No processed documents", { description: "Upload and process at least one document first." })
      return
    }

    setLoading((prev) => ({ ...prev, [fieldId]: true }))
    try {
      const docIds = readyDocs.map((doc) => doc.id)
      const res = await apiSuggestField(fieldId, formValues, docIds)

      setFormValues((prev) => ({ ...prev, [fieldId]: res.suggested_value }))
      setFieldMeta((prev) => ({
        ...prev,
        [fieldId]: {
          field_id: res.field_id,
          suggested_value: res.suggested_value,
          confidence: res.confidence,
          confidenceLabel: res.confidenceLabel || labelConfidence(res.confidence),
          rationale: res.rationale,
          citations: res.citations || [],
          flags: (res.flags || []).map((f) => ({ ...f, severity: f.severity as "info" | "warning" | "error" })),
          model: res.model || "api",
          usage: res.usage || { input_tokens: 0, output_tokens: 0 },
        },
      }))

      toast.success("Suggested value", {
        description: `${field.label} filled (${res.confidenceLabel || labelConfidence(res.confidence)} confidence).`,
      })
    } catch (err) {
      toast.error("Suggest failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      })
    } finally {
      setLoading((prev) => ({ ...prev, [fieldId]: false }))
    }
  }

  async function suggestAll() {
    if (readyDocs.length === 0) {
      toast.error("No processed documents", { description: "Upload and process at least one document first." })
      return
    }

    setBatchLoading(true)
    try {
      const docIds = readyDocs.map((doc) => doc.id)
      const res = await apiSuggestAll(formValues, docIds)

      const newValues: Record<string, string> = { ...formValues }
      const newMeta: Record<string, FieldSuggestion> = { ...fieldMeta }

      for (const suggestion of res.suggestions) {
        newValues[suggestion.field_id] = suggestion.suggested_value
        newMeta[suggestion.field_id] = {
          field_id: suggestion.field_id,
          suggested_value: suggestion.suggested_value,
          confidence: suggestion.confidence,
          confidenceLabel: suggestion.confidenceLabel || labelConfidence(suggestion.confidence),
          rationale: suggestion.rationale,
          citations: suggestion.citations || [],
          flags: (suggestion.flags || []).map((f) => ({ ...f, severity: f.severity as "info" | "warning" | "error" })),
          model: suggestion.model || "api",
          usage: suggestion.usage || { input_tokens: 0, output_tokens: 0 },
        }
      }

      setFormValues(newValues)
      setFieldMeta(newMeta)
      toast.success("All fields suggested", {
        description: `${res.suggestions.length} suggestions returned from API.`,
      })
    } catch (err) {
      toast.error("Suggest all failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      })
    } finally {
      setBatchLoading(false)
    }
  }

  function resetForm() {
    setFormValues({})
    setFieldMeta({})
    toast.info("Form reset", { description: "All fields cleared." })
  }

  return (
    <section
      className="rounded-2xl border border-white/[0.08] shadow-xl overflow-hidden"
      style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.03), transparent 32%), #121a33" }}
    >
      <h2 className="flex items-center justify-between px-4 py-3 text-sm font-semibold tracking-wide border-b border-white/[0.08]">
        <span>Application Form</span>
        <span className="text-xs text-slate-400 font-medium">{filledCount}/15 filled</span>
      </h2>

      <div className="p-4 space-y-3">
        {hasSensitive && (
          <div className="rounded-2xl border border-amber-400/25 bg-amber-400/[0.08] p-3 text-xs leading-snug">
            <strong className="flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-300" /> Sensitive data detected.
            </strong>
            <span className="text-slate-300 ml-5">Keep sensitive fields minimal and verified before submission.</span>
          </div>
        )}

        <p className="text-xs text-slate-400 leading-snug">
          Use <strong className="text-white">Suggest</strong> to fill fields from processed evidence. Only ready documents are used.
        </p>

        {readyDocs.length === 0 && (
          <div className="rounded-2xl border border-cyan-400/25 bg-cyan-400/[0.08] p-3 text-xs text-slate-300 flex items-center gap-2">
            <UploadCloud className="w-4 h-4 text-cyan-300" />
            Upload documents and wait for status <strong className="text-white">ready</strong> to enable AI suggestions.
          </div>
        )}

        <div className="h-px bg-white/[0.08]" />

        <div className="flex flex-col gap-3">
          {formSchema.map((field) => (
            <FieldRow
              key={field.id}
              field={field}
              value={formValues[field.id] ?? ""}
              meta={fieldMeta[field.id]}
              isLoading={loading[field.id] || false}
              onChange={(value) => setFormValues((prev) => ({ ...prev, [field.id]: value }))}
              onSuggest={() => suggestField(field.id)}
              onEvidence={() => onShowEvidence(field.id)}
            />
          ))}
        </div>

        <div className="h-px bg-white/[0.08]" />

        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            onClick={onRunAudit}
            className="flex items-center gap-1.5 rounded-xl border border-cyan-400/28 bg-gradient-to-r from-cyan-400/[0.18] to-emerald-400/[0.18] px-3 py-2.5 text-xs font-semibold hover:border-cyan-400/50 transition-colors"
          >
            Preview Audit
          </button>
          <button
            type="button"
            onClick={suggestAll}
            disabled={batchLoading}
            className="flex items-center gap-1.5 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2.5 text-xs font-semibold hover:border-white/20 transition-colors disabled:opacity-50"
          >
            {batchLoading && <Loader2 className="w-3 h-3 animate-spin" />}
            Suggest all
          </button>
          <button
            type="button"
            onClick={onSaveSubmission}
            className="rounded-xl border border-emerald-400/30 bg-emerald-400/[0.10] px-3 py-2.5 text-xs font-semibold hover:border-emerald-400/50 transition-colors"
          >
            Save submission
          </button>
          <button
            type="button"
            onClick={resetForm}
            className="rounded-xl border border-white/[0.08] bg-transparent px-3 py-2.5 text-xs font-semibold hover:border-white/20 transition-colors"
          >
            Reset form
          </button>
        </div>
      </div>
    </section>
  )
}

function FieldRow({
  field,
  value,
  meta,
  isLoading,
  onChange,
  onSuggest,
  onEvidence,
}: {
  field: FormField
  value: string
  meta: FieldSuggestion | undefined
  isLoading: boolean
  onChange: (v: string) => void
  onSuggest: () => void
  onEvidence: () => void
}) {
  const confPct = meta ? Math.round((meta.confidence || 0) * 100) : 0

  return (
    <div className="rounded-2xl border border-white/[0.08] bg-black/[0.10] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <label className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400 mb-1.5">
            {field.label}
            {field.required ? (
              <span className={`rounded-full border px-2 py-0.5 text-[10px] ${badgeCls.required}`}>Required</span>
            ) : (
              <span className={`rounded-full border px-2 py-0.5 text-[10px] ${badgeCls.optional}`}>Optional</span>
            )}
            {field.evidence && (
              <span className={`rounded-full border px-2 py-0.5 text-[10px] ${badgeCls.evidence}`}>Evidence</span>
            )}
          </label>

          {field.type === "textarea" ? (
            <textarea
              id={`in_${field.id}`}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder="Type here..."
              className="w-full rounded-xl border border-white/10 bg-white/[0.03] text-white text-[13px] px-3 py-2.5 min-h-[80px] resize-y focus:border-cyan-400/45 focus:ring-2 focus:ring-cyan-400/12 outline-none transition-all"
            />
          ) : (
            <input
              id={`in_${field.id}`}
              type={field.type === "number" ? "number" : field.type}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder={field.type === "number" ? "Enter a number" : "Type here..."}
              className="w-full rounded-xl border border-white/10 bg-white/[0.03] text-white text-[13px] px-3 py-2.5 focus:border-cyan-400/45 focus:ring-2 focus:ring-cyan-400/12 outline-none transition-all"
            />
          )}

          <div className="flex items-center gap-2 flex-wrap mt-2.5">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-400">
              <strong className="text-white">Confidence</strong> {meta ? meta.confidenceLabel : "—"}
            </span>
            <div className="w-[140px] h-2 rounded-full bg-white/[0.07] border border-white/[0.06] overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${confPct}%`,
                  background: "linear-gradient(90deg, rgba(255,207,90,0.9), rgba(46,229,157,0.95))",
                }}
              />
            </div>
            <span className="text-xs text-slate-500">{meta ? `${confPct}% · ${meta.model}` : "No suggestion yet"}</span>
          </div>

          {meta && meta.citations.length > 0 ? (
            <div className="flex flex-col gap-2 mt-2.5">
              {meta.citations.slice(0, 2).map((citation: Citation, idx: number) => (
                <div
                  key={`${citation.chunk}-${idx}`}
                  className="flex items-start justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.02] p-2.5"
                >
                  <div className="min-w-0">
                    <div className="text-xs font-bold truncate">
                      {citation.doc} · p.{citation.page} · {citation.chunk}
                    </div>
                    <div className="text-xs text-slate-400 mt-1 line-clamp-2">{citation.quote}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500 mt-2.5">No citations yet for this field.</p>
          )}
        </div>

        <div className="flex flex-col gap-2 shrink-0">
          <button
            type="button"
            onClick={onSuggest}
            disabled={isLoading}
            className="flex items-center gap-1 rounded-xl border border-cyan-400/28 bg-gradient-to-r from-cyan-400/[0.18] to-emerald-400/[0.18] px-2.5 py-2 text-xs font-bold hover:border-cyan-400/50 transition-colors disabled:opacity-50"
          >
            {isLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />} Suggest
          </button>
          <button
            type="button"
            onClick={onEvidence}
            disabled={!meta}
            className="flex items-center gap-1 rounded-xl border border-white/[0.08] bg-white/[0.03] px-2.5 py-2 text-xs font-bold disabled:opacity-40 disabled:cursor-not-allowed hover:border-cyan-400/30 transition-colors"
          >
            <Eye className="w-3 h-3" /> Evidence
          </button>
        </div>
      </div>
    </div>
  )
}
