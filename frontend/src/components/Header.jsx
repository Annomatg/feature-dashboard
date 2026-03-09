import { Settings, Sparkles, MessageSquare } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import DatabaseSelector from './DatabaseSelector'
import AutoPilotToggle from './AutoPilotToggle'
import ManualRunIndicator from './ManualRunIndicator'
import AiBudgetBadge from './AiBudgetBadge'
import PushNotifications from './PushNotifications'

function Header({ onSettingsClick, onPlanTasksClick }) {
  const location = useLocation()
  const isInterviewActive = location.pathname === '/interview'

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

          {/* Spacer */}
          <div className="flex-1" />

          {/* AI Budget badge — desktop only in title row */}
          <div className="hidden md:block">
            <AiBudgetBadge testId="ai-budget-badge-desktop" />
          </div>

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

          {/* Push notifications toggle */}
          <PushNotifications />

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

        {/* Row 2: AI Budget + DB selector — mobile only */}
        <div
          data-testid="header-mobile-row"
          className="flex md:hidden items-center gap-3 mt-2"
        >
          <AiBudgetBadge testId="ai-budget-badge-mobile" />

          {/* Database selector */}
          <div className="flex-shrink-0 ml-auto">
            <DatabaseSelector />
          </div>
        </div>

      </div>
    </header>
  )
}

export default Header
