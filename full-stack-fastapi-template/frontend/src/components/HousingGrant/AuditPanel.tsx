import { useState } from "react"
import { ShieldCheck, ArrowRight } from "lucide-react"
import type { AuditResult } from "./types"
import { formSchema } from "./mockData"

const tabConfig = [
    { key: "blocker", label: "Blockers" },
    { key: "warning", label: "Warnings" },
    { key: "info", label: "Info" },
] as const

interface Props {
    audit: AuditResult | null
}

export default function AuditPanel({ audit }: Props) {
    const [activeTab, setActiveTab] = useState<"blocker" | "warning" | "info">("blocker")

    const statusText = audit
        ? audit.blockers ? "Needs attention" : audit.warnings ? "Review warnings" : "Looks good"
        : "Not run"

    function scrollToField(fieldId: string) {
        if (!fieldId || fieldId === "__global__") return
        const el = document.getElementById(`in_${fieldId}`)
        if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "center" })
            el.focus()
        }
    }

    const filtered = audit
        ? audit.flags.filter((f) => {
            if (activeTab === "blocker") return f.severity === "BLOCKER"
            if (activeTab === "warning") return f.severity === "WARNING"
            return f.severity === "INFO"
        })
        : []

    return (
        <section
            className="rounded-2xl border border-white/[0.08] shadow-xl overflow-hidden"
            style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.03), transparent 32%), #121a33" }}
        >
            <h2 className="flex items-center justify-between px-4 py-3 text-sm font-semibold tracking-wide border-b border-white/[0.08]">
                <span className="flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-cyan-400" /> Preview Audit</span>
                <span className="text-xs text-slate-400 font-medium">{statusText}</span>
            </h2>

            <div className="p-4 space-y-3">
                <p className="text-xs text-slate-400 leading-snug">
                    The audit checks required fields, formats, internal consistency, and whether key claims are
                    supported by uploaded documents.
                </p>

                <div className="h-px bg-white/[0.08]" />

                {/* KPIs */}
                <div className="grid grid-cols-2 gap-2.5">
                    <KPI label="Risk score" value={audit ? String(audit.risk) : "—"} />
                    <KPI label="Evidence coverage" value={audit ? `${audit.coveragePct}%` : "—"} />
                    <KPI label="Blockers" value={audit ? String(audit.blockers) : "—"} color={audit && audit.blockers > 0 ? "text-red-400" : undefined} />
                    <KPI label="Warnings" value={audit ? String(audit.warnings) : "—"} color={audit && audit.warnings > 0 ? "text-amber-300" : undefined} />
                </div>

                {/* Tabs */}
                <div className="flex gap-2 flex-wrap">
                    {tabConfig.map((t) => (
                        <button
                            key={t.key}
                            type="button"
                            onClick={() => setActiveTab(t.key)}
                            className={`rounded-full border px-3 py-2 text-xs font-bold cursor-pointer select-none transition-colors
                ${activeTab === t.key
                                    ? "bg-cyan-400/10 border-cyan-400/25 text-white"
                                    : "bg-white/[0.03] border-white/[0.08] text-slate-400 hover:border-white/20"
                                }`}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>

                {/* Flags */}
                <div className="flex flex-col gap-2.5">
                    {!audit ? (
                        <p className="text-xs text-slate-500">Run Preview Audit to see flags.</p>
                    ) : filtered.length === 0 ? (
                        <p className="text-xs text-slate-500">No {activeTab}s.</p>
                    ) : (
                        filtered.map((f, i) => {
                            const sevBadge =
                                f.severity === "BLOCKER"
                                    ? "bg-red-400/10 border-red-400/26 text-red-400"
                                    : f.severity === "WARNING"
                                        ? "bg-amber-400/10 border-amber-400/28 text-amber-300"
                                        : "bg-cyan-400/10 border-cyan-400/26 text-cyan-300"

                            const fieldLabel =
                                f.field_id && f.field_id !== "__global__"
                                    ? formSchema.find((x) => x.id === f.field_id)?.label || f.field_id
                                    : "Global"

                            return (
                                <div
                                    key={`${f.code}-${f.field_id}-${i}`}
                                    className="rounded-2xl border border-white/[0.08] bg-black/[0.12] p-3"
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <span className={`inline-block rounded-full border px-2.5 py-1 text-[10px] font-bold ${sevBadge}`}>
                                                {f.severity}
                                            </span>
                                            <span className="ml-2.5 font-extrabold text-sm">{fieldLabel}</span>
                                            <div className="font-mono text-[11px] text-slate-500 mt-1.5">{f.code}</div>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => scrollToField(f.field_id)}
                                            className="flex items-center gap-1 shrink-0 rounded-xl border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5 text-xs font-bold hover:border-cyan-400/30 transition-colors"
                                        >
                                            Go to field <ArrowRight className="w-3 h-3" />
                                        </button>
                                    </div>
                                    <p className="text-xs text-slate-400 mt-2 leading-snug">{f.message}</p>
                                    <p className="text-xs mt-2">
                                        <strong>Fix:</strong> {f.fix || "—"}
                                    </p>
                                </div>
                            )
                        })
                    )}
                </div>

                {/* Footer */}
                <p className="text-xs text-slate-500 pt-2 leading-snug">
                    <strong>Demo notes:</strong> in production we would store the audit report (redacted)
                    and include doc/chunk references for each grounded field.
                </p>
            </div>
        </section>
    )
}

function KPI({ label, value, color }: { label: string; value: string; color?: string }) {
    return (
        <div className="rounded-2xl border border-white/[0.08] bg-black/[0.12] p-3">
            <div className="text-xs text-slate-400">{label}</div>
            <div className={`text-xl font-black mt-0.5 ${color ?? ""}`}>{value}</div>
        </div>
    )
}
