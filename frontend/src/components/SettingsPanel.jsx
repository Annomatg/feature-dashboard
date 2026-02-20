import { useState, useEffect, useRef } from 'react'
import { X, RotateCcw, Save } from 'lucide-react'

const DEFAULT_PROMPT_TEMPLATE =
  'Please work on the following feature:\n\nFeature #{feature_id} [{category}]: {name}\n\nDescription:\n{description}\n\nSteps:\n{steps}'

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
      })
      .catch(() => {
        setPromptTemplate(DEFAULT_PROMPT_TEMPLATE)
        setSavedTemplate(DEFAULT_PROMPT_TEMPLATE)
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

  const isDirty = promptTemplate !== savedTemplate

  const handleSave = async () => {
    setIsSaving(true)
    setSaveMessage(null)
    try {
      await saveSettings({ claude_prompt_template: promptTemplate })
      setSavedTemplate(promptTemplate)
      setSaveMessage({ type: 'success', text: 'Settings saved!' })
    } catch (err) {
      setSaveMessage({ type: 'error', text: err.message || 'Failed to save' })
    } finally {
      setIsSaving(false)
      setTimeout(() => setSaveMessage(null), 3000)
    }
  }

  const handleReset = () => {
    setPromptTemplate(DEFAULT_PROMPT_TEMPLATE)
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
        className="fixed top-0 right-0 h-full w-[480px] bg-surface border-l border-border z-50 flex flex-col shadow-2xl animate-slide-in-right"
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
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5 custom-scrollbar">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div>
              <label className="block text-xs font-mono text-text-secondary mb-2 uppercase tracking-wide">
                Claude Prompt Template
              </label>
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
                rows={14}
                placeholder="Enter prompt template..."
                spellCheck={false}
              />
            </div>
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
          <div className="flex gap-2">
            <button
              onClick={handleReset}
              data-testid="settings-reset-btn"
              title="Reset to default"
              className="p-2 rounded border border-border text-text-secondary hover:text-text-primary hover:bg-surface-light transition-colors"
            >
              <RotateCcw size={14} />
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving || !isDirty}
              data-testid="settings-save-btn"
              className="flex-1 py-2 rounded font-mono text-sm font-semibold border border-primary text-primary hover:bg-primary hover:text-black transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save size={14} />
              {isSaving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

export default SettingsPanel
