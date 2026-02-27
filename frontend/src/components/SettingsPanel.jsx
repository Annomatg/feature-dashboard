import { useState, useEffect, useRef } from 'react'
import { X, RotateCcw, Save } from 'lucide-react'

const DEFAULT_PROMPT_TEMPLATE =
  'Please work on the following feature:\n\nFeature #{feature_id} [{category}]: {name}\n\nDescription:\n{description}\n\nSteps:\n{steps}'

const DEFAULT_PLAN_TASKS_TEMPLATE =
  'You are a Project Expansion Assistant for the Feature Dashboard project.\n\n## Project Context\n\nFeature Dashboard is a web application for visualizing and managing project features stored in a SQLite database. It uses React 18 + Vite on the frontend and FastAPI + SQLite on the backend. Features are tracked in a kanban board with TODO, In Progress, and Done lanes.\n\n**Available MCP tools:** feature_create_bulk, feature_create, feature_get_stats, feature_get_next, feature_mark_passing, feature_skip\n\n## User Request\n\nThe user wants to expand the project with the following:\n\n{description}\n\n## Your Role\n\nFollow the expand-project process:\n\n**Phase 1: Clarify Requirements**\nAsk focused questions to fully understand what the user wants:\n- What the user sees (UI/UX flows)\n- What actions they can take\n- What happens as a result\n- Error states and edge cases\n\n**Phase 2: Present Feature Breakdown**\nCount testable behaviors and present a breakdown by category for approval before creating anything:\n- `functional` - Core functionality, CRUD operations, workflows\n- `style` - Visual design, layout, responsive behavior\n- `navigation` - Routing, links, breadcrumbs\n- `error-handling` - Error states, validation, edge cases\n- `data` - Data integrity, persistence\n\n**Phase 3: Create Features**\nOnce the user approves the breakdown, call `feature_create_bulk` with ALL features at once.\n\nStart by greeting the user, summarizing what they want to add, and asking clarifying questions.'

async function fetchSettings() {
  const response = await fetch('/api/settings')
  if (!response.ok) throw new Error('Failed to load settings')
  return response.json()
}

async function saveSettings(settings) {
  const response = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to save settings')
  }
  return response.json()
}

function SettingsPanel({ onClose }) {
  const [promptTemplate, setPromptTemplate] = useState('')
  const [savedTemplate, setSavedTemplate] = useState('')
  const [planTemplate, setPlanTemplate] = useState('')
  const [savedPlanTemplate, setSavedPlanTemplate] = useState('')
  const [budgetLimit, setBudgetLimit] = useState(0)
  const [savedBudgetLimit, setSavedBudgetLimit] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState(null)
  const panelRef = useRef(null)

  // Load settings on mount
  useEffect(() => {
    fetchSettings()
      .then(data => {
        setPromptTemplate(data.claude_prompt_template)
        setSavedTemplate(data.claude_prompt_template)
        setPlanTemplate(data.plan_tasks_prompt_template ?? DEFAULT_PLAN_TASKS_TEMPLATE)
        setSavedPlanTemplate(data.plan_tasks_prompt_template ?? DEFAULT_PLAN_TASKS_TEMPLATE)
        const limit = data.autopilot_budget_limit ?? 0
        setBudgetLimit(limit)
        setSavedBudgetLimit(limit)
      })
      .catch(() => {
        setPromptTemplate(DEFAULT_PROMPT_TEMPLATE)
        setSavedTemplate(DEFAULT_PROMPT_TEMPLATE)
        setPlanTemplate(DEFAULT_PLAN_TASKS_TEMPLATE)
        setSavedPlanTemplate(DEFAULT_PLAN_TASKS_TEMPLATE)
        setBudgetLimit(0)
        setSavedBudgetLimit(0)
      })
      .finally(() => setIsLoading(false))
  }, [])

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const isDirty = promptTemplate !== savedTemplate || planTemplate !== savedPlanTemplate || budgetLimit !== savedBudgetLimit

  const handleSave = async () => {
    setIsSaving(true)
    setSaveMessage(null)
    try {
      await saveSettings({
        claude_prompt_template: promptTemplate,
        plan_tasks_prompt_template: planTemplate,
        autopilot_budget_limit: budgetLimit,
      })
      setSavedTemplate(promptTemplate)
      setSavedPlanTemplate(planTemplate)
      setSavedBudgetLimit(budgetLimit)
      setSaveMessage({ type: 'success', text: 'Settings saved!' })
    } catch (err) {
      setSaveMessage({ type: 'error', text: err.message || 'Failed to save' })
    } finally {
      setIsSaving(false)
      setTimeout(() => setSaveMessage(null), 3000)
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
        data-testid="settings-panel-backdrop"
      />

      {/* Panel */}
      <div
        ref={panelRef}
        data-testid="settings-panel"
        className="fixed top-0 right-0 h-dvh w-full md:w-[480px] bg-surface border-l border-border z-50 flex flex-col shadow-2xl animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-mono font-semibold text-text-primary uppercase tracking-wider">
              Settings
            </h2>
            {isSaving && (
              <span className="text-xs font-mono text-text-secondary animate-pulse">
                saving...
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            data-testid="settings-panel-close"
            className="p-1.5 rounded hover:bg-surface-light transition-colors"
            aria-label="Close settings"
          >
            <X size={18} className="text-text-secondary hover:text-text-primary transition-colors" />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-6 custom-scrollbar">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <>
              {/* Session Budget */}
              <div>
                <label className="block text-xs font-mono text-text-secondary uppercase tracking-wide mb-2">
                  Session Budget (max features)
                </label>
                <p className="text-xs text-text-secondary mb-3 leading-relaxed">
                  Stop autopilot after completing this many features in one session. Set to{' '}
                  <code className="font-mono text-primary">0</code> for unlimited.
                </p>
                <input
                  type="number"
                  data-testid="budget-limit-input"
                  value={budgetLimit}
                  min={0}
                  onChange={(e) => setBudgetLimit(Math.max(0, parseInt(e.target.value, 10) || 0))}
                  className="w-32 bg-background border border-border rounded px-3 py-2 text-sm text-text-primary font-mono focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              {/* Autopilot prompt template */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs font-mono text-text-secondary uppercase tracking-wide">
                    Claude Prompt Template
                  </label>
                  <button
                    onClick={() => setPromptTemplate(DEFAULT_PROMPT_TEMPLATE)}
                    data-testid="settings-reset-btn"
                    title="Reset to default"
                    className="p-1 rounded text-text-secondary hover:text-text-primary hover:bg-surface-light transition-colors"
                  >
                    <RotateCcw size={12} />
                  </button>
                </div>
                <p className="text-xs text-text-secondary mb-3 leading-relaxed">
                  Template used when launching Claude for a feature.
                  Available variables: <code className="font-mono text-primary">{'{feature_id}'}</code>,{' '}
                  <code className="font-mono text-primary">{'{category}'}</code>,{' '}
                  <code className="font-mono text-primary">{'{name}'}</code>,{' '}
                  <code className="font-mono text-primary">{'{description}'}</code>,{' '}
                  <code className="font-mono text-primary">{'{steps}'}</code>
                </p>
                <textarea
                  data-testid="prompt-template-input"
                  value={promptTemplate}
                  onChange={(e) => setPromptTemplate(e.target.value)}
                  className="w-full bg-background border border-border rounded px-3 py-2.5 text-sm text-text-primary font-mono focus:outline-none focus:border-primary transition-colors resize-none custom-scrollbar"
                  rows={10}
                  placeholder="Enter prompt template..."
                  spellCheck={false}
                />
              </div>

              {/* Plan tasks prompt template */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs font-mono text-text-secondary uppercase tracking-wide">
                    Plan Tasks Prompt Template
                  </label>
                  <button
                    onClick={() => setPlanTemplate(DEFAULT_PLAN_TASKS_TEMPLATE)}
                    data-testid="plan-prompt-reset-btn"
                    title="Reset to default"
                    className="p-1 rounded text-text-secondary hover:text-text-primary hover:bg-surface-light transition-colors"
                  >
                    <RotateCcw size={12} />
                  </button>
                </div>
                <p className="text-xs text-text-secondary mb-3 leading-relaxed">
                  Template used when launching an interactive planning session.
                  Available variable: <code className="font-mono text-primary">{'{description}'}</code>
                </p>
                <textarea
                  data-testid="plan-prompt-template-input"
                  value={planTemplate}
                  onChange={(e) => setPlanTemplate(e.target.value)}
                  className="w-full bg-background border border-border rounded px-3 py-2.5 text-sm text-text-primary font-mono focus:outline-none focus:border-primary transition-colors resize-none custom-scrollbar"
                  rows={14}
                  placeholder="Enter plan tasks prompt template..."
                  spellCheck={false}
                />
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-border flex-shrink-0 space-y-2">
          {saveMessage && (
            <p
              data-testid="settings-save-message"
              className={`text-xs font-mono text-center ${saveMessage.type === 'success' ? 'text-green-400' : 'text-error'}`}
            >
              {saveMessage.text}
            </p>
          )}
          <button
            onClick={handleSave}
            disabled={isSaving || !isDirty}
            data-testid="settings-save-btn"
            className="w-full py-2 rounded font-mono text-sm font-semibold border border-primary text-primary hover:bg-primary hover:text-black transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Save size={14} />
            {isSaving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </>
  )
}

export default SettingsPanel
