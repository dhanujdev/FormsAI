import { useRef } from "react"
import { FileUp, Plus, Trash2, Eye } from "lucide-react"
import type { MockDoc } from "./types"
import { guessDocType, sampleDocs } from "./mockData"
import { toast } from "sonner"

const badgeClass: Record<string, string> = {
    good: "bg-emerald-500/10 border-emerald-500/25 text-emerald-400",
    warn: "bg-amber-400/10 border-amber-400/28 text-amber-300",
    bad: "bg-red-400/10 border-red-400/26 text-red-400",
    info: "bg-cyan-400/10 border-cyan-400/26 text-cyan-300",
}

interface Props {
    docs: MockDoc[]
    setDocs: (docs: MockDoc[]) => void
    onViewMeta: (doc: MockDoc, index: number) => void
}

export default function DocumentsPanel({ docs, setDocs, onViewMeta }: Props) {
    const fileRef = useRef<HTMLInputElement>(null)

    function addSampleDocs() {
        setDocs(JSON.parse(JSON.stringify(sampleDocs)))
        toast.success("Sample docs added", {
            description: "Lease, paystub, utility bill, provider letter (mock).",
        })
    }

    function clearDocs() {
        setDocs([])
        toast.info("Cleared documents", {
            description: "Upload or add sample docs to continue.",
        })
    }

    async function handleFiles(files: FileList | null) {
        if (!files || files.length === 0) return

        const toastId = toast.loading("Reading files...")
        const newDocs: MockDoc[] = []

        try {
            for (let i = 0; i < files.length; i++) {
                const file = files[i]
                const docType = guessDocType(file.name)
                let content = ""

                try {
                    if (file.type.startsWith("image/")) {
                        content = await new Promise<string>((resolve, reject) => {
                            const reader = new FileReader()
                            reader.onload = (e) => resolve(e.target?.result as string || "")
                            reader.onerror = reject
                            reader.readAsDataURL(file)
                        })
                    } else {
                        // Default to text reading (best effort for non-images)
                        content = await new Promise<string>((resolve, reject) => {
                            const reader = new FileReader()
                            reader.onload = (e) => resolve(e.target?.result as string || "")
                            reader.onerror = reject
                            reader.readAsText(file) // Might produce garbage for binary PDF, but prevents crash
                        })
                    }
                } catch (err) {
                    console.error("File read error", err)
                    content = ""
                }

                newDocs.push({
                    name: file.name,
                    docType,
                    status: "Ready",
                    badge: "good",
                    pages: 1,
                    content
                })
            }

            const combined = [...docs, ...newDocs]
            setDocs(combined)
            toast.dismiss(toastId)
            toast.success("Documents ready", {
                description: `${newDocs.length} files processed for extraction.`
            })
        } catch (err) {
            toast.dismiss(toastId)
            toast.error("Upload failed")
        }
    }

    return (
        <section className="rounded-2xl border border-white/[0.08] bg-gradient-to-b from-white/[0.03] to-transparent shadow-xl overflow-hidden"
            style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.03), transparent 32%), #121a33" }}>
            <h2 className="flex items-center justify-between px-4 py-3 text-sm font-semibold tracking-wide border-b border-white/[0.08]">
                <span className="flex items-center gap-2"><FileUp className="w-4 h-4 text-cyan-400" /> Documents</span>
                <span className="text-xs text-slate-400 font-medium">{docs.length} uploaded</span>
            </h2>

            <div className="p-4 space-y-3">
                <p className="text-xs text-slate-400 leading-snug">
                    Upload paystubs, lease, utility bill, and (optional) provider letter.
                    In the real app, uploads go via signed URLs to object storage and ingestion runs OCR + chunking.
                </p>

                {/* Drop zone */}
                <label
                    className="flex items-center justify-between gap-3 cursor-pointer rounded-2xl border border-dashed border-cyan-400/35 bg-cyan-400/[0.06] p-4 hover:border-cyan-400/50 transition-colors"
                    htmlFor="fileInput"
                >
                    <div>
                        <div className="font-extrabold text-sm">Drop files here</div>
                        <div className="text-xs text-slate-400">or click to choose (PDF, JPG, PNG)</div>
                    </div>
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1.5 text-xs text-slate-400">
                        <strong className="text-white">Mock</strong> ingestion
                    </span>
                    <input
                        ref={fileRef}
                        id="fileInput"
                        type="file"
                        className="hidden"
                        multiple
                        onChange={(e) => handleFiles(e.target.files)}
                    />
                </label>

                {/* Buttons */}
                <div className="flex gap-2 flex-wrap">
                    <button
                        type="button"
                        onClick={addSampleDocs}
                        className="flex items-center gap-1.5 rounded-xl border border-cyan-400/28 bg-gradient-to-r from-cyan-400/[0.18] to-emerald-400/[0.18] px-3 py-2.5 text-xs font-semibold hover:border-cyan-400/50 transition-colors"
                    >
                        <Plus className="w-3.5 h-3.5" /> Add sample docs
                    </button>
                    <button
                        type="button"
                        onClick={clearDocs}
                        className="flex items-center gap-1.5 rounded-xl border border-white/[0.08] bg-transparent px-3 py-2.5 text-xs font-semibold hover:border-white/20 transition-colors"
                    >
                        <Trash2 className="w-3.5 h-3.5" /> Clear
                    </button>
                </div>

                <div className="h-px bg-white/[0.08]" />

                <p className="text-xs text-slate-400 leading-snug">
                    Security posture (demo): we avoid showing raw doc text and keep evidence snippets small.
                </p>

                {/* Doc list */}
                <div className="flex flex-col gap-2.5">
                    {docs.length === 0 ? (
                        <p className="text-xs text-slate-500">No documents yet. Add sample docs to demo the flow.</p>
                    ) : (
                        docs.map((d, idx) => (
                            <div
                                key={`${d.name}-${idx}`}
                                className="flex items-center justify-between gap-2 rounded-2xl border border-white/[0.08] bg-black/[0.12] p-3"
                            >
                                <div className="min-w-0">
                                    <div className="text-[13px] font-bold truncate" title={d.name}>{d.name}</div>
                                    <div className="text-xs text-slate-400 mt-0.5">{d.docType} · {d.pages} page(s)</div>
                                </div>
                                <div className="flex flex-col gap-1.5 items-end shrink-0">
                                    <span className={`rounded-full border px-2.5 py-1 text-xs ${badgeClass[d.badge]}`}>
                                        {d.status}
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => onViewMeta(d, idx)}
                                        className="flex items-center gap-1 rounded-xl border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5 text-xs font-bold hover:border-cyan-400/30 transition-colors"
                                    >
                                        <Eye className="w-3 h-3" /> View meta
                                    </button>
                                </div>
                            </div>
                        ))
                    )}
                </div>

                {/* Planned badges */}
                <div className="flex flex-wrap gap-2 pt-2 text-xs text-slate-400">
                    {["Workspace isolation", "PII redaction", "Prompt injection defense"].map((s) => (
                        <span key={s} className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1.5">
                            <strong className="text-white">Planned</strong> {s}
                        </span>
                    ))}
                </div>
            </div>
        </section>
    )
}
