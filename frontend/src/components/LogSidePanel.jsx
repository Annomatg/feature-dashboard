import { useEffect, useRef, useState } from 'react'
import { X, Terminal, RefreshCw } from 'lucide-react'

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

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString('en-US', { hour12: false })
  } catch {
    return iso
  }
}

function LogSidePanel({ taskId, node, onClose }) {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const logRef = useRef(null)

  async function fetchLog() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/tasks/${taskId}/node-log/${node.id}?limit=100`)
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setEntries(data.entries ?? [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLog()
  }, [taskId, node.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Scroll to bottom when entries load
  useEffect(() => {
    if (!loading && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [loading, entries.length])

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
        className="absolute top-0 right-0 h-full w-full md:w-[400px] bg-gray-900 border-l border-gray-800 z-20 flex flex-col shadow-2xl"
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
          <Terminal size={11} className="text-gray-600" />
          <span className="font-mono text-[10px] text-gray-600 uppercase tracking-widest">
            Session Log
          </span>
        </div>

        {/* Content */}
        <div
          ref={logRef}
          className="flex-1 overflow-y-auto px-3 py-2"
          data-testid="log-panel-entries"
        >
          {loading ? (
            <p className="font-mono text-xs text-gray-500 italic p-2">
              Loading log…
            </p>
          ) : error ? (
            <p className="font-mono text-xs text-red-400 p-2">
              {error}
            </p>
          ) : entries.length === 0 ? (
            <p className="font-mono text-xs text-gray-600 italic p-2">
              No log entries available
            </p>
          ) : (
            <div className="space-y-0.5">
              {entries.map((entry, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 py-0.5 min-w-0"
                  data-testid="log-panel-entry"
                >
                  <span className="font-mono text-[10px] text-gray-600 flex-shrink-0 pt-0.5 w-14 text-right tabular-nums">
                    {formatTime(entry.timestamp)}
                  </span>
                  <span
                    className={`font-mono text-[10px] px-1 rounded flex-shrink-0 mt-0.5 ${
                      entry.entry_type === 'tool_use'
                        ? 'bg-blue-500/20 text-blue-400'
                        : entry.entry_type === 'thinking'
                        ? 'bg-purple-500/20 text-purple-400'
                        : 'bg-emerald-500/20 text-emerald-400'
                    }`}
                  >
                    {entry.entry_type === 'tool_use'
                      ? (entry.tool_name?.split('__').pop() ?? 'tool')
                      : entry.entry_type === 'thinking'
                      ? 'think'
                      : 'text'}
                  </span>
                  <span className="font-mono text-[11px] text-gray-300 break-all min-w-0 leading-relaxed">
                    {entry.text}
                  </span>
                </div>
              ))}
            </div>
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
