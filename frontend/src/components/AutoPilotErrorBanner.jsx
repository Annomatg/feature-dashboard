import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle, X } from 'lucide-react'

async function fetchAutoPilotStatus() {
  const response = await fetch('/api/autopilot/status')
  if (!response.ok) throw new Error('Failed to fetch autopilot status')
  return response.json()
}

async function clearAutoPilotError() {
  const response = await fetch('/api/autopilot/clear-error', { method: 'POST' })
  if (!response.ok) throw new Error('Failed to clear error')
  return response.json()
}

function AutoPilotErrorBanner() {
  const queryClient = useQueryClient()

  const { data: status } = useQuery({
    queryKey: ['autopilot-status'],
    queryFn: fetchAutoPilotStatus,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.enabled) return 2000
      if (data?.last_error) return 5000
      return 10000
    },
  })

  const isBudgetExhausted = !status?.enabled && !!status?.budget_exhausted
  const hasError = !status?.enabled && !!status?.last_error

  // Only show when disabled AND there is an error or budget was exhausted
  if (!isBudgetExhausted && !hasError) return null

  async function handleDismiss() {
    await clearAutoPilotError()
    queryClient.invalidateQueries({ queryKey: ['autopilot-status'] })
  }

  if (isBudgetExhausted) {
    const n = status.features_completed ?? 0
    const msg = `Session budget reached \u2014 ${n} feature${n !== 1 ? 's' : ''} completed this session.`
    return (
      <div
        data-testid="autopilot-error-banner"
        data-variant="budget"
        className="flex-shrink-0 bg-success/10 border-b border-success/30 px-6 py-2"
      >
        <div className="max-w-[1800px] mx-auto flex items-center gap-3">
          <CheckCircle
            size={14}
            className="text-success flex-shrink-0"
            data-testid="autopilot-error-icon"
          />
          <span className="font-mono text-xs text-success uppercase tracking-wider flex-shrink-0 font-semibold">
            Session Complete
          </span>
          <span className="text-success/40 flex-shrink-0">·</span>
          <span
            data-testid="autopilot-error-message"
            className="font-mono text-xs text-success/80 truncate"
          >
            {msg}
          </span>
          <button
            data-testid="autopilot-error-dismiss"
            onClick={handleDismiss}
            aria-label="Dismiss"
            className="ml-auto flex-shrink-0 p-0.5 rounded text-success/60 hover:text-success hover:bg-success/10 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      data-testid="autopilot-error-banner"
      data-variant="error"
      className="flex-shrink-0 bg-error/10 border-b border-error/30 px-6 py-2"
    >
      <div className="max-w-[1800px] mx-auto flex items-center gap-3">
        {/* Warning icon */}
        <AlertTriangle
          size={14}
          className="text-error flex-shrink-0"
          data-testid="autopilot-error-icon"
        />

        {/* Label */}
        <span className="font-mono text-xs text-error uppercase tracking-wider flex-shrink-0 font-semibold">
          Auto-Pilot stopped
        </span>

        {/* Separator */}
        <span className="text-error/40 flex-shrink-0">·</span>

        {/* Error message */}
        <span
          data-testid="autopilot-error-message"
          className="font-mono text-xs text-error/80 truncate"
        >
          {status.last_error}
        </span>

        {/* Dismiss button */}
        <button
          data-testid="autopilot-error-dismiss"
          onClick={handleDismiss}
          aria-label="Dismiss error"
          className="ml-auto flex-shrink-0 p-0.5 rounded text-error/60 hover:text-error hover:bg-error/10 transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  )
}

export default AutoPilotErrorBanner
