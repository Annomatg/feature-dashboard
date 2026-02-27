import { useRef, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronUp, ChevronDown, RefreshCw } from 'lucide-react'

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------

async function fetchInterviewDebug() {
  const res = await fetch('/api/interview/debug')
  if (res.status === 404) return null   // no active/recent session — not an error
  if (!res.ok) throw new Error(`Debug fetch failed: ${res.status}`)
  return res.json()
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatTimestamp(iso) {
  try {
    return new Date(iso).toLocaleTimeString('en-GB', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    })
  } catch {
    return iso
  }
}

function formatDetail(detail) {
  if (!detail || Object.keys(detail).length === 0) return ''
  if (typeof detail.text === 'string') {
    return detail.text.length > 50 ? detail.text.slice(0, 50) + '…' : detail.text
  }
  if (typeof detail.value === 'string') return detail.value
  if (typeof detail.started_at === 'string') return detail.started_at
  if ('features_created' in detail) return `features: ${detail.features_created}`
  return JSON.stringify(detail)
}

// ---------------------------------------------------------------------------
// Event-type badge colours
// ---------------------------------------------------------------------------

const EVENT_TYPE_CLASSES = {
  session_start:    'text-primary bg-primary/15 border border-primary/30',
  question_posted:  'text-primary bg-primary/15 border border-primary/30',
  answer_submitted: 'text-success bg-success/15 border border-success/30',
  sse_connect:      'text-success bg-success/15 border border-success/30',
  sse_disconnect:   'text-warning bg-warning/15 border border-warning/30',
  answer_timeout:   'text-error bg-red-500/15 border border-red-500/30',
  error:            'text-error bg-red-500/15 border border-red-500/30',
  session_end:      'text-text-secondary bg-surface-light border border-border',
}

function eventTypeClass(type) {
  return EVENT_TYPE_CLASSES[type] ?? 'text-text-secondary bg-surface-light border border-border'
}

// ---------------------------------------------------------------------------
// Connection status indicator
// ---------------------------------------------------------------------------

function ConnectionStatus({ data, isError }) {
  let dot = 'bg-surface-light'
  let label = 'No session'

  if (isError) {
    dot = 'bg-error'
    label = 'Error'
  } else if (data?.active === true) {
    dot = 'bg-success'
    label = 'Active'
  } else if (data?.active === false) {
    dot = 'bg-warning'
    label = 'Ended'
  }

  return (
    <span
      data-testid="interview-debug-status"
      className="flex items-center gap-1 font-mono text-[10px] text-text-secondary"
    >
      <span
        data-testid="interview-debug-status-dot"
        className={`w-1.5 h-1.5 rounded-full ${dot} flex-shrink-0`}
      />
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function InterviewDebugPanel() {
  const [open, setOpen] = useState(false)
  const bottomRef = useRef(null)

  const { data, isError, refetch } = useQuery({
    queryKey: ['interview-debug'],
    queryFn: fetchInterviewDebug,
    refetchInterval: 2000,
    retry: false,
  })

  const entries = data?.log ?? []

  // Auto-scroll to bottom when new entries arrive while panel is open
  useEffect(() => {
    if (open && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [entries.length, open])

  return (
    <div
      data-testid="interview-debug-panel"
      className="flex-shrink-0 bg-surface border-t border-border"
    >
      {/* Header row */}
      <div className="flex items-center px-4 py-2 gap-3">
        <button
          data-testid="interview-debug-toggle"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 text-text-secondary hover:text-text-primary transition-colors"
          aria-expanded={open}
          aria-controls="interview-debug-entries"
        >
          {open
            ? <ChevronDown size={14} className="flex-shrink-0" />
            : <ChevronUp size={14} className="flex-shrink-0" />
          }
          <span className="font-mono text-xs uppercase tracking-wider">Debug</span>
          {entries.length > 0 && (
            <span
              data-testid="interview-debug-count"
              className="font-mono text-xs text-text-secondary"
            >
              ({entries.length})
            </span>
          )}
        </button>

        <ConnectionStatus data={data} isError={isError} />

        <button
          data-testid="interview-debug-refresh"
          onClick={() => refetch()}
          className="ml-auto flex items-center gap-1.5 font-mono text-xs text-text-secondary hover:text-text-primary transition-colors"
          title="Refresh debug log"
        >
          <RefreshCw size={12} />
          <span className="hidden md:inline">Refresh</span>
        </button>
      </div>

      {/* Log entries */}
      {open && (
        <div
          id="interview-debug-entries"
          data-testid="interview-debug-entries"
          className="max-h-[150px] md:max-h-48 overflow-y-auto px-4 pb-3 space-y-1"
        >
          {entries.length === 0 ? (
            <p
              data-testid="interview-debug-empty"
              className="font-mono text-xs text-text-secondary italic py-2"
            >
              No log entries yet
            </p>
          ) : (
            entries.map((entry, idx) => (
              <div
                key={idx}
                data-testid="interview-debug-entry"
                className="flex items-center gap-2 font-mono text-xs"
              >
                <span className="text-text-secondary flex-shrink-0 w-16 text-right tabular-nums">
                  {formatTimestamp(entry.timestamp)}
                </span>
                <span
                  data-testid={`interview-debug-badge-${entry.event_type}`}
                  className={`flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide whitespace-nowrap ${eventTypeClass(entry.event_type)}`}
                >
                  {entry.event_type}
                </span>
                <span className="text-text-primary truncate">
                  {formatDetail(entry.detail)}
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

export default InterviewDebugPanel
