import { Sun, Moon, Code, ChevronDown, Search, PanelLeftClose, PanelRightClose } from 'lucide-react'

interface Props {
  dark: boolean
  setDark: (v: boolean) => void
  developerMode: boolean
  setDeveloperMode: (v: boolean) => void
  health: any
  scopeLabel: string
  sidebarOpen: boolean
  setSidebarOpen: (v: boolean) => void
  inspectorOpen: boolean
  setInspectorOpen: (v: boolean) => void
  onOpenPalette: () => void
  onRunEval: () => void
}

export function GlobalHeader({
  dark, setDark, developerMode, setDeveloperMode,
  health, scopeLabel, sidebarOpen, setSidebarOpen,
  inspectorOpen, setInspectorOpen, onOpenPalette, onRunEval
}: Props) {
  const statusColor = health?.llm_provider ? 'bg-emerald-500' : 'bg-zinc-400'
  const statusText = health?.llm_provider
    ? `${health.llm_provider}/${health.embedding_provider}`
    : 'Offline'

  return (
    <header className="shell-header flex items-center h-[44px] px-3 border-b"
      style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}>
      <div className="flex items-center gap-3 min-w-0">
        <button onClick={() => setSidebarOpen(!sidebarOpen)}
          className="lg:hidden p-1 rounded hover:bg-[var(--bg-hover)]" title="Toggle library">
          <PanelLeftClose size={16} />
        </button>

        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded flex items-center justify-center font-mono text-[10px] font-bold"
            style={{ background: 'var(--accent)', color: '#fff' }}>
            STEM
          </div>
          <div className="hidden sm:block">
            <div className="text-[12px] font-semibold tracking-[0.06em] uppercase leading-none"
              style={{ color: 'var(--text-primary)' }}>
              AI STEM Research Assistant
            </div>
            <div className="text-[10px] leading-none mt-0.5"
              style={{ color: 'var(--text-muted)' }}>
              Source-grounded · Evidence-first
            </div>
          </div>
        </div>

        <div className="hidden md:flex items-center gap-1.5 ml-3 px-2 py-1 rounded text-[10px]"
          style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}>
          <span className={`w-1.5 h-1.5 rounded-full ${statusColor}`} />
          {statusText}
        </div>
      </div>

      <div className="flex-1 flex justify-center">
        <button onClick={onOpenPalette}
          className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded text-[11px] max-w-[280px] w-full"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-faint)' }}>
          <Search size={13} />
          <span>Search or ask a question...</span>
          <kbd className="ml-auto">Ctrl K</kbd>
        </button>
      </div>

      <div className="flex items-center gap-1.5">
        {developerMode && (
          <span className="hidden sm:flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono"
            style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
            <Code size={11} />
            DEV
          </span>
        )}

        <button onClick={onRunEval}
          className="btn hidden sm:inline-flex text-[11px] py-1"
          title="Run evaluation">
          Eval
        </button>

        <label className="flex items-center gap-1 text-[11px] cursor-pointer px-2 py-1 rounded"
          style={{ color: 'var(--text-muted)' }}>
          <input type="checkbox" checked={developerMode}
            onChange={e => setDeveloperMode(e.target.checked)}
            className="w-3 h-3 rounded" />
          <Code size={12} />
        </label>

        <button onClick={() => setDark(!dark)}
          className="p-1.5 rounded hover:bg-[var(--bg-hover)]"
          style={{ color: 'var(--text-muted)' }}
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}>
          {dark ? <Sun size={15} /> : <Moon size={15} />}
        </button>

        <button onClick={() => setInspectorOpen(!inspectorOpen)}
          className="lg:hidden p-1 rounded hover:bg-[var(--bg-hover)]"
          style={{ color: 'var(--text-muted)' }}
          title="Toggle inspector">
          <PanelRightClose size={15} />
        </button>
      </div>
    </header>
  )
}
