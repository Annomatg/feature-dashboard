import DatabaseSelector from './DatabaseSelector'

function StatPill({ label, value, color }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="w-2 h-2 rounded-full flex-shrink-0"
        style={{ backgroundColor: color }}
      />
      <span className="text-text-secondary font-mono text-xs uppercase tracking-wider">{label}</span>
      <span className="text-text-primary font-mono text-sm font-semibold tabular-nums">{value}</span>
    </div>
  )
}

function Header({ totalFeatures, inProgressCount, doneCount }) {
  const donePercentage = totalFeatures > 0
    ? Math.round((doneCount / totalFeatures) * 100)
    : 0

  return (
    <header className="flex-shrink-0 bg-background border-b border-border px-6 py-4">
      <div className="max-w-[1800px] mx-auto flex items-center gap-6">
        {/* Title with accent bar */}
        <div className="flex items-center gap-3">
          <div className="w-1 h-8 bg-primary rounded-full" />
          <h1 className="text-xl font-bold font-mono text-text-primary tracking-tight">
            FEATURE DASHBOARD
          </h1>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-5 ml-4 pl-4 border-l border-border">
          <StatPill
            label="Total"
            value={totalFeatures}
            color="#6b7280"
          />
          <StatPill
            label="In Progress"
            value={inProgressCount}
            color="#3b82f6"
          />
          <StatPill
            label="Done"
            value={`${doneCount} (${donePercentage}%)`}
            color="#22c55e"
          />
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Database selector */}
        <DatabaseSelector />
      </div>
    </header>
  )
}

export default Header
