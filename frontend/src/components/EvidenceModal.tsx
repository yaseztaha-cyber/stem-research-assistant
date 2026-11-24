import { X, ExternalLink, FileText } from 'lucide-react'

interface Props {
  data: any
  onClose: () => void
}

export function EvidenceModal({ data, onClose }: Props) {
  if (!data) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div onClick={e => e.stopPropagation()}
        className="relative w-full max-w-[640px] max-h-[80vh] overflow-auto rounded-lg"
        style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', boxShadow: '0 16px 64px rgba(0,0,0,0.3)' }}>

        <div className="flex items-center justify-between px-4 py-3 border-b sticky top-0"
          style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <FileText size={14} style={{ color: 'var(--accent)' }} />
            <span className="text-[12px] font-semibold tracking-[0.06em] uppercase"
              style={{ color: 'var(--text-primary)' }}>
              Source Context
            </span>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-[var(--bg-hover)]"
            style={{ color: 'var(--text-muted)' }}>
            <X size={16} />
          </button>
        </div>

        {data.dataset ? (
          <pre className="p-4 text-[11px] font-mono whitespace-pre-wrap overflow-auto"
            style={{ color: 'var(--text-secondary)' }}>
            {JSON.stringify(data.dataset, null, 2)}
          </pre>
        ) : (
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-2 text-[12px]">
              <div>
                <span className="text-[10px] font-semibold tracking-[0.1em] uppercase"
                  style={{ color: 'var(--text-faint)' }}>Document</span>
                <div className="mt-0.5" style={{ color: 'var(--text-primary)' }}>
                  {data.document || data.document_name}
                </div>
              </div>
              <div>
                <span className="text-[10px] font-semibold tracking-[0.1em] uppercase"
                  style={{ color: 'var(--text-faint)' }}>Page</span>
                <div className="mt-0.5" style={{ color: 'var(--text-primary)' }}>
                  {data.page || data.page_number}
                </div>
              </div>
              {data.section && (
                <div>
                  <span className="text-[10px] font-semibold tracking-[0.1em] uppercase"
                    style={{ color: 'var(--text-faint)' }}>Section</span>
                  <div className="mt-0.5" style={{ color: 'var(--text-primary)' }}>{data.section}</div>
                </div>
              )}
              {data.retrieval_score != null && (
                <div>
                  <span className="text-[10px] font-semibold tracking-[0.1em] uppercase"
                    style={{ color: 'var(--text-faint)' }}>Retrieval Score</span>
                  <div className="mt-0.5 font-mono" style={{ color: 'var(--text-primary)' }}>
                    {data.retrieval_score?.toFixed?.(3) || data.score?.toFixed?.(3)}
                  </div>
                </div>
              )}
            </div>

            {data.support_status && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold tracking-[0.1em] uppercase"
                  style={{ color: 'var(--text-faint)' }}>Support</span>
                <span className={`badge ${data.support_status === 'supported' ? 'badge-supported' : 'badge-partial'}`}>
                  {data.support_status}
                </span>
                {data.support_score != null && (
                  <span className="text-[10px] font-mono" style={{ color: 'var(--text-faint)' }}>
                    score {data.support_score}
                  </span>
                )}
              </div>
            )}

            {data.citation_status && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold tracking-[0.1em] uppercase"
                  style={{ color: 'var(--text-faint)' }}>Citation</span>
                <span className={`badge ${data.citation_status === 'VALID' ? 'badge-supported' : 'badge-unsupported'}`}>
                  {data.citation_status}
                </span>
              </div>
            )}

            <div className="rounded p-3"
              style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
              <div className="text-[10px] font-semibold tracking-[0.1em] uppercase mb-2"
                style={{ color: 'var(--text-muted)' }}>
                Supporting passage
              </div>
              <div className="text-[12px] leading-6 whitespace-pre-wrap"
                style={{ color: 'var(--text-secondary)' }}>
                {data.source_text || data.text || JSON.stringify(data, null, 2)}
              </div>
            </div>

            <div className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
              Supported = evidence found · Partially supported = weak overlap ·
              Unsupported = no evidence · Contradicted = conflicts with source
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
