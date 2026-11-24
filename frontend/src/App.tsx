import { useEffect, useState, useCallback } from 'react'
import * as API from './api/client'
import { GlobalHeader } from './components/GlobalHeader'
import { LibrarySidebar } from './components/LibrarySidebar'
import { MainWorkspace } from './components/MainWorkspace'
import { ResearchInspector } from './components/ResearchInspector'
import { CommandPalette } from './components/CommandPalette'
import { EvidenceModal } from './components/EvidenceModal'
import { GradingPanel } from './components/GradingPanel'

export default function App() {
  const [docs, setDocs] = useState<API.Document[]>([])
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null)
  const [collections, setCollections] = useState<any[]>([])
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [grounded, setGrounded] = useState(true)
  const [messages, setMessages] = useState<any[]>([])
  const [retrieved, setRetrieved] = useState<any[]>([])
  const [grounding, setGrounding] = useState<any>(null)
  const [citations, setCitations] = useState<any[]>([])
  const [equations, setEquations] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [health, setHealth] = useState<any>(null)
  const [retrievalTrace, setRetrievalTrace] = useState<any>(null)
  const [queryType, setQueryType] = useState<string | null>(null)
  const [developerMode, setDeveloperMode] = useState(false)
  const [dark, setDark] = useState(false)
  const [showEvidenceModal, setShowEvidenceModal] = useState<any>(null)
  const [explainLevel, setExplainLevel] = useState('intermediate')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [graderId, setGraderId] = useState('local-grader')
  const [evalRes, setEvalRes] = useState<any>(null)

  const refreshDocs = async () => {
    const d = await API.listDocuments()
    setDocs(d)
    if (d.length && !selectedDoc) setSelectedDoc(d[0].id)
  }
  const refreshCols = async () => {
    const c = await API.listCollections()
    setCollections(c)
  }
  const refreshEquations = async (docId?: string) => {
    const e = await API.getEquations(docId || selectedDoc || undefined)
    setEquations(e)
  }

  useEffect(() => {
    refreshDocs()
    refreshCols()
    API.health().then(setHealth).catch(() => {})
    if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) setDark(true)
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  useEffect(() => {
    if (selectedDoc) refreshEquations(selectedDoc)
  }, [selectedDoc])

  // Ctrl+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setPaletteOpen(v => !v)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return
    setUploading(true)
    for (const f of Array.from(files)) {
      try { await API.uploadDocument(f) }
      catch (e: any) { alert('Upload failed: ' + (e.response?.data?.detail || e.message)) }
    }
    setUploading(false)
    refreshDocs()
  }

  const handleQuery = async () => {
    if (!query.trim()) return
    setLoading(true)
    try {
      let payload: any = { query, grounded_mode: grounded, top_k: 6 }
      if (selectedCollection) payload.collection_id = selectedCollection
      else if (selectedDoc) payload.document_ids = [selectedDoc]

      if (query.toLowerCase().startsWith('explain')) {
        const concept = query.replace(/^explain/i, '').trim() || 'Seebeck effect'
        const res = await API.explain({
          concept, level: explainLevel,
          document_ids: payload.document_ids,
          collection_id: payload.collection_id
        })
        setMessages(m => [...m,
          { role: 'user', content: query },
          { role: 'assistant', content: res.explanation, evidence: res.sources }
        ])
        setRetrieved(res.sources || [])
        setGrounding(null)
        setCitations([])
      } else {
        const res = await API.ragQuery(payload)
        setMessages(m => [...m, {
          role: 'user', content: query,
        }, {
          role: 'assistant', content: res.answer,
          grounding: res.grounding, evidence: res.retrieved,
          citations: res.citations, trace: res.retrieval_trace,
          query_type: res.query_type, claims: res.claims
        }])
        setRetrieved(res.retrieved)
        setGrounding(res.grounding)
        setCitations(res.citations)
        setRetrievalTrace(res.retrieval_trace)
        setQueryType(res.query_type)
      }
      setQuery('')
    } catch (e: any) {
      alert('Query failed: ' + (e.response?.data?.detail || e.message))
    }
    setLoading(false)
  }

  const handleGenerate = async (type: string) => {
    try {
      if (type === 'flashcards') {
        const data = await API.flashcards(selectedDoc || undefined)
        setMessages(m => [...m, { role: 'assistant', content: `Generated ${data.length} flashcards.`, flashcards: data }])
      } else if (type === 'problems') {
        const data = await API.problems(selectedDoc || undefined, 'medium')
        setMessages(m => [...m, { role: 'assistant', content: `Generated ${data.length} practice problems.`, problems: data }])
      } else if (type === 'questions') {
        const data = await API.questions(selectedDoc || undefined)
        setMessages(m => [...m, { role: 'assistant', content: `Generated ${data.length} research questions.`, questions: data }])
      } else if (type === 'equations') {
        await refreshEquations(selectedDoc || undefined)
      }
    } catch (e: any) { alert(e.message) }
  }

  const handleAnalyze = async (kind: 'paper' | 'lab' | 'dataset') => {
    if (!selectedDoc) return
    try {
      const res = kind === 'paper' ? await API.analyzePaper(selectedDoc)
        : kind === 'lab' ? await API.analyzeLab(selectedDoc)
        : await API.analyzeDataset(selectedDoc)
      setMessages(m => [...m, {
        role: 'assistant', content: JSON.stringify(res, null, 2), [kind]: res
      }])
    } catch (e: any) { alert(e.response?.data?.detail || e.message) }
  }

  const runEval = async () => {
    try {
      const r = await API.evaluation()
      setEvalRes(r)
      alert(`Eval: Recall ${r.summary.retrieval_recall} Prec ${r.summary.retrieval_precision}`)
    } catch (e: any) { alert(e.message) }
  }

  const handlePaletteAction = (action: string) => {
    if (action === 'ask') { /* focus query */ }
    else if (action === 'explain') setQuery('Explain the main mechanism at ' + explainLevel + ' level')
    else if (action === 'flashcards') handleGenerate('flashcards')
    else if (action === 'problems') handleGenerate('problems')
    else if (action === 'questions') handleGenerate('questions')
    else if (action === 'equations') handleGenerate('equations')
    else if (action === 'paper') handleAnalyze('paper')
    else if (action === 'lab') handleAnalyze('lab')
    else if (action === 'dataset') handleAnalyze('dataset')
    else if (action === 'eval') runEval()
    else if (action === 'developer') setDeveloperMode(v => !v)
    else if (action.startsWith('doc:')) {
      setSelectedDoc(action.slice(4))
      setSelectedCollection(null)
    }
  }

  const scopeLabel = selectedCollection
    ? collections.find(c => c.id === selectedCollection)?.name || 'Collection'
    : selectedDoc
      ? docs.find(d => d.id === selectedDoc)?.original_filename || 'Document'
      : 'All sources'

  return (
    <div className="shell-grid">
      {/* Header */}
      <GlobalHeader
        dark={dark} setDark={setDark}
        developerMode={developerMode} setDeveloperMode={setDeveloperMode}
        health={health} scopeLabel={scopeLabel}
        sidebarOpen={sidebarOpen} setSidebarOpen={setSidebarOpen}
        inspectorOpen={inspectorOpen} setInspectorOpen={setInspectorOpen}
        onOpenPalette={() => setPaletteOpen(true)}
        onRunEval={runEval}
      />

      {/* Sidebar */}
      <div className={`shell-sidebar overflow-hidden ${sidebarOpen ? 'open' : ''}`}>
        <LibrarySidebar
          docs={docs} selectedDoc={selectedDoc} setSelectedDoc={(id) => { setSelectedDoc(id); setSelectedCollection(null); setSidebarOpen(false) }}
          collections={collections} selectedCollection={selectedCollection} setSelectedCollection={setSelectedCollection}
          uploading={uploading} onUpload={handleUpload}
          onRefreshDocs={refreshDocs} onRefreshCols={refreshCols}
        />
      </div>

      {/* Main Workspace */}
      <div className="shell-workspace overflow-hidden">
        <MainWorkspace
          messages={messages} query={query} setQuery={setQuery}
          loading={loading} onQuery={handleQuery}
          onGenerate={handleGenerate} onAnalyze={handleAnalyze}
          selectedDoc={selectedDoc} selectedCollection={selectedCollection}
          collections={collections} docs={docs} scopeLabel={scopeLabel}
          grounded={grounded} setGrounded={setGrounded}
          explainLevel={explainLevel} setExplainLevel={setExplainLevel}
          developerMode={developerMode}
          onShowEvidence={(e) => setShowEvidenceModal(e)}
          setShowEvidenceModal={setShowEvidenceModal}
        />
      </div>

      {/* Inspector */}
      <div className={`shell-inspector overflow-hidden ${inspectorOpen ? 'open' : ''}`}>
        <ResearchInspector
          retrieved={retrieved} citations={citations} grounding={grounding}
          equations={equations} developerMode={developerMode}
          retrievalTrace={retrievalTrace} queryType={queryType}
          onShowEvidence={(e) => setShowEvidenceModal(e)}
          selectedDoc={selectedDoc} docs={docs}
        />
      </div>

      {/* Command Palette */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)}
        onAction={handlePaletteAction} docs={docs} />

      {/* Evidence Modal */}
      <EvidenceModal data={showEvidenceModal} onClose={() => setShowEvidenceModal(null)} />
    </div>
  )
}
