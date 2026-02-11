import { useRef, useState } from "react"
import { Eye, FileUp, RefreshCcw, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { completeUpload, createUploadUrl, deleteDocument } from "./api"
import { guessDocType } from "./mockData"
import type { HousingDocument } from "./types"

const badgeClass: Record<string, string> = {
  good: "bg-emerald-500/10 border-emerald-500/25 text-emerald-400",
  warn: "bg-amber-400/10 border-amber-400/28 text-amber-300",
  bad: "bg-red-400/10 border-red-400/26 text-red-400",
  info: "bg-cyan-400/10 border-cyan-400/26 text-cyan-300",
}

interface Props {
  docs: HousingDocument[]
  setDocs: React.Dispatch<React.SetStateAction<HousingDocument[]>>
  onViewMeta: (doc: HousingDocument) => void
  refreshDocuments: () => Promise<void>
}

export default function DocumentsPanel({ docs, setDocs, onViewMeta, refreshDocuments }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return

    setUploading(true)
    const loadingToast = toast.loading("Uploading files...")

    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        const docType = guessDocType(file.name)

        const init = await createUploadUrl({
          filename: file.name,
          doc_type: docType,
          content_type: file.type || "application/octet-stream",
          size_bytes: file.size,
        })

        const uploadResponse = await fetch(init.upload_url, {
          method: "PUT",
          headers: init.required_headers,
          body: file,
        })

        if (!uploadResponse.ok) {
          const errText = await uploadResponse.text()
          throw new Error(`Direct upload failed for ${file.name}: ${uploadResponse.status} ${errText}`)
        }

        const etag = uploadResponse.headers.get("etag") || uploadResponse.headers.get("ETag") || undefined
        await completeUpload(init.document_id, etag)
      }

      await refreshDocuments()
      toast.dismiss(loadingToast)
      toast.success("Documents uploaded", { description: "Ingestion started. Refresh to see status changes." })
    } catch (err) {
      toast.dismiss(loadingToast)
      toast.error("Upload failed", { description: err instanceof Error ? err.message : "Unknown upload error" })
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  async function removeDoc(docId: string) {
    try {
      await deleteDocument(docId)
      setDocs((prev) => prev.filter((doc) => doc.id !== docId))
      toast.success("Document deleted")
    } catch (err) {
      toast.error("Delete failed", { description: err instanceof Error ? err.message : "Unknown error" })
    }
  }

  return (
    <section
      className="rounded-2xl border border-white/[0.08] bg-gradient-to-b from-white/[0.03] to-transparent shadow-xl overflow-hidden"
      style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.03), transparent 32%), #121a33" }}
    >
      <h2 className="flex items-center justify-between px-4 py-3 text-sm font-semibold tracking-wide border-b border-white/[0.08]">
        <span className="flex items-center gap-2">
          <FileUp className="w-4 h-4 text-cyan-400" /> Documents
        </span>
        <span className="text-xs text-slate-400 font-medium">{docs.length} uploaded</span>
      </h2>

      <div className="p-4 space-y-3">
        <p className="text-xs text-slate-400 leading-snug">
          Upload supporting documents. Files are uploaded directly via signed URLs and processed asynchronously.
        </p>

        <label
          className="flex items-center justify-between gap-3 cursor-pointer rounded-2xl border border-dashed border-cyan-400/35 bg-cyan-400/[0.06] p-4 hover:border-cyan-400/50 transition-colors"
          htmlFor="fileInput"
        >
          <div>
            <div className="font-extrabold text-sm">Drop files here</div>
            <div className="text-xs text-slate-400">or click to choose (PDF, TXT, JPG, PNG)</div>
          </div>
          <input
            ref={fileRef}
            id="fileInput"
            type="file"
            className="hidden"
            multiple
            disabled={uploading}
            onChange={(e) => handleFiles(e.target.files)}
          />
        </label>

        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            onClick={refreshDocuments}
            className="flex items-center gap-1.5 rounded-xl border border-cyan-400/28 bg-gradient-to-r from-cyan-400/[0.18] to-emerald-400/[0.18] px-3 py-2.5 text-xs font-semibold hover:border-cyan-400/50 transition-colors"
          >
            <RefreshCcw className="w-3.5 h-3.5" /> Refresh status
          </button>
        </div>

        <div className="h-px bg-white/[0.08]" />

        <div className="flex flex-col gap-2.5">
          {docs.length === 0 ? (
            <p className="text-xs text-slate-500">No uploaded documents yet.</p>
          ) : (
            docs.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between gap-2 rounded-2xl border border-white/[0.08] bg-black/[0.12] p-3"
              >
                <div className="min-w-0">
                  <div className="text-[13px] font-bold truncate" title={doc.filename}>
                    {doc.filename}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {doc.doc_type} · {doc.pages ?? "?"} page(s)
                  </div>
                </div>
                <div className="flex flex-col gap-1.5 items-end shrink-0">
                  <span className={`rounded-full border px-2.5 py-1 text-xs ${badgeClass[doc.badge] || badgeClass.info}`}>
                    {doc.status}
                  </span>
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => onViewMeta(doc)}
                      className="flex items-center gap-1 rounded-xl border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5 text-xs font-bold hover:border-cyan-400/30 transition-colors"
                    >
                      <Eye className="w-3 h-3" /> Meta
                    </button>
                    <button
                      type="button"
                      onClick={() => removeDoc(doc.id)}
                      className="flex items-center gap-1 rounded-xl border border-red-400/25 bg-red-400/[0.08] px-2.5 py-1.5 text-xs font-bold hover:border-red-400/40 transition-colors"
                    >
                      <Trash2 className="w-3 h-3" /> Delete
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  )
}
