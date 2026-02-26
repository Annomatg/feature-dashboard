import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot } from 'lucide-react'
import { useToast } from './Toast'

async function fetchAutoPilotStatus() {
  const response = await fetch('/api/autopilot/status')
  if (!response.ok) throw new Error('Failed to fetch autopilot status')
  return response.json()
}

async function enableAutoPilot() {
  const response = await fetch('/api/autopilot/enable', { method: 'POST' })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to enable auto-pilot')
  }
  return response.json()
}

async function disableAutoPilot() {
  const response = await fetch('/api/autopilot/disable', { method: 'POST' })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to disable auto-pilot')
  }
  return response.json()
}

function AutoPilotToggle() {
  const [loading, setLoading] = useState(false)
  const toast = useToast()
  const queryClient = useQueryClient()

  const { data: status } = useQuery({
    queryKey: ['autopilot-status'],
    queryFn: fetchAutoPilotStatus,
    // Poll frequently while running or while waiting for the process to exit.
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.enabled || data?.stopping) return 2000
      return 10000
    },
  })

  const enabled = status?.enabled ?? false
  const stopping = status?.stopping ?? false

  async function handleClick() {
    if (loading) return
    setLoading(true)
    try {
      if (enabled) {
        // Running → stop
        await disableAutoPilot()
      } else {
        // Disabled or stopping → (re-)enable.
        // When stopping=true the backend cancels the old monitoring task,
        // terminates the orphaned process, and starts a fresh run.
        await enableAutoPilot()
      }
      queryClient.invalidateQueries(['autopilot-status'])
    } catch (err) {
      toast.error(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      data-testid="autopilot-toggle"
      aria-label={
        enabled   ? 'Disable Auto-Pilot'
        : stopping ? 'Re-enable Auto-Pilot'
        :            'Enable Auto-Pilot'
      }
      title={
        enabled   ? 'Auto-Pilot ON — click to disable'
        : stopping ? 'Claude process still finishing — click to restart Auto-Pilot'
        :            'Enable Auto-Pilot'
      }
      className={`
        flex-shrink-0 flex items-center gap-2 px-2 md:px-2.5 py-1.5 rounded transition-colors font-mono text-xs
        disabled:opacity-60 disabled:cursor-not-allowed
        ${enabled
          ? 'bg-success/15 border border-success/40 text-success hover:bg-success/25'
          : stopping
            ? 'bg-amber-500/10 border border-amber-500/40 text-amber-400 hover:bg-amber-500/20'
            : 'text-text-secondary hover:bg-surface-light hover:text-text-primary'
        }
      `}
    >
      {enabled ? (
        <>
          <span
            data-testid="autopilot-pulse-dot"
            className="w-2 h-2 rounded-full bg-success animate-pulse flex-shrink-0"
          />
          <span className="hidden md:inline">Auto-Pilot ON</span>
        </>
      ) : stopping ? (
        <>
          <span
            data-testid="autopilot-stopping-dot"
            className="w-2 h-2 rounded-full bg-amber-400 animate-pulse flex-shrink-0"
          />
          <span className="hidden md:inline">Stopping\u2026</span>
        </>
      ) : (
        <>
          <Bot size={16} className="flex-shrink-0" />
          <span className="hidden md:inline">Auto-Pilot</span>
        </>
      )}
    </button>
  )
}

export default AutoPilotToggle
