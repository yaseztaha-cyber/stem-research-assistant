import { useState } from 'react'
import { FileText, BookOpen, FlaskConical, Database, AlertTriangle, ChevronRight, ExternalLink } from 'lucide-react'

interface Props {
  retrieved: any[]
  citations: any[]
  grounding: any
  equations: any[]
  developerMode: boolean
  retrievalTrace: any
  queryType: string | null
  onShowEvidence: (e: any) => void
  selectedDoc: string | null
  docs: any[]
}

type InspectorTab = 'evidence' | 'claims' | 'equations' | 'source'

export function ResearchInspector({
  retrieved, citations, grounding, equations,
  developerMode, retrievalTrace, queryType,
  onShowEvidence, selectedDoc, docs
}: Props) {
  const [tab, setTab] = useState<InspectorTab>('evidence')

  const doc = docs.find(d => d.id === selectedDoc)

  const tabs: { key: InspectorTab; label: string; count?: number }[] = [
    { key: 'evidence', label: 'Evidence', count: retrieved.length || undefined },
    { key: 'claims', label: 'Claims', count: citations.length || undefined },
    { key: 'equations', label: 'Equations', count: equations.length || undefined },
    { key: 'source', label: 'Source' },
  ]

  return (
    <aside className="flex flex-col h-full overflow-hidden"
      style={{ background: 'var(--bg-panel)', borderLeft: '1px solid var(--border)' }}>

      {/* Tabs */}
      <div className="flex items-center gap-0.5 px-2 py-2 border-b"
        style={{ borderColor: 'var(--border)' }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`tab ${tab === t.key ? 'active' : ''}`}>
            {t.label}
            {t.count !== undefined && (
              <span className="ml-1 text-[9px] opacity-60">{t.count}</span>
            )}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-3">

        {/* EVIDENCE TAB */}
        {tab === 'evidence' && (
          <>
            {queryType && (
              <div className="flex items-center gap-2 px-2 py-1.5 rounded text-[10px]"
                style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}>
                <span className="font-medium">{queryType}</span>
                {retrievalTrace && (
                  <span style={{ color: 'var(--text-faint)' }}>
                    {retrievalTrace.retrieval_strategy} · {retrievalTrace.reranker}
                  </span>
                )}
              </div>
            )}

            {retrieved.length === 0 && (
              <EmptyInspector text="Select a claim, equation, or source to inspect its evidence and provenance."
                subtext={doc ? `${docs.length} sources loaded` : 'Ask a question to retrieve evidence.'} />
            )}

            {retrieved.map((r, i) => (
              <div key={i} className="rounded transition-panel"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                <div className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="badge badge-source">SOURCE</span>
                    <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>
                      {r.document_name}
                    </span>
                    <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                      p.{r.page_number}
                    </span>
                  </div>
                  {r.section && (
                    <div className="text-[10px] mt-1" style={{ color: 'var(--text-faint)' }}>
                      § {r.section}
                      {r.heading_hierarchy && ` — ${r.heading_hierarchy.slice(0, 50)}`}
                    </div>
                  )}
                  <div className="text-[12px] leading-5 mt-2 line-clamp-4"
                    style={{ color: 'var(--text-secondary)' }}>
                    {r.text.slice(0, 280)}...
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-[9px] px-1.5 py-0.5 rounded font-mono"
                      style={{ background: 'var(--bg-hover)', color: 'var(--text-faint)' }}>
                      {r.retrieval_score?.toFixed(3)}
                    </span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded"
                      style={{ background: 'var(--bg-hover)', color: 'var(--text-faint)' }}>
                      {r.content_type}
                    </span>
                    <button onClick={() => onShowEvidence(r)}
                      className="ml-auto text-[10px] flex items-center gap-1"
                      style={{ color: 'var(--accent)' }}>
                      <ExternalLink size={10} />
                      Context
                    </button>
                  </div>
                </div>
              </div>
            ))}

            {/* Citations */}
            {citations.length > 0 && (
              <div className="pt-2">
                <div className="text-[10px] font-semibold tracking-[0.1em] uppercase mb-2"
                  style={{ color: 'var(--text-muted)' }}>
                  Citations
                </div>
                {citations.slice(0, 4).map((c, i) => (
                  <div key={i} className="px-2 py-1.5 rounded mb-1 text-[11px]"
                    style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                    <div className="flex items-center gap-1.5">
                      <span style={{ color: 'var(--text-secondary)' }}>
                        {c.document} p.{c.page}
                      </span>
                      <span className={`badge ${c.validation === 'VALID' ? 'badge-supported' : 'badge-partial'}`}>
                        {c.validation || 'VALID'}
                      </span>
                    </div>
                    <div className="text-[10px] truncate mt-0.5" style={{ color: 'var(--text-faint)' }}>
                      {c.source_text?.slice(0, 60)}...
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* CLAIMS TAB */}
        {tab === 'claims' && (
          <>
            {citations.length === 0 && (
              <EmptyInspector text="No claims extracted yet."
                subtext="Ask a question to see claim-level provenance." />
            )}
            {citations.map((c, i) => (
              <div key={i} className="px-3 py-2 rounded"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`badge ${c.validation === 'VALID' ? 'badge-supported' : c.validation === 'PARTIAL' ? 'badge-partial' : 'badge-unsupported'}`}>
                    {c.validation || 'VALID'}
                  </span>
                  <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                    {c.document} p.{c.page}
                  </span>
                </div>
                <div className="text-[12px] leading-5" style={{ color: 'var(--text-secondary)' }}>
                  {c.claim_text || c.source_text?.slice(0, 150) || '—'}
                </div>
                <button onClick={() => onShowEvidence(c)}
                  className="text-[10px] mt-1 flex items-center gap-1"
                  style={{ color: 'var(--accent)' }}>
                  <ExternalLink size={10} />
                  Inspect source
                </button>
              </div>
            ))}
          </>
        )}

        {/* EQUATIONS TAB */}
        {tab === 'equations' && (
          <>
            {equations.length === 0 && (
              <EmptyInspector text="No equations extracted."
                subtext="Upload a document containing equations like V=IR." />
            )}
            {equations.map((e: any) => (
              <div key={e.id} className="rounded"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                <div className="px-3 py-2">
                  <div className="font-mono text-[14px] px-2 py-1.5 rounded"
                    style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                    {e.equation_text}
                  </div>
                  <div className="text-[10px] mt-1.5 flex items-center gap-2"
                    style={{ color: 'var(--text-faint)' }}>
                    <span>p.{e.page}</span>
                    <span>§ {e.section}</span>
                    {e.uncertain && (
                      <span className="flex items-center gap-0.5 text-amber-500">
                        <AlertTriangle size={10} />
                        uncertain
                      </span>
                    )}
                  </div>
                  {e.variables && Object.keys(e.variables).length > 0 && (
                    <div className="mt-2 space-y-0.5">
                      {Object.entries(e.variables).map(([k, v]: any) => (
                        <div key={k} className="flex items-baseline gap-2 text-[11px]">
                          <code className="font-mono font-medium" style={{ color: 'var(--accent)' }}>{k}</code>
                          <span style={{ color: 'var(--text-muted)' }}>{v.meaning}</span>
                          <span className="text-[9px]" style={{ color: 'var(--text-faint)' }}>[{v.unit}]</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </>
        )}

        {/* SOURCE TAB */}
        {tab === 'source' && (
          <>
            {!doc ? (
              <EmptyInspector text="Select a document to inspect."
                subtext="Browse your research library to select a source." />
            ) : (
              <div className="space-y-3">
                <div className="px-3 py-2 rounded"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                  <div className="flex items-center gap-2">
                    <FileText size={14} style={{ color: 'var(--accent)' }} />
                    <span className="text-[12px] font-medium">{doc.original_filename}</span>
                  </div>
                  <div className="text-[10px] mt-1" style={{ color: 'var(--text-faint)' }}>
                    {doc.page_count} pages · {doc.source_quality} · {doc.file_type}
                  </div>
                  <div className="mt-2">
                    <span className={`badge ${doc.status === 'ready' ? 'badge-supported' : doc.status === 'failed' ? 'badge-unsupported' : 'badge-partial'}`}>
                      {doc.status}
                    </span>
                  </div>
                </div>

                {grounding && (
                  <div className="px-3 py-2 rounded"
                    style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                    <div className="text-[10px] font-semibold tracking-[0.1em] uppercase mb-2"
                      style={{ color: 'var(--text-muted)' }}>
                      Grounding
                    </div>
                    <div className="flex items-center gap-2 mb-1.5">
                      <div className="flex-1 h-1.5 rounded overflow-hidden"
                        style={{ background: 'var(--border)' }}>
                        <div className="h-full rounded transition-all"
                          style={{ width: `${grounding.percentage}%`, background: 'var(--accent)' }} />
                      </div>
                      <span className="text-[12px] font-semibold" style={{ color: 'var(--accent)' }}>
                        {grounding.percentage}%
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-[9px]" style={{ color: 'var(--text-faint)' }}>
                      <div>
                        <div>Coverage</div>
                        <div className="font-medium" style={{ color: 'var(--text-muted)' }}>
                          {grounding.factors?.evidence_coverage}
                        </div>
                      </div>
                      <div>
                        <div>Alignment</div>
                        <div className="font-medium" style={{ color: 'var(--text-muted)' }}>
                          {grounding.factors?.claim_source_alignment}
                        </div>
                      </div>
                      <div>
                        <div>Quality</div>
                        <div className="font-medium" style={{ color: 'var(--text-muted)' }}>
                          {grounding.factors?.retrieval_relevance}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Developer Trace */}
        {developerMode && retrievalTrace && (
          <details className="rounded"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
            <summary className="px-3 py-2 text-[11px] font-medium cursor-pointer"
              style={{ color: 'var(--text-secondary)' }}>
              Retrieval trace
            </summary>
            <pre className="px-3 pb-3 text-[9px] font-mono overflow-auto max-h-[200px] whitespace-pre-wrap"
              style={{ color: 'var(--text-faint)' }}>
              {JSON.stringify(retrievalTrace, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </aside>
  )
}

function EmptyInspector({ text, subtext }: { text: string; subtext?: string }) {
  return (
    <div className="py-8 text-center">
      <div className="text-[12px] font-medium mb-1" style={{ color: 'var(--text-muted)' }}>{text}</div>
      {subtext && <div className="text-[11px]" style={{ color: 'var(--text-faint)' }}>{subtext}</div>}
    </div>
  )
}
