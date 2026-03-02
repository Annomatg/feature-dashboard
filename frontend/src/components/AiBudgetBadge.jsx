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

/** Render one usage period (5h or 7d). */
function PeriodLabel({ label, data }) {
  if (!data) return null
  const pct = Math.round(data.utilization)
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
 * Desktop: icon + "5h: XX%  week: XX%" labels.
 * Mobile:  icon + colored dot for worst-case utilization.
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

  // Degrade silently when no data, API error, or both periods absent
  if (!data || data.error || (!data.five_hour && !data.seven_day)) return null

  // Worst utilization across periods (for mobile dot color)
  const maxPct = Math.max(
    data.five_hour ? Math.round(data.five_hour.utilization) : 0,
    data.seven_day ? Math.round(data.seven_day.utilization) : 0,
  )

  return (
    <div
      data-testid={testId}
      className="flex-shrink-0 flex items-center gap-1.5 px-2 py-1 rounded border border-border font-mono text-xs"
      title={`AI Usage — 5h: ${data.five_hour ? Math.round(data.five_hour.utilization) + '%' : 'n/a'} | week: ${data.seven_day ? Math.round(data.seven_day.utilization) + '%' : 'n/a'}`}
    >
      <Activity size={14} className="flex-shrink-0 text-text-secondary" />

      {/* Mobile: single colored dot for worst utilization */}
      <span
        data-testid={`${testId}-dot`}
        className="md:hidden w-2 h-2 rounded-full flex-shrink-0"
        style={{ backgroundColor: utilColor(maxPct) }}
      />

      {/* Desktop: full period labels */}
      <span className="hidden md:flex items-center gap-2">
        <PeriodLabel label="5h"   data={data.five_hour} />
        <PeriodLabel label="week" data={data.seven_day} />
      </span>
    </div>
  )
}

export default AiBudgetBadge
