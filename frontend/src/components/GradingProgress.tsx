import { useEffect, useState } from 'react'
import * as API from '../api/client'

export function GradingProgress() {
  const [prog, setProg] = useState<any>(null)
  useEffect(() => { API.gradingProgress().then(setProg).catch(() => {}) }, [])
  if (!prog) return null
  const pct = prog.total ? Math.round(100 * prog.graded / prog.total) : 0
  return (
    <div className="px-2 py-1.5 rounded text-[10px]"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <div className="flex justify-between" style={{ color: 'var(--text-muted)' }}>
        <span>Graded {prog.graded}/{prog.total} · double {prog.double_graded} · left {prog.remaining}</span>
        <button onClick={() => API.gradingProgress().then(setProg).catch(() => {})}
          className="underline" style={{ color: 'var(--accent)' }}>
          refresh
        </button>
      </div>
      <div className="w-full h-1 rounded mt-1 overflow-hidden"
        style={{ background: 'var(--border)' }}>
        <div className="h-full rounded transition-all"
          style={{ width: `${pct}%`, background: 'var(--accent)' }} />
      </div>
    </div>
  )
}
