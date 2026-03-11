import { useEffect, useRef, useState } from 'react'
import { X, RefreshCw, MessageSquare } from 'lucide-react'

const NODE_COLOR = {
  main: '#22d3ee',
  Explore: '#4ade80',
  'general-purpose': '#a78bfa',
  Plan: '#fb923c',
  'code-review': '#f472b6',
  'deep-dive': '#38bdf8',
  'git-workflow': '#facc15',
  'test-reporter': '#34d399',
  'playwright-tester': '#c084fc',
}
const DEFAULT_COLOR = '#475569'

function getNodeColor(type) {
  return NODE_COLOR[type] || DEFAULT_COLOR
}

// Role badge styles
const ROLE_BADGE = {
  user: {
    bg: 'bg-amber-500/15',
    text: 'text-amber-400',
    border: 'border-amber-500/30',
    label: 'USER',
  },
  assistant: {
    bg: 'bg-cyan-500/15',
    text: 'text-cyan-400',
    border: 'border-cyan-500/30',
    label: 'AI',
  },
  system: {
    bg: 'bg-slate-500/15',
    text: 'text-slate-400',
    border: 'border-slate-500/30',
    label: 'SYS',
  },
}

const ROLE_CARD_ACCENT = {
  user: 'border-l-amber-500/50',
  assistant: 'border-l-cyan-500/50',
  system: 'border-l-slate-500/40',
}

function RoleBadge({ role }) {
  const style = ROLE_BADGE[role] ?? ROLE_BADGE.system
  return (
    <span
      className={`inline-flex items-center font-mono text-[9px] font-semibold tracking-widest px-1.5 py-0.5 rounded border ${style.bg} ${style.text} ${style.border} flex-shrink-0`}
    >
      {style.label}
    </span>
  )
}

function TurnCard({ turn, index }) {
  const accent = ROLE_CARD_ACCENT[turn.role] ?? ROLE_CARD_ACCENT.system
  const lines = turn.content.split('\n').filter(Boolean)

  return (
    <div
      data-testid="log-panel-turn-card"
      data-role={turn.role}
      className={`border-l-2 ${accent} border border-gray-800/60 rounded-r bg-gray-900/60 px-3 py-2.5 space-y-1.5`}
    >
      <div className="flex items-center gap-2">
        <RoleBadge role={turn.role} />
        {turn.timestamp && (
          <span className="font-mono text-[9px] text-gray-600 tabular-nums ml-auto">
            {(() => {
              try {
                return new Date(turn.timestamp).toLocaleTimeString('en-US', { hour12: false })
              } catch {
                return ''
              }
            })()}
          </span>
        )}
      </div>
      <div className="space-y-1">
        {lines.map((line, i) => (
          <p
            key={i}
            className="font-mono text-[11px] leading-relaxed text-gray-300 break-all whitespace-pre-wrap"
          >
            {line}
          </p>
        ))}
      </div>
    </div>
  )
}

function LogSidePanel({ taskId, node, onClose }) {
  const [turns, setTurns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const logRef = useRef(null)

  async function fetchLog() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/tasks/${taskId}/agent/${node.id}/log?limit=100`)
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setTurns(data.turns ?? [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLog()
  }, [taskId, node.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Scroll to bottom when turns load
  useEffect(() => {
    if (!loading && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [loading, turns.length])

  // Close on Escape
  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  const nodeColor = getNodeColor(node.type)

  return (
    <>
      {/* Backdrop */}
      <div
        className="absolute inset-0 z-10"
        onClick={onClose}
        data-testid="log-panel-backdrop"
      />

      {/* Panel */}
      <div
        data-testid="log-side-panel"
        className="absolute top-0 right-0 h-full w-full md:w-[420px] bg-gray-950 border-l border-gray-800 z-20 flex flex-col shadow-2xl"
        style={{ animation: 'slideInRight 0.18s ease-out' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 flex-shrink-0">
          <div
            className="w-3 h-3 rounded-full flex-shrink-0"
            style={{ backgroundColor: nodeColor }}
          />
          <div className="flex-1 min-w-0">
            <p
              data-testid="log-panel-agent-name"
              className="font-mono text-sm text-gray-200 truncate"
            >
              {node.label}
            </p>
            <p className="font-mono text-xs text-gray-500">{node.type}</p>
          </div>
          <button
            onClick={fetchLog}
            title="Refresh"
            className="p-1.5 rounded text-gray-500 hover:text-cyan-400 transition-colors flex-shrink-0"
            data-testid="log-panel-refresh"
          >
            <RefreshCw size={13} />
          </button>
          <button
            onClick={onClose}
            data-testid="log-panel-close"
            className="p-1.5 rounded text-gray-500 hover:text-gray-200 transition-colors flex-shrink-0"
            aria-label="Close log panel"
          >
            <X size={16} />
          </button>
        </div>

        {/* Log title */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-800/50 flex-shrink-0">
          <MessageSquare size={11} className="text-gray-600" />
          <span className="font-mono text-[10px] text-gray-600 uppercase tracking-widest">
            Conversation Turns
          </span>
          {!loading && !error && (
            <span className="ml-auto font-mono text-[10px] text-gray-700">
              {turns.length} turn{turns.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>

        {/* Content */}
        <div
          ref={logRef}
          className="flex-1 overflow-y-auto px-3 py-3 space-y-2"
          data-testid="log-panel-entries"
        >
          {loading ? (
            <p className="font-mono text-xs text-gray-500 italic p-2">
              Loading turns…
            </p>
          ) : error ? (
            <p className="font-mono text-xs text-red-400 p-2">
              {error}
            </p>
          ) : turns.length === 0 ? (
            <p className="font-mono text-xs text-gray-600 italic p-2">
              No conversation turns available
            </p>
          ) : (
            turns.map((turn, i) => (
              <TurnCard key={i} turn={turn} index={i} />
            ))
          )}
        </div>
      </div>

      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </>
  )
}

export default LogSidePanel
