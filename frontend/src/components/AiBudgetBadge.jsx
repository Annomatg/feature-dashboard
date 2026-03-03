import { useQuery } from '@tanstack/react-query'
import { Activity } from 'lucide-react'

async function fetchBudget() {
  const resp = await fetch('/api/budget')
  if (!resp.ok) throw new Error('Failed to fetch budget')
  return resp.json()
}

/** Return a hex color string based on utilization percentage. */
function utilColor(pct) {
  if (pct >= 95) return '#ef4444'   // red-500
  if (pct >= 75) return '#f59e0b'   // amber-500
  return '#22c55e'                   // green-500
}

/** Render one usage period (5h or 7d). Shows 0% when data is absent (no usage yet). */
function PeriodLabel({ label, data }) {
  const pct = data ? Math.round(data.utilization) : 0
  const exhausted = pct >= 100
  return (
    <span className="flex items-center gap-0.5">
      <span className="text-text-secondary">{label}:</span>
      {exhausted ? (
        <span style={{ color: '#ef4444' }}>resets&nbsp;{data.resets_formatted}</span>
      ) : (
        <span className="font-semibold tabular-nums" style={{ color: utilColor(pct) }}>{pct}%</span>
      )}
    </span>
  )
}

/**
 * AiBudgetBadge — shows Anthropic 5-hour and weekly usage in the header.
 *
 * Displays "5h: XX%  week: XX%" labels on all screen sizes.
 *
 * Renders nothing when credentials are unavailable or the API call fails.
 *
 * @param {string} [testId="ai-budget-badge"] - data-testid for the root element.
 *   Pass a unique value when rendering multiple instances to avoid strict-mode
 *   violations in Playwright tests.
 */
function AiBudgetBadge({ testId = 'ai-budget-badge' }) {
  const { data } = useQuery({
    queryKey: ['ai-budget'],
    queryFn: fetchBudget,
    refetchInterval: 60_000,
    retry: false,
    // Don't throw on error — we want silent degradation
    throwOnError: false,
  })

  // Degrade silently only when no data at all or API returns an error (e.g. missing credentials)
  if (!data || data.error) return null

  // Worst utilization across periods (for title tooltip color)
  const maxPct = Math.max(
    data.five_hour ? Math.round(data.five_hour.utilization) : 0,
    data.seven_day ? Math.round(data.seven_day.utilization) : 0,
  )

  return (
    <div
      data-testid={testId}
      className="flex-shrink-0 flex items-center gap-1.5 px-2 py-1 rounded border border-border font-mono text-xs"
      title={`AI Usage — 5h: ${data.five_hour ? Math.round(data.five_hour.utilization) + '%' : '0%'} | week: ${data.seven_day ? Math.round(data.seven_day.utilization) + '%' : '0%'}`}
    >
      <Activity size={14} className="flex-shrink-0 text-text-secondary" />

      <span className="flex items-center gap-2">
        <PeriodLabel label="5h"   data={data.five_hour} />
        <PeriodLabel label="week" data={data.seven_day} />
      </span>
    </div>
  )
}

export default AiBudgetBadge
