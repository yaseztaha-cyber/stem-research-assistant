import { useState } from 'react'
import { Send, BookOpen, FlaskConical, BarChart3, Lightbulb, Loader2, ChevronDown, ExternalLink, AlertTriangle, X } from 'lucide-react'
import * as API from '../api/client'

interface Props {
  messages: any[]
  query: string
  setQuery: (v: string) => void
  loading: boolean
  onQuery: () => void
  onGenerate: (type: string) => void
  onAnalyze: (kind: 'paper' | 'lab' | 'dataset') => void
  selectedDoc: string | null
  selectedCollection: string | null
  collections: any[]
  docs: any[]
  scopeLabel: string
  grounded: boolean
  setGrounded: (v: boolean) => void
  explainLevel: string
  setExplainLevel: (v: string) => void
  developerMode: boolean
  onShowEvidence: (e: any) => void
  setShowEvidenceModal: (v: any) => void
}

export function MainWorkspace({
  messages, query, setQuery, loading, onQuery,
  onGenerate, onAnalyze, selectedDoc, selectedCollection,
  collections, docs, scopeLabel, grounded, setGrounded,
  explainLevel, setExplainLevel, developerMode,
  onShowEvidence, setShowEvidenceModal
}: Props) {
  const [scopeOpen, setScopeOpen] = useState(false)

  const quickActions = [
    { id: 'explain', label: 'Explain', icon: <Lightbulb size={12} /> },
    { id: 'equations', label: 'Equations', icon: <BarChart3 size={12} /> },
    { id: 'flashcards', label: 'Flashcards', icon: <BookOpen size={12} /> },
    { id: 'problems', label: 'Problems', icon: <FlaskConical size={12} /> },
  ]

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Research Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b"
        style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}>
        {/* Scope selector */}
        <div className="relative">
          <button onClick={() => setScopeOpen(!scopeOpen)}
            className="flex items-center gap-1.5 text-[11px] px-2 py-1 rounded"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
            <span className="max-w-[180px] truncate">{scopeLabel}</span>
            <ChevronDown size={11} />
          </button>
          {scopeOpen && (
            <div className="absolute top-full left-0 mt-1 w-52 rounded z-20 py-1"
              style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-md)' }}>
              <ScopeOption label="All sources" active={!selectedCollection && !selectedDoc}
                onClick={() => { setScopeOpen(false) }} />
              {selectedDoc && (
                <ScopeOption label="Current document" active={!!selectedDoc && !selectedCollection}
                  onClick={() => { setScopeOpen(false) }} />
              )}
              {selectedCollection && (
                <ScopeOption label={`Collection: ${collections.find(c => c.id === selectedCollection)?.name}`}
                  active={!!selectedCollection}
                  onClick={() => { setScopeOpen(false) }} />
              )}
            </div>
          )}
        </div>

        <label className="flex items-center gap-1.5 text-[11px] cursor-pointer"
          style={{ color: grounded ? 'var(--accent)' : 'var(--text-faint)' }}>
          <input type="checkbox" checked={grounded}
            onChange={e => setGrounded(e.target.checked)}
            className="w-3 h-3 rounded" />
          Source-Grounded
        </label>

        <select value={explainLevel} onChange={e => setExplainLevel(e.target.value)}
          className="input text-[11px] py-1 px-2">
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="advanced">Advanced</option>
          <option value="research">Research</option>
        </select>

        <div className="ml-auto flex gap-1">
          <button onClick={() => onAnalyze('paper')} className="btn text-[11px] py-1">Paper</button>
          <button onClick={() => onAnalyze('lab')} className="btn text-[11px] py-1">Lab</button>
          <button onClick={() => onAnalyze('dataset')} className="btn text-[11px] py-1">Dataset</button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {messages.length === 0 ? (
          <EmptyState
            onQuery={(q) => { setQuery(q); }}
            onGenerate={onGenerate}
            onSubmitQuery={onQuery}
          />
        ) : (
          <div className="max-w-[800px] mx-auto p-4 space-y-4">
            {messages.map((m, idx) => (
              <MessageBubble key={idx} message={m} developerMode={developerMode}
                onShowEvidence={onShowEvidence}
                setShowEvidenceModal={setShowEvidenceModal} />
            ))}
          </div>
        )}

        {loading && (
          <div className="max-w-[800px] mx-auto px-4 pb-4">
            <div className="flex items-center gap-2 text-[12px] px-3 py-2 rounded"
              style={{ color: 'var(--text-muted)', background: 'var(--bg-surface)' }}>
              <Loader2 size={14} className="animate-spin" style={{ color: 'var(--accent)' }} />
              Processing your research question...
            </div>
          </div>
        )}
      </div>

      {/* Query bar */}
      <div className="px-4 py-3 border-t"
        style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}>
        <div className="flex gap-2">
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onQuery() } }}
            placeholder="Ask a research question..."
            className="input flex-1 py-2.5 text-[13px]"
          />
          <button onClick={onQuery} disabled={loading || !query.trim()}
            className="btn btn-primary px-4 py-2.5 text-[13px]">
            <Send size={14} />
          </button>
        </div>
        <div className="flex items-center gap-2 mt-2">
          {quickActions.map(a => (
            <button key={a.id} onClick={() => onGenerate(a.id)}
              className="flex items-center gap-1 text-[11px] px-2 py-1 rounded transition-panel hover:bg-[var(--bg-hover)]"
              style={{ color: 'var(--text-muted)' }}>
              {a.icon}
              {a.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function EmptyState({ onQuery, onGenerate, onSubmitQuery }: { onQuery: (q: string) => void; onGenerate: (t: string) => void; onSubmitQuery: () => void }) {
  const suggestions = [
    { q: 'Explain the main mechanism', label: 'Explain a concept' },
    { q: 'What equation defines electrical power?', label: 'Find an equation' },
    { q: 'Compare experimental methods', label: 'Compare methods' },
    { q: 'What are key experimental results?', label: 'Key results' },
  ]

  return (
    <div className="flex items-center justify-center h-full min-h-[400px] grid-bg">
      <div className="max-w-[440px] text-center px-6">
        <div className="text-[13px] font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          Ready to research
        </div>
        <div className="text-[12px] mb-5" style={{ color: 'var(--text-muted)' }}>
          Select your sources, choose a scope, and ask a question.
        </div>
        <div className="space-y-1.5">
          {suggestions.map(s => (
            <button key={s.q}
              onClick={() => { onQuery(s.q) }}
              className="flex items-center gap-2 w-full px-3 py-2 rounded text-left text-[12px] transition-panel hover:bg-[var(--bg-hover)]"
              style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
              <span style={{ color: 'var(--accent)' }}>&#8594;</span>
              {s.label}
              <span className="ml-auto text-[10px] truncate max-w-[200px]"
                style={{ color: 'var(--text-faint)' }}>
                {s.q}
              </span>
            </button>
          ))}
        </div>
        <div className="flex items-center justify-center gap-2 mt-5">
          <button onClick={() => onGenerate('flashcards')} className="btn text-[11px]">
            <BookOpen size={12} /> Flashcards
          </button>
          <button onClick={() => onGenerate('problems')} className="btn text-[11px]">
            <FlaskConical size={12} /> Problems
          </button>
          <button onClick={() => onGenerate('questions')} className="btn text-[11px]">
            <BarChart3 size={12} /> Questions
          </button>
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ message: m, developerMode, onShowEvidence, setShowEvidenceModal }: any) {
  const isUser = m.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : ''}`}>
      <div className={isUser ? 'px-3 py-2 rounded-lg text-[13px] max-w-[70%]'
        : 'w-full rounded-lg p-4'}
        style={isUser
          ? { background: 'var(--accent)', color: '#fff' }
          : { background: 'var(--bg-surface)', border: '1px solid var(--border)' }
        }>

        {isUser ? m.content : (
          <div className="space-y-3 prose-scientific">
            <div className="text-[13px] leading-6 whitespace-pre-wrap"
              style={{ color: 'var(--text-secondary)' }}>
              {m.content}
            </div>

            {/* Grounding */}
            {m.grounding && (
              <div className="p-3 rounded"
                style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-semibold tracking-[0.1em] uppercase"
                    style={{ color: 'var(--text-muted)' }}>
                    Grounding
                  </span>
                  <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${m.grounding.percentage > 70 ? 'badge-supported' : m.grounding.percentage > 40 ? 'badge-partial' : 'badge-unsupported'}`}>
                    {m.grounding.percentage}%
                  </span>
                </div>
                <div className="h-1.5 rounded overflow-hidden mb-2"
                  style={{ background: 'var(--border)' }}>
                  <div className="h-full rounded transition-all"
                    style={{ width: `${m.grounding.percentage}%`, background: 'var(--accent)' }} />
                </div>
                <div className="grid grid-cols-3 gap-2 text-[9px]" style={{ color: 'var(--text-faint)' }}>
                  <span>Retrieval {m.grounding.factors?.retrieval_relevance}</span>
                  <span>Coverage {m.grounding.factors?.evidence_coverage}</span>
                  <span>Alignment {m.grounding.factors?.claim_source_alignment}</span>
                </div>
              </div>
            )}

            {/* Citations */}
            {m.citations?.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {m.citations.slice(0, 4).map((c: any, i: number) => (
                  <button key={i} onClick={() => setShowEvidenceModal(c)}
                    className="flex items-center gap-1 text-[10px] px-2 py-1 rounded transition-panel hover:bg-[var(--bg-hover)]"
                    style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                    <ExternalLink size={10} />
                    {c.document} p.{c.page}
                  </button>
                ))}
              </div>
            )}

            {/* Evidence */}
            {m.evidence?.length > 0 && (
              <details className="text-[11px]">
                <summary className="cursor-pointer" style={{ color: 'var(--text-muted)' }}>
                  Evidence ({m.evidence.length})
                </summary>
                <div className="mt-2 space-y-1.5">
                  {m.evidence.slice(0, 3).map((e: any, i: number) => (
                    <div key={i} className="px-2 py-1.5 rounded text-[11px]"
                      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                      <div className="font-medium" style={{ color: 'var(--text-secondary)' }}>
                        {e.document_name} p.{e.page_number}
                      </div>
                      <div style={{ color: 'var(--text-faint)' }}>{e.text.slice(0, 120)}...</div>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {/* Developer */}
            {developerMode && m.trace && (
              <details className="text-[10px]">
                <summary className="cursor-pointer" style={{ color: 'var(--text-faint)' }}>
                  Retrieval trace
                </summary>
                <pre className="mt-1 p-2 rounded font-mono overflow-auto"
                  style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', color: 'var(--text-faint)' }}>
                  {JSON.stringify(m.trace, null, 2)}
                </pre>
              </details>
            )}

            {developerMode && m.claims && (
              <details className="text-[11px]">
                <summary className="cursor-pointer" style={{ color: 'var(--text-faint)' }}>
                  Claim verification ({m.claims?.length || m.grounding?.factors?.total_claims})
                </summary>
                <div className="mt-2 space-y-1">
                  {m.claims?.slice(0, 5).map((c: any, i: number) => (
                    <div key={i} className="flex items-center gap-2 px-2 py-1 rounded"
                      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                      <span className={`badge ${c.type === 'source' ? 'badge-source' : c.type === 'derived' ? 'badge-derived' : 'badge-generated'}`}>
                        {c.type === 'source' ? 'SOURCE' : c.type === 'derived' ? 'DERIVED' : 'GENERATED'}
                      </span>
                      <span className="flex-1 truncate text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                        {c.text?.slice(0, 80)}
                      </span>
                      <span className={`badge ${c.support_status === 'supported' ? 'badge-supported' : c.support_status === 'partially_supported' ? 'badge-partial' : 'badge-unsupported'}`}>
                        {c.support_status || c.claim_type}
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function ScopeOption({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className="flex items-center w-full px-3 py-1.5 text-[11px] text-left"
      style={{
        background: active ? 'var(--accent-soft)' : 'transparent',
        color: active ? 'var(--accent)' : 'var(--text-secondary)'
      }}>
      {label}
    </button>
  )
}
