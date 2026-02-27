import { Settings, Sparkles, MessageSquare } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import DatabaseSelector from './DatabaseSelector'
import AutoPilotToggle from './AutoPilotToggle'
import ManualRunIndicator from './ManualRunIndicator'

function StatPill({ label, value, color }) {
  return (
    <div className="flex items-center gap-2 flex-shrink-0">
      <span
        className="w-2 h-2 rounded-full flex-shrink-0"
        style={{ backgroundColor: color }}
      />
      <span className="text-text-secondary font-mono text-xs uppercase tracking-wider">{label}</span>
      <span className="text-text-primary font-mono text-sm font-semibold tabular-nums">{value}</span>
    </div>
  )
}

function Header({ totalFeatures, inProgressCount, doneCount, onSettingsClick, onPlanTasksClick }) {
  const location = useLocation()
  const isInterviewActive = location.pathname === '/interview'

  const donePercentage = totalFeatures > 0
    ? Math.round((doneCount / totalFeatures) * 100)
    : 0

  return (
    <header className="flex-shrink-0 bg-background border-b border-border px-4 py-3 md:px-6 md:py-4">
      <div className="max-w-[1800px] mx-auto">

        {/* Row 1: title + controls (always visible) */}
        <div className="flex items-center gap-3 md:gap-6">

          {/* Title with accent bar */}
          <div className="flex items-center gap-3">
            <div className="w-1 h-8 bg-primary rounded-full" />
            <h1 className="text-xl font-bold font-mono text-text-primary tracking-tight">
              FEATURE DASHBOARD
            </h1>
          </div>

          {/* Stats — desktop only (shown inline with title row) */}
          <div
            data-testid="header-stats-desktop"
            className="hidden md:flex items-center gap-5 ml-4 pl-4 border-l border-border"
          >
            <StatPill label="Total"       value={totalFeatures}                  color="#6b7280" />
            <StatPill label="In Progress" value={inProgressCount}                color="#3b82f6" />
            <StatPill label="Done"        value={`${doneCount} (${donePercentage}%)`} color="#22c55e" />
          </div>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Database selector — desktop only (shown in title row) */}
          <div className="hidden md:block">
            <DatabaseSelector />
          </div>

          {/* Interview link */}
          <Link
            to="/interview"
            data-testid="interview-nav-link"
            className={`flex-shrink-0 p-1.5 md:p-2 rounded transition-colors ${
              isInterviewActive
                ? 'bg-primary/15 text-primary'
                : 'text-primary/70 hover:bg-primary/10 hover:text-primary'
            }`}
            aria-label="Interview mode"
            title="Interview"
          >
            <MessageSquare size={18} />
          </Link>

          {/* Manual run indicator (shown when user manually launched Claude) */}
          <ManualRunIndicator />

          {/* Auto-Pilot toggle */}
          <AutoPilotToggle />

          {/* Plan Tasks button */}
          <button
            onClick={onPlanTasksClick}
            data-testid="plan-tasks-btn"
            className="flex-shrink-0 p-2 rounded hover:bg-surface-light transition-colors"
            aria-label="Plan tasks with Claude"
            title="Plan Tasks"
          >
            <Sparkles size={18} className="text-text-secondary hover:text-text-primary transition-colors" />
          </button>

          {/* Settings button */}
          <button
            onClick={onSettingsClick}
            data-testid="settings-btn"
            className="flex-shrink-0 p-2 rounded hover:bg-surface-light transition-colors"
            aria-label="Open settings"
            title="Settings"
          >
            <Settings size={18} className="text-text-secondary hover:text-text-primary transition-colors" />
          </button>
        </div>

        {/* Row 2: stats + DB selector — mobile only */}
        <div
          data-testid="header-mobile-row"
          className="flex md:hidden items-center gap-3 mt-2"
        >
          {/* Stats pills — horizontally scrollable */}
          <div
            data-testid="header-stats-mobile"
            className="flex items-center gap-4 flex-1 min-w-0 overflow-x-auto"
          >
            <StatPill label="Total"       value={totalFeatures}                  color="#6b7280" />
            <StatPill label="In Progress" value={inProgressCount}                color="#3b82f6" />
            <StatPill label="Done"        value={`${doneCount} (${donePercentage}%)`} color="#22c55e" />
          </div>

          {/* Database selector */}
          <div className="flex-shrink-0">
            <DatabaseSelector />
          </div>
        </div>

      </div>
    </header>
  )
}

export default Header
