import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'

async function fetchAutoPilotStatus() {
  const response = await fetch('/api/autopilot/status')
  if (!response.ok) throw new Error('Failed to fetch autopilot status')
  return response.json()
}

const MODEL_COLORS = {
  opus:   'bg-purple-500/20 text-purple-300 border-purple-500/30',
  sonnet: 'bg-primary/20 text-primary border-primary/30',
  haiku:  'bg-success/20 text-success border-success/30',
}

function modelBadgeClass(model) {
  if (!model) return MODEL_COLORS.sonnet
  const key = model.toLowerCase()
  if (key.includes('opus')) return MODEL_COLORS.opus
  if (key.includes('haiku')) return MODEL_COLORS.haiku
  return MODEL_COLORS.sonnet
}

function modelLabel(model) {
  if (!model) return 'sonnet'
  if (model.toLowerCase().includes('opus')) return 'opus'
  if (model.toLowerCase().includes('haiku')) return 'haiku'
  return 'sonnet'
}

function AutoPilotStatusBar() {
  const { data: status } = useQuery({
    queryKey: ['autopilot-status'],
    queryFn: fetchAutoPilotStatus,
    refetchInterval: (query) => {
      const data = query.state.data
      // Poll frequently while running, stopping, or a manual launch is active.
      if (data?.enabled || data?.stopping || data?.manual_active) return 2000
      return 10000
    },
  })

  // Hide the bar when nothing is running.
  if (!status?.enabled && !status?.stopping && !status?.manual_active) return null

  const isStopping = !status.enabled && !!status.stopping
  const isManual = !status.enabled && !status.stopping && !!status.manual_active
  const featureId = isManual ? status.manual_feature_id : status.current_feature_id
  const featureName = isManual ? status.manual_feature_name : status.current_feature_name
  const model = isManual ? status.manual_feature_model : status.current_feature_model

  return (
    <div
      data-testid="autopilot-status-bar"
      className="flex-shrink-0 bg-surface border-b border-border px-6 py-2"
    >
      <div className="max-w-[1800px] mx-auto flex items-center gap-3">
        {/* Spinning loader — amber when stopping, blue when running */}
        <Loader2
          size={14}
          className={`${isStopping ? 'text-amber-400' : 'text-primary'} animate-spin flex-shrink-0`}
          data-testid="autopilot-status-spinner"
        />

        {/* Label */}
        <span
          className={`font-mono text-xs uppercase tracking-wider flex-shrink-0 ${
            isStopping ? 'text-amber-400' : 'text-text-secondary'
          }`}
          data-testid="autopilot-status-label"
        >
          {isStopping ? 'Stopping\u2026' : isManual ? 'Manual Run' : 'Auto-Pilot'}
        </span>

        {/* Separator */}
        <span className="text-border flex-shrink-0">·</span>

        {/* Feature ID + name */}
        {featureId != null ? (
          <span
            data-testid="autopilot-status-feature"
            className="font-mono text-xs text-text-primary truncate"
          >
            <span className="text-text-secondary">#{featureId}</span>
            {featureName && (
              <span className={`${isStopping ? 'text-amber-400/80' : 'text-primary'} ml-2`}>
                {featureName}
              </span>
            )}
          </span>
        ) : (
          <span className="font-mono text-xs text-text-secondary italic">
            Initializing…
          </span>
        )}

        {/* Model badge */}
        {model && (
          <span
            data-testid="autopilot-status-model"
            className={`
              ml-auto flex-shrink-0 font-mono text-xs px-2 py-0.5 rounded border
              ${isStopping
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                : modelBadgeClass(model)
              }
            `}
          >
            {modelLabel(model)}
          </span>
        )}
      </div>
    </div>
  )
}

export default AutoPilotStatusBar
