import { FileText, Upload, FolderPlus, ChevronDown, ChevronRight, Search, X, BookOpen, Database, FlaskConical, FileStack } from 'lucide-react'
import { useState, useRef } from 'react'
import * as API from '../api/client'

interface Props {
  docs: API.Document[]
  selectedDoc: string | null
  setSelectedDoc: (id: string | null) => void
  collections: any[]
  selectedCollection: string | null
  setSelectedCollection: (id: string | null) => void
  uploading: boolean
  onUpload: (files: FileList | null) => void
  onRefreshDocs: () => void
  onRefreshCols: () => void
}

const docIcon = (type: string) => {
  if (type === 'pdf') return <FileText size={14} />
  if (type === 'csv') return <Database size={14} />
  if (type === 'md') return <BookOpen size={14} />
  return <FileStack size={14} />
}

export function LibrarySidebar({
  docs, selectedDoc, setSelectedDoc,
  collections, selectedCollection, setSelectedCollection,
  uploading, onUpload, onRefreshDocs, onRefreshCols
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [searchQ, setSearchQ] = useState('')
  const [searchRes, setSearchRes] = useState<any>(null)
  const [docsOpen, setDocsOpen] = useState(true)
  const [colsOpen, setColsOpen] = useState(true)

  const filteredDocs = docs.filter(d =>
    !searchQ || d.original_filename.toLowerCase().includes(searchQ.toLowerCase())
  )

  const handleSearch = async () => {
    if (!searchQ.trim()) return
    try { setSearchRes(await API.search(searchQ)) } catch {}
  }

  return (
    <aside className="flex flex-col h-full overflow-hidden"
      style={{ background: 'var(--bg-panel)', borderRight: '1px solid var(--border)' }}>

      {/* Upload area */}
      <div className="px-3 pt-3 pb-2">
        <div
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); onUpload(e.dataTransfer.files) }}
          onClick={() => fileRef.current?.click()}
          className="flex items-center gap-2 px-3 py-2 rounded cursor-pointer transition-panel hover:bg-[var(--bg-hover)]"
          style={{ border: '1px dashed var(--border)' }}>
          <Upload size={14} style={{ color: 'var(--text-muted)' }} />
          <span className="text-[11px] font-medium" style={{ color: 'var(--text-secondary)' }}>
            {uploading ? 'Uploading...' : 'Add sources'}
          </span>
          <input ref={fileRef} type="file" className="hidden" multiple
            onChange={e => onUpload(e.target.files)} accept=".pdf,.txt,.md,.csv" />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {/* Documents */}
        <div className="px-2 pt-1">
          <button onClick={() => setDocsOpen(!docsOpen)}
            className="flex items-center gap-1 w-full px-2 py-1.5 text-[10px] font-semibold tracking-[0.1em] uppercase"
            style={{ color: 'var(--text-muted)' }}>
            {docsOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Recent
            <span className="ml-auto px-1.5 py-0.5 rounded text-[9px] font-medium"
              style={{ background: 'var(--bg-surface)', color: 'var(--text-faint)' }}>
              {docs.length}
            </span>
          </button>
          {docsOpen && (
            <div className="space-y-0.5">
              {filteredDocs.length === 0 && (
                <div className="px-2 py-4 text-center text-[11px]"
                  style={{ color: 'var(--text-faint)' }}>
                  {searchQ ? 'No matches' : 'No documents yet'}
                </div>
              )}
              {filteredDocs.map(d => (
                <button key={d.id} onClick={() => setSelectedDoc(d.id)}
                  className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-left transition-panel"
                  style={{
                    background: selectedDoc === d.id ? 'var(--accent-soft)' : 'transparent',
                    color: selectedDoc === d.id ? 'var(--accent)' : 'var(--text-secondary)',
                    borderLeft: selectedDoc === d.id ? '2px solid var(--accent)' : '2px solid transparent'
                  }}>
                  <span style={{ color: selectedDoc === d.id ? 'var(--accent)' : 'var(--text-faint)' }}>
                    {docIcon(d.file_type)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] font-medium truncate">{d.original_filename}</div>
                    <div className="text-[9px] flex items-center gap-1.5" style={{ color: 'var(--text-faint)' }}>
                      <span>{d.page_count}p</span>
                      <span className={`w-1.5 h-1.5 rounded-full ${d.status === 'ready' ? 'bg-emerald-500' : d.status === 'failed' ? 'bg-red-500' : 'bg-amber-500'}`} />
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Collections */}
        <div className="px-2 pt-2">
          <button onClick={() => setColsOpen(!colsOpen)}
            className="flex items-center gap-1 w-full px-2 py-1.5 text-[10px] font-semibold tracking-[0.1em] uppercase"
            style={{ color: 'var(--text-muted)' }}>
            {colsOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Collections
          </button>
          {colsOpen && (
            <div className="space-y-0.5">
              <button onClick={() => {
                const name = prompt('Collection name:')
                if (name) API.createCollection(name).then(() => onRefreshCols())
              }}
                className="flex items-center gap-1.5 w-full px-2 py-1 rounded text-[11px]"
                style={{ color: 'var(--accent)' }}>
                <FolderPlus size={12} />
                New collection
              </button>
              {collections.map(c => (
                <div key={c.id}>
                  <button onClick={() => setSelectedCollection(selectedCollection === c.id ? null : c.id)}
                    className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-left transition-panel"
                    style={{
                      background: selectedCollection === c.id ? 'var(--accent-soft)' : 'transparent',
                      color: selectedCollection === c.id ? 'var(--accent)' : 'var(--text-secondary)',
                      borderLeft: selectedCollection === c.id ? '2px solid var(--accent)' : '2px solid transparent'
                    }}>
                    <FolderPlus size={12} style={{ color: 'var(--text-faint)' }} />
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] font-medium truncate">{c.name}</div>
                      <div className="text-[9px]" style={{ color: 'var(--text-faint)' }}>
                        {c.document_ids?.length || 0} docs
                      </div>
                    </div>
                  </button>
                  {selectedCollection === c.id && selectedDoc && (
                    <button onClick={(e) => {
                      e.stopPropagation()
                      API.addToCollection(c.id, selectedDoc).then(() => onRefreshCols())
                    }}
                      className="ml-5 text-[10px] px-1.5 py-0.5 rounded mb-1"
                      style={{ color: 'var(--accent)', background: 'var(--accent-soft)' }}>
                      + Add selected
                    </button>
                  )}
                </div>
              ))}
              {collections.length === 0 && (
                <div className="px-2 py-2 text-[10px]" style={{ color: 'var(--text-faint)' }}>
                  Organize sources for multi-doc reasoning
                </div>
              )}
            </div>
          )}
        </div>

        {/* Search */}
        <div className="px-2 pt-3 pb-3">
          <div className="px-2 py-1.5 text-[10px] font-semibold tracking-[0.1em] uppercase"
            style={{ color: 'var(--text-muted)' }}>
            Search
          </div>
          <div className="flex gap-1 px-1">
            <input value={searchQ} onChange={e => setSearchQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="Sources, chunks, equations..."
              className="input flex-1 text-[11px] py-1.5" />
            {searchQ && (
              <button onClick={() => { setSearchQ(''); setSearchRes(null) }}
                className="p-1 rounded hover:bg-[var(--bg-hover)]">
                <X size={12} style={{ color: 'var(--text-faint)' }} />
              </button>
            )}
          </div>
          {searchRes && (
            <div className="mt-2 space-y-1 max-h-[160px] overflow-auto scrollbar-thin">
              {searchRes.chunks?.slice(0, 3).map((c: any, i: number) => (
                <div key={i} className="px-2 py-1.5 rounded text-[10px]"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)' }}>
                  <div className="font-medium truncate">{c.document_name} p.{c.page_number}</div>
                  <div style={{ color: 'var(--text-faint)' }}>{c.text.slice(0, 60)}...</div>
                </div>
              ))}
              {searchRes.equations?.length > 0 && (
                <div className="px-2 py-1 text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                  {searchRes.equations.map((e: any) => e.equation_text).join(', ')}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}
