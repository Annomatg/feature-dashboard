import { useQuery } from '@tanstack/react-query'
import { Terminal } from 'lucide-react'

async function fetchAutoPilotStatus() {
  const response = await fetch('/api/autopilot/status')
  if (!response.ok) throw new Error('Failed to fetch autopilot status')
  return response.json()
}

function ManualRunIndicator() {
  const { data: status } = useQuery({
    queryKey: ['autopilot-status'],
    queryFn: fetchAutoPilotStatus,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.manual_active || data?.enabled || data?.stopping) return 2000
      return 10000
    },
  })

  if (!status?.manual_active) return null

  const featureId = status.manual_feature_id
  const featureName = status.manual_feature_name
  const model = status.manual_feature_model ?? 'sonnet'

  return (
    <div
      data-testid="manual-run-indicator"
      className="flex-shrink-0 flex items-center gap-2 px-2 md:px-2.5 py-1.5 rounded font-mono text-xs bg-primary/10 border border-primary/30 text-primary"
      title={featureName ? `Manual run: #${featureId} ${featureName} (${model})` : 'Manual Claude run in progress'}
    >
      <span
        data-testid="manual-run-pulse-dot"
        className="w-2 h-2 rounded-full bg-primary animate-pulse flex-shrink-0"
      />
      <Terminal size={13} className="flex-shrink-0 hidden md:block" />
      <span className="hidden md:inline">Claude Running</span>
    </div>
  )
}

export default ManualRunIndicator
