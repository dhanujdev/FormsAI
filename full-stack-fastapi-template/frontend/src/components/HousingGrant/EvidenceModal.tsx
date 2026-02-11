import { useEffect } from "react"
import { X, Copy } from "lucide-react"
import type { Citation, FieldSuggestion } from "./types"
import { toast } from "sonner"

interface Props {
    open: boolean
    onClose: () => void
    fieldId: string
    value: string
    rationale: string
    citations: Citation[]
    json: FieldSuggestion | Record<string, unknown> | null
}

export default function EvidenceModal({ open, onClose, fieldId, value, rationale, citations, json }: Props) {
    // ESC to close
    useEffect(() => {
        function handler(e: KeyboardEvent) {
            if (e.key === "Escape") onClose()
        }
        if (open) window.addEventListener("keydown", handler)
        return () => window.removeEventListener("keydown", handler)
    }, [open, onClose])

    if (!open) return null

    async function copyJSON() {
        try {
            await navigator.clipboard.writeText(JSON.stringify(json, null, 2))
            toast.success("Copied", { description: "JSON payload copied to clipboard." })
        } catch {
            toast.error("Copy failed", { description: "Clipboard permission blocked." })
        }
    }

    const title = fieldId === "document_meta" ? "Document metadata" : "Evidence"

    return (
        <div
            className="fixed inset-0 z-40 flex items-center justify-center p-4 bg-black/55"
            onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
            role="dialog"
            aria-modal="true"
            aria-label={title}
        >
            <div
                className="w-full max-w-[860px] rounded-2xl border border-white/[0.08] shadow-xl overflow-hidden"
                style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.04), transparent 30%), #0f1630" }}
            >
                {/* Head */}
                <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-white/[0.08]">
                    <div>
                        <div className="font-extrabold">{title}</div>
                        <div className="text-xs text-slate-400">Citations & snippets (mock)</div>
                    </div>
                    <div className="flex gap-2">
                        <button
                            type="button"
                            onClick={copyJSON}
                            className="flex items-center gap-1 rounded-xl border border-white/[0.08] bg-transparent px-3 py-2 text-xs font-bold hover:border-white/20 transition-colors"
                        >
                            <Copy className="w-3 h-3" /> Copy JSON
                        </button>
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex items-center gap-1 rounded-xl border border-red-400/25 bg-red-400/[0.08] px-3 py-2 text-xs font-bold hover:border-red-400/40 transition-colors"
                        >
                            <X className="w-3 h-3" /> Close
                        </button>
                    </div>
                </div>

                {/* Body */}
                <div className="p-4 max-h-[70vh] overflow-auto space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Left */}
                        <div className="space-y-3">
                            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1.5 text-xs text-slate-400">
                                <strong className="text-white">Field</strong> {fieldId}
                            </span>

                            <div>
                                <div className="text-xs text-slate-400">Suggested value</div>
                                <div className="font-black mt-1">{value || "—"}</div>
                            </div>

                            <div>
                                <div className="text-xs text-slate-400">Rationale</div>
                                <div className="text-xs text-slate-400 mt-1 leading-relaxed">{rationale || "—"}</div>
                            </div>
                        </div>

                        {/* Right – raw payload */}
                        <div>
                            <div className="text-xs text-slate-400">Raw payload (what backend would return)</div>
                            <div className="h-px bg-white/[0.08] my-2" />
                            <pre className="font-mono text-xs text-slate-400 whitespace-pre-wrap break-words bg-black/20 rounded-xl p-3 max-h-[280px] overflow-auto">
                                {JSON.stringify(json, null, 2)}
                            </pre>
                        </div>
                    </div>

                    <div className="h-px bg-white/[0.08]" />

                    {/* Citations */}
                    <div>
                        <div className="text-xs text-slate-400 mb-2">Citations</div>
                        {!citations || citations.length === 0 ? (
                            <p className="text-xs text-slate-500">No citations available.</p>
                        ) : (
                            <div className="flex flex-col gap-2">
                                {citations.map((c, i) => (
                                    <div
                                        key={`${c.chunk}-${i}`}
                                        className="flex items-start justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.02] p-3"
                                    >
                                        <div className="min-w-0">
                                            <div className="text-xs font-bold truncate">
                                                {c.doc} · {c.docType || "doc"} · p.{c.page} · {c.chunk}
                                            </div>
                                            <div className="text-xs text-slate-400 mt-1 line-clamp-2">{c.quote}</div>
                                        </div>
                                        <span className="shrink-0 rounded-full border border-cyan-400/26 bg-cyan-400/10 px-2.5 py-1 text-[10px] text-cyan-300">
                                            Citation
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
