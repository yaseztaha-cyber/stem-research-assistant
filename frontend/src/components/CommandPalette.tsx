import { useEffect, useRef, useState } from 'react'
import { Search, FileText, BookOpen, FlaskConical, BarChart3, MessageSquare, Lightbulb, Play, Code, X } from 'lucide-react'
import * as API from '../api/client'

interface Props {
  open: boolean
  onClose: () => void
  onAction: (action: string) => void
  docs: any[]
}

const COMMANDS = [
  { id: 'ask', icon: <MessageSquare size={14} />, label: 'Ask a question', category: 'Research' },
  { id: 'explain', icon: <Lightbulb size={14} />, label: 'Explain a concept', category: 'Research' },
  { id: 'flashcards', icon: <BookOpen size={14} />, label: 'Generate flashcards', category: 'Learning' },
  { id: 'problems', icon: <FlaskConical size={14} />, label: 'Practice problems', category: 'Learning' },
  { id: 'questions', icon: <Search size={14} />, label: 'Research questions', category: 'Learning' },
  { id: 'equations', icon: <BarChart3 size={14} />, label: 'Key equations', category: 'Analysis' },
  { id: 'paper', icon: <FileText size={14} />, label: 'Analyze paper', category: 'Analysis' },
  { id: 'lab', icon: <FlaskConical size={14} />, label: 'Lab manual mode', category: 'Analysis' },
  { id: 'dataset', icon: <BarChart3 size={14} />, label: 'Dataset analysis', category: 'Analysis' },
  { id: 'eval', icon: <Play size={14} />, label: 'Run evaluation', category: 'System' },
  { id: 'developer', icon: <Code size={14} />, label: 'Toggle developer mode', category: 'System' },
]

export function CommandPalette({ open, onClose, onAction, docs }: Props) {
  const [query, setQuery] = useState('')
  const [selectedIdx, setSelectedIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = COMMANDS.filter(c =>
    !query || c.label.toLowerCase().includes(query.toLowerCase()) ||
    c.category.toLowerCase().includes(query.toLowerCase())
  )

  const docMatches = docs.filter(d =>
    query && d.original_filename.toLowerCase().includes(query.toLowerCase())
  ).slice(0, 3)

  useEffect(() => {
    if (open) {
      setQuery('')
      setSelectedIdx(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  useEffect(() => {
    setSelectedIdx(0)
  }, [query])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { onClose(); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIdx(i => Math.min(i + 1, filtered.length + docMatches.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIdx(i => Math.max(i - 1, 0)) }
    if (e.key === 'Enter') {
      if (selectedIdx < filtered.length) {
        onAction(filtered[selectedIdx].id)
      } else {
        const docIdx = selectedIdx - filtered.length
        if (docMatches[docIdx]) onAction(`doc:${docMatches[docIdx].id}`)
      }
      onClose()
    }
  }

  if (!open) return null

  let globalIdx = 0

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div onClick={e => e.stopPropagation()}
        className="relative w-full max-w-[480px] rounded-lg overflow-hidden"
        style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', boxShadow: '0 16px 64px rgba(0,0,0,0.25)' }}>

        <div className="flex items-center gap-2 px-4 py-3 border-b"
          style={{ borderColor: 'var(--border)' }}>
          <Search size={16} style={{ color: 'var(--text-faint)' }} />
          <input ref={inputRef} value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search sources, run commands..."
            className="flex-1 bg-transparent outline-none text-[14px]"
            style={{ color: 'var(--text-primary)' }} />
          <kbd>ESC</kbd>
        </div>

        <div className="max-h-[320px] overflow-y-auto scrollbar-thin py-1">
          {docMatches.length > 0 && (
            <div className="px-3 py-1">
              <div className="text-[9px] font-semibold tracking-[0.1em] uppercase"
                style={{ color: 'var(--text-faint)' }}>
                Documents
              </div>
              {docMatches.map(d => {
                const idx = globalIdx++
                return (
                  <button key={d.id}
                    onClick={() => { onAction(`doc:${d.id}`); onClose() }}
                    className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-left text-[12px]"
                    style={{
                      background: idx === selectedIdx ? 'var(--bg-hover)' : 'transparent',
                      color: 'var(--text-secondary)'
                    }}>
                    <FileText size={13} style={{ color: 'var(--text-faint)' }} />
                    {d.original_filename}
                    <span className="ml-auto text-[9px]" style={{ color: 'var(--text-faint)' }}>
                      {d.page_count}p
                    </span>
                  </button>
                )
              })}
            </div>
          )}

          <div className="px-3 py-1">
            {['Research', 'Learning', 'Analysis', 'System'].map(cat => {
              const items = filtered.filter(c => c.category === cat)
              if (items.length === 0) return null
              return (
                <div key={cat} className="mb-1">
                  <div className="text-[9px] font-semibold tracking-[0.1em] uppercase px-2 py-1"
                    style={{ color: 'var(--text-faint)' }}>
                    {cat}
                  </div>
                  {items.map(c => {
                    const idx = globalIdx++
                    return (
                      <button key={c.id}
                        onClick={() => { onAction(c.id); onClose() }}
                        className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-left text-[12px]"
                        style={{
                          background: idx === selectedIdx ? 'var(--bg-hover)' : 'transparent',
                          color: 'var(--text-secondary)'
                        }}>
                        <span style={{ color: 'var(--text-faint)' }}>{c.icon}</span>
                        {c.label}
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
