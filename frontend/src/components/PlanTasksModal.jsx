import { useState, useEffect, useRef } from 'react'
import { X, Sparkles } from 'lucide-react'

async function postPlanTasks(description) {
  const response = await fetch('/api/plan-tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description })
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to launch planning session')
  }
  return response.json()
}

function PlanTasksModal({ onClose, onToast }) {
  const [description, setDescription] = useState('')
  const [isLaunching, setIsLaunching] = useState(false)
  const textareaRef = useRef(null)

  // Auto-focus textarea when modal opens
  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const canSubmit = description.trim().length > 0 && !isLaunching

  const handleSubmit = async () => {
    if (!canSubmit) return
    setIsLaunching(true)
    try {
      await postPlanTasks(description.trim())
      onToast('success', 'Planning session launched')
      onClose()
    } catch (err) {
      onToast('error', err.message || 'Failed to launch planning session')
    } finally {
      setIsLaunching(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      handleSubmit()
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 flex items-center justify-center"
        onClick={onClose}
        data-testid="plan-tasks-backdrop"
      >
        {/* Modal panel — stop clicks from bubbling to backdrop */}
        <div
          className="relative bg-surface border border-border rounded-lg shadow-2xl w-full max-w-lg mx-4 animate-slide-in"
          onClick={(e) => e.stopPropagation()}
          data-testid="plan-tasks-modal"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-primary" />
              <h2 className="text-sm font-mono font-semibold text-text-primary uppercase tracking-wider">
                Plan Tasks
              </h2>
            </div>
            <button
              onClick={onClose}
              data-testid="plan-tasks-close"
              className="p-1.5 rounded hover:bg-surface-light transition-colors"
              aria-label="Close modal"
            >
              <X size={18} className="text-text-secondary hover:text-text-primary transition-colors" />
            </button>
          </div>

          {/* Body */}
          <div className="px-5 py-4">
            <label className="block text-xs font-mono text-text-secondary mb-2 uppercase tracking-wide">
              Planning Description
            </label>
            <p className="text-xs text-text-secondary mb-3 leading-relaxed">
              Describe what you want to plan. Claude will create features in the backlog based on your description.
            </p>
            <textarea
              ref={textareaRef}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onKeyDown={handleKeyDown}
              data-testid="plan-tasks-description"
              placeholder="e.g. Add user authentication with JWT tokens, including login, logout, and session management..."
              className="w-full bg-background border border-border rounded px-3 py-2.5 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-primary transition-colors resize-none custom-scrollbar"
              rows={6}
              spellCheck={false}
            />
            <p className="text-xs text-text-secondary mt-1">
              Ctrl+Enter to submit
            </p>
          </div>

          {/* Footer */}
          <div className="px-5 py-4 border-t border-border flex gap-2 justify-end">
            <button
              onClick={onClose}
              disabled={isLaunching}
              className="px-4 py-2 rounded font-mono text-sm font-semibold bg-background border border-border text-text-secondary hover:bg-surface-light hover:text-text-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              data-testid="plan-tasks-submit"
              className="px-4 py-2 rounded font-mono text-sm font-semibold border border-primary text-primary hover:bg-primary hover:text-black transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <Sparkles size={14} />
              {isLaunching ? 'Launching...' : 'Launch Planning Session'}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

export default PlanTasksModal
