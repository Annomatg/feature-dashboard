import { useRef, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronUp, ChevronDown, Trash2 } from 'lucide-react'

async function fetchAutoPilotStatus() {
  const response = await fetch('/api/autopilot/status')
  if (!response.ok) throw new Error('Failed to fetch autopilot status')
  return response.json()
}

async function clearAutoPilotLog() {
  const response = await fetch('/api/autopilot/log/clear', { method: 'POST' })
  if (!response.ok) throw new Error('Failed to clear log')
}

function formatTimestamp(iso) {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  } catch {
    return iso
  }
}

const LEVEL_CLASSES = {
  success: 'text-success bg-success/15 border border-success/30',
  error:   'text-red-400 bg-red-500/15 border border-red-500/30',
  info:    'text-text-secondary bg-surface-light border border-border',
}

function levelClass(level) {
  return LEVEL_CLASSES[level] ?? LEVEL_CLASSES.info
}

function AutoPilotLog() {
  const [open, setOpen] = useState(false)
  const bottomRef = useRef(null)
  const queryClient = useQueryClient()

  const { data: status } = useQuery({
    queryKey: ['autopilot-status'],
    queryFn: fetchAutoPilotStatus,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.enabled || data?.stopping || data?.manual_active) return 2000
      return 10000
    },
  })

  const entries = status?.log ?? []

  // Auto-scroll to bottom when new entries arrive while panel is open
  useEffect(() => {
    if (open && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [entries.length, open])

  async function handleClear() {
    await clearAutoPilotLog()
    queryClient.invalidateQueries(['autopilot-status'])
  }

  return (
    <div
      data-testid="autopilot-log-panel"
      className="flex-shrink-0 bg-surface border-t border-border"
    >
      {/* Header row */}
      <div className="flex items-center px-6 py-2 gap-3 max-w-[1800px] mx-auto">
        <button
          data-testid="autopilot-log-toggle"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 text-text-secondary hover:text-text-primary transition-colors"
          aria-expanded={open}
          aria-controls="autopilot-log-entries"
        >
          {open
            ? <ChevronDown size={14} className="flex-shrink-0" />
            : <ChevronUp size={14} className="flex-shrink-0" />
          }
          <span className="font-mono text-xs uppercase tracking-wider">
            Event Log
          </span>
          {entries.length > 0 && (
            <span
              data-testid="autopilot-log-count"
              className="font-mono text-xs text-text-secondary"
            >
              ({entries.length})
            </span>
          )}
        </button>

        {open && entries.length > 0 && (
          <button
            data-testid="autopilot-log-clear"
            onClick={handleClear}
            className="ml-auto flex items-center gap-1.5 font-mono text-xs text-text-secondary hover:text-red-400 transition-colors"
            title="Clear log"
          >
            <Trash2 size={12} />
            Clear
          </button>
        )}
      </div>

      {/* Log entries */}
      {open && (
        <div
          id="autopilot-log-entries"
          data-testid="autopilot-log-entries"
          className="max-h-48 overflow-y-auto px-6 pb-3 space-y-1 max-w-[1800px] mx-auto"
        >
          {entries.length === 0 ? (
            <p
              data-testid="autopilot-log-empty"
              className="font-mono text-xs text-text-secondary italic py-2"
            >
              No log entries yet
            </p>
          ) : (
            entries.map((entry, idx) => (
              <div
                key={idx}
                data-testid="autopilot-log-entry"
                className="flex items-center gap-2 font-mono text-xs"
              >
                <span className="text-text-secondary flex-shrink-0 w-16 text-right tabular-nums">
                  {formatTimestamp(entry.timestamp)}
                </span>
                <span
                  data-testid={`autopilot-log-badge-${entry.level}`}
                  className={`flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide ${levelClass(entry.level)}`}
                >
                  {entry.level}
                </span>
                <span className="text-text-primary truncate">
                  {entry.message}
                </span>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}

export default AutoPilotLog
