import { useState, useEffect } from 'react'
import * as API from '../api/client'

const GRADE_DIMS = [
  { key: 'correctness', label: 'Correctness', hint: 'Scientifically correct?' },
  { key: 'relevance', label: 'Relevance', hint: 'Answers the question?' },
  { key: 'completeness', label: 'Completeness', hint: 'Covers requested info?' },
  { key: 'grounding', label: 'Grounding', hint: 'Claims supported?' },
  { key: 'citation_quality', label: 'Citation Quality', hint: 'Citations support claims?' },
  { key: 'directness', label: 'Directness', hint: 'Direct, no digression?' },
]

interface GradingPanelProps {
  graderId: string
  setGraderId: (v: string) => void
}

export function GradingPanel({ graderId, setGraderId }: GradingPanelProps) {
  const [mode, setMode] = useState<'single' | 'pairwise'>('single')
  const [cases, setCases] = useState<any[]>([])
  const [idx, setIdx] = useState(0)
  const [detail, setDetail] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [scores, setScores] = useState<Record<string, number>>({
    correctness: 3, relevance: 3, completeness: 3, grounding: 3, citation_quality: 3, directness: 3
  })
  const [comments, setComments] = useState('')
  const [consensus, setConsensus] = useState<any>(null)
  const [filter, setFilter] = useState<'all' | 'ungraded' | 'disagreements'>('all')

  // Pairwise
  const [pair, setPair] = useState<any>(null)
  const [pref, setPref] = useState<string>('A')
  const [pairReason, setPairReason] = useState('')

  useEffect(() => { API.gradingCases(false).then(setCases).catch(() => {}) }, [])

  const list = cases.filter((c: any) =>
    filter === 'all' ? true : filter === 'ungraded' ? (c.grade_count || 0) === 0 : true
  )
  const c = list[Math.min(idx, Math.max(0, list.length - 1))]

  const loadAnswer = async () => {
    if (!c) return
    setLoading(true)
    try {
      const d = await API.gradingCases(true).then((all: any) => all.find((x: any) => x.id === c.id))
      setDetail(d || c)
      const cons = await API.gradingConsensus(c.id)
      setConsensus(cons)
    } catch (e: any) { alert(e.message) }
    setLoading(false)
  }

  const loadPair = async () => {
    if (!c) return
    setLoading(true)
    try { setPair(await API.makePair(c.id, 7 + idx)) } catch (e: any) { alert(e.message) }
    setLoading(false)
  }

  const saveGrade = async () => {
    if (!c) return
    try {
      await API.submitGrade({
        evaluation_case_id: c.id,
        answer_text: detail?.system_answer || '(no answer)',
        source_ids: (detail?.citations || []).map((x: any) => x.chunk_id),
        grader_id: graderId || 'anonymous',
        ...scores, comments
      })
      alert('Grade saved')
      setComments('')
      const upd = await API.gradingCases(false)
      setCases(upd)
    } catch (e: any) { alert(e.response?.data?.detail || e.message) }
  }

  const savePairwise = async () => {
    try {
      await API.submitPairwiseBlind({
        pair_id: pair.pair_id, grader_id: graderId || 'anonymous',
        preferred_answer: pref, reason: pairReason
      })
      alert('Preference saved')
      setPair(null)
      setPairReason('')
    } catch (e: any) { alert(e.response?.data?.detail || e.message) }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1">
        <button onClick={() => setMode(mode === 'single' ? 'pairwise' : 'single')}
          className="btn text-[11px] py-1">
          {mode === 'single' ? 'Single → Pairwise' : 'Pairwise → Single'}
        </button>
      </div>

      <GradingProgressInner />

      {mode === 'pairwise' ? (
        <PairwiseGrading
          cases={cases} idx={idx} setIdx={setIdx}
          pair={pair} setPair={setPair} loadPair={loadPair}
          pref={pref} setPref={setPref} pairReason={pairReason} setPairReason={setPairReason}
          savePairwise={savePairwise} loading={loading}
        />
      ) : (
        <>
          <div className="flex items-center gap-1 text-[11px]">
            <input value={graderId} onChange={e => setGraderId(e.target.value)}
              placeholder="grader id" className="input w-24 text-[11px] py-1" />
            <select value={filter} onChange={e => setFilter(e.target.value as any)}
              className="input text-[11px] py-1">
              <option value="all">All</option>
              <option value="ungraded">Ungraded</option>
              <option value="disagreements">Disagreements</option>
            </select>
            <button onClick={async () => {
              setLoading(true)
              try { setCases(await API.gradingCases(false)); setIdx(0) } catch {}
              setLoading(false)
            }} className="btn text-[11px] py-1">Refresh</button>
          </div>

          {loading && <div className="text-[10px]" style={{ color: 'var(--text-faint)' }}>Loading...</div>}

          {c && (
            <div className="space-y-2">
              <div className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                Case {Math.min(idx + 1, list.length)}/{list.length} · {c.category} · grades: {c.grade_count || 0}
              </div>
              <div className="px-2 py-1.5 rounded text-[11px]"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                <div className="font-medium" style={{ color: 'var(--text-secondary)' }}>{c.question}</div>
                <div className="flex gap-1 mt-1">
                  <button disabled={idx <= 0} onClick={() => { setIdx(i => Math.max(0, i - 1)); setDetail(null); setConsensus(null) }}
                    className="btn text-[10px] py-0.5 disabled:opacity-40">Prev</button>
                  <button disabled={idx >= list.length - 1} onClick={() => { setIdx(i => Math.min(list.length - 1, i + 1)); setDetail(null); setConsensus(null) }}
                    className="btn text-[10px] py-0.5 disabled:opacity-40">Next</button>
                  <button onClick={loadAnswer} className="btn btn-primary text-[10px] py-0.5">Load</button>
                </div>
              </div>

              {detail?.system_answer && (
                <div className="px-2 py-1.5 rounded text-[11px] space-y-1"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                  <div className="font-medium" style={{ color: 'var(--text-muted)' }}>Answer</div>
                  <div className="whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>
                    {detail.system_answer.slice(0, 1200)}
                  </div>
                </div>
              )}

              {GRADE_DIMS.map(d => (
                <div key={d.key} className="px-2 py-1.5 rounded"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                  <div className="text-[10px] font-medium" style={{ color: 'var(--text-secondary)' }}>
                    {d.label} <span style={{ color: 'var(--text-faint)' }}>— {d.hint}</span>
                  </div>
                  <div className="flex gap-1 mt-1">
                    {[1, 2, 3, 4, 5].map(v => (
                      <button key={v} onClick={() => setScores(s => ({ ...s, [d.key]: v }))}
                        className="w-6 h-6 rounded text-[11px] font-semibold transition-panel"
                        style={{
                          background: scores[d.key] === v ? 'var(--accent)' : 'var(--bg-panel)',
                          color: scores[d.key] === v ? '#fff' : 'var(--text-muted)',
                          border: '1px solid var(--border)'
                        }}>
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
              ))}

              <textarea value={comments} onChange={e => setComments(e.target.value)}
                placeholder="Optional comments" className="input w-full text-[11px]" rows={2} />
              <button onClick={saveGrade} className="btn btn-primary w-full text-[12px] py-2">
                Save grade
              </button>

              {consensus?.grader_count > 0 && (
                <div className="text-[10px] px-2 py-1.5 rounded"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-faint)' }}>
                  Consensus ({consensus.grader_count} graders): {consensus.consensus_score}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function GradingProgressInner() {
  const [prog, setProg] = useState<any>(null)
  useEffect(() => { API.gradingProgress().then(setProg).catch(() => {}) }, [])
  if (!prog) return null
  const pct = prog.total ? Math.round(100 * prog.graded / prog.total) : 0
  return (
    <div className="px-2 py-1.5 rounded text-[10px]"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <div className="flex justify-between" style={{ color: 'var(--text-muted)' }}>
        <span>{prog.graded}/{prog.total} graded</span>
        <button onClick={() => API.gradingProgress().then(setProg).catch(() => {})}
          className="underline" style={{ color: 'var(--accent)' }}>refresh</button>
      </div>
      <div className="w-full h-1 rounded mt-1 overflow-hidden" style={{ background: 'var(--border)' }}>
        <div className="h-full rounded" style={{ width: `${pct}%`, background: 'var(--accent)' }} />
      </div>
    </div>
  )
}

function PairwiseGrading({
  cases, idx, setIdx, pair, setPair, loadPair,
  pref, setPref, pairReason, setPairReason, savePairwise, loading
}: any) {
  const c = cases[idx]
  return (
    <div className="space-y-2">
      <div className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
        Blinded A/B: systems hidden until after grading.
      </div>
      <div className="flex gap-1">
        <button disabled={idx <= 0} onClick={() => { setIdx((i: number) => Math.max(0, i - 1)); setPair(null) }}
          className="btn text-[10px] py-0.5 disabled:opacity-40">Prev</button>
        <button disabled={idx >= cases.length - 1} onClick={() => { setIdx((i: number) => Math.min(cases.length - 1, i + 1)); setPair(null) }}
          className="btn text-[10px] py-0.5 disabled:opacity-40">Next ({idx + 1}/{cases.length})</button>
        <button onClick={loadPair} className="btn btn-primary text-[10px] py-0.5">Load pair</button>
      </div>
      {c && <div className="text-[11px] font-medium px-2 py-1.5 rounded"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        {c.question}
      </div>}
      {loading && <div className="text-[10px]" style={{ color: 'var(--text-faint)' }}>Generating...</div>}
      {pair && (
        <>
          <div className="px-2 py-1.5 rounded text-[10px]"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
            <div className="font-semibold mb-0.5" style={{ color: 'var(--text-muted)' }}>Answer A</div>
            <div className="whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>
              {pair.answer_a.slice(0, 1000)}
            </div>
          </div>
          <div className="px-2 py-1.5 rounded text-[10px]"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
            <div className="font-semibold mb-0.5" style={{ color: 'var(--text-muted)' }}>Answer B</div>
            <div className="whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>
              {pair.answer_b.slice(0, 1000)}
            </div>
          </div>
          <div className="flex gap-1">
            {['A', 'B', 'tie'].map(v => (
              <button key={v} onClick={() => setPref(v)}
                className="px-3 py-1 rounded text-[11px] font-semibold transition-panel"
                style={{
                  background: pref === v ? 'var(--accent)' : 'var(--bg-panel)',
                  color: pref === v ? '#fff' : 'var(--text-muted)',
                  border: '1px solid var(--border)'
                }}>
                {v === 'tie' ? 'Same' : v}
              </button>
            ))}
          </div>
          <textarea value={pairReason} onChange={e => setPairReason(e.target.value)}
            placeholder="Reason (required)" className="input w-full text-[11px]" rows={2} />
          <button onClick={savePairwise} className="btn btn-primary w-full text-[11px] py-1.5">
            Save preference
          </button>
        </>
      )}
    </div>
  )
}
