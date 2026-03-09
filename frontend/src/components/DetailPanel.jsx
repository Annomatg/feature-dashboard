import { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react'
import { X, Trash2, Check, RotateCcw, Terminal, MessageSquare, ChevronDown, RefreshCw } from 'lucide-react'
import EditableSteps from './EditableSteps'
import GhostTextArea from './GhostTextArea'

async function fetchComments(featureId) {
  const response = await fetch(`/api/features/${featureId}/comments`)
  if (!response.ok) throw new Error('Failed to fetch comments')
  return response.json()
}

async function updateFeature(featureId, data) {
  const response = await fetch(`/api/features/${featureId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to update feature')
  }
  return response.json()
}

async function deleteFeatureApi(featureId) {
  const response = await fetch(`/api/features/${featureId}`, {
    method: 'DELETE'
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to delete feature')
  }
}

async function launchClaudeApi(featureId, hiddenExecution) {
  const response = await fetch(`/api/features/${featureId}/launch-claude`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hidden_execution: hiddenExecution })
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to launch Claude')
  }
  return response.json()
}

const MODEL_OPTIONS = [
  { value: 'haiku', label: 'Haiku', title: 'Fastest, most efficient' },
  { value: 'sonnet', label: 'Sonnet', title: 'Balanced (default)' },
  { value: 'opus', label: 'Opus', title: 'Most capable' },
]

// Editable field that shows value inline, turns into input on click
function EditableField({ value, onSave, multiline = false, className = '', placeholder = '' }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const inputRef = useRef(null)
  const cancellingRef = useRef(false)

  useEffect(() => {
    setDraft(value)
  }, [value])

  useEffect(() => {
    if (editing) {
      cancellingRef.current = false
      inputRef.current?.focus()
      if (!multiline) {
        inputRef.current?.select()
      }
    }
  }, [editing, multiline])

  const handleSave = useCallback(() => {
    if (cancellingRef.current) return
    setEditing(false)
    if (draft !== value) {
      onSave(draft)
    }
  }, [draft, value, onSave])

  const handleCancel = useCallback(() => {
    cancellingRef.current = true
    setEditing(false)
    setDraft(value)
  }, [value])

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      handleCancel()
    } else if (e.key === 'Enter' && !multiline) {
      handleSave()
    } else if (e.key === 'Enter' && e.ctrlKey && multiline) {
      handleSave()
    }
  }

  if (editing) {
    return (
      <div className="relative">
        {multiline ? (
          <GhostTextArea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            className={`w-full bg-background border border-primary rounded px-2 py-1.5 text-text-primary focus:outline-none resize-none ${className}`}
            rows={4}
            placeholder={placeholder}
          />
        ) : (
          <input
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            className={`w-full bg-background border border-primary rounded px-2 py-1.5 text-text-primary focus:outline-none ${className}`}
            placeholder={placeholder}
          />
        )}
        <div className="flex gap-1 mt-1 justify-end">
          <button
            onMouseDown={(e) => { e.preventDefault(); handleSave() }}
            className="p-1 rounded bg-primary text-black hover:opacity-80 transition-opacity"
            title="Save (Enter)"
          >
            <Check size={12} />
          </button>
          <button
            onMouseDown={(e) => { e.preventDefault(); handleCancel() }}
            className="p-1 rounded bg-surface-light text-text-secondary hover:text-text-primary transition-colors"
            title="Cancel (Esc)"
          >
            <RotateCcw size={12} />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      onClick={() => setEditing(true)}
      className={`cursor-text rounded px-2 py-1.5 hover:bg-surface-light transition-colors group ${className}`}
      title="Click to edit"
    >
      {value || <span className="text-text-secondary italic">{placeholder || 'Click to edit...'}</span>}
    </div>
  )
}


function ClaudeLogSection({ featureId, inProgress, claudeSessionId }) {
  const [collapsed, setCollapsed] = useState(false)
  const [liveData, setLiveData] = useState(null)   // from /api/autopilot/session-log
  const [histData, setHistData] = useState(null)   // from /api/features/{id}/session-log
  const [fetchError, setFetchError] = useState(null)
  const liveIntervalRef = useRef(null)
  const logContainerRef = useRef(null)
  const atBottomRef = useRef(true)

  // Live session is for this feature only when in-progress and feature_id matches
  const liveIsForThisFeature = inProgress && liveData?.feature_id === featureId

  // Display live data when the active session is for this feature; otherwise fall back to historical
  const displayData = liveIsForThisFeature ? liveData : histData
  const entries = displayData?.entries ?? []

  const fetchLive = useCallback(async () => {
    try {
      const resp = await fetch('/api/autopilot/session-log?limit=50')
      if (!resp.ok) throw new Error('Failed to fetch log')
      setLiveData(await resp.json())
      setFetchError(null)
    } catch (err) {
      setFetchError(err.message)
    }
  }, [])

  const fetchHist = useCallback(async () => {
    try {
      const resp = await fetch(`/api/features/${featureId}/session-log?limit=50`)
      if (!resp.ok) throw new Error('Failed to fetch log')
      setHistData(await resp.json())
      setFetchError(null)
    } catch (err) {
      setFetchError(err.message)
    }
  }, [featureId])

  // Poll live session log while in-progress
  useEffect(() => {
    if (!inProgress) {
      clearInterval(liveIntervalRef.current)
      liveIntervalRef.current = null
      return
    }
    fetchLive()
    liveIntervalRef.current = setInterval(fetchLive, 3000)
    return () => {
      clearInterval(liveIntervalRef.current)
      liveIntervalRef.current = null
    }
  }, [inProgress, fetchLive])

  // Fetch historical log whenever claudeSessionId or featureId changes (one-time, not polled)
  useEffect(() => {
    if (!claudeSessionId) return
    const controller = new AbortController()
    const load = async () => {
      try {
        const resp = await fetch(`/api/features/${featureId}/session-log?limit=50`, { signal: controller.signal })
        if (!resp.ok) throw new Error('Failed to fetch log')
        setHistData(await resp.json())
        setFetchError(null)
      } catch (err) {
        if (err.name !== 'AbortError') setFetchError(err.message)
      }
    }
    load()
    return () => controller.abort()
  }, [featureId, claudeSessionId])

  // Auto-scroll to bottom when new entries arrive — only if already pinned to bottom.
  // useLayoutEffect ensures the scroll fires synchronously after the DOM update and
  // before the browser paints, so tests and users never see a flash of un-scrolled content.
  useLayoutEffect(() => {
    const el = logContainerRef.current
    if (!el) return
    if (atBottomRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [entries.length])

  // When expanding the log, always jump to bottom and re-pin
  useEffect(() => {
    if (collapsed) return
    atBottomRef.current = true
    const el = logContainerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [collapsed])

  const handleScroll = useCallback(() => {
    const el = logContainerRef.current
    if (!el) return
    atBottomRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 20
  }, [])

  // Hide if no log source at all
  if (!inProgress && !claudeSessionId) return null
  // Hide if in-progress but active session is for another feature AND no historical session
  if (inProgress && !liveIsForThisFeature && !claudeSessionId) return null

  // Refresh the currently displayed source
  const handleRefresh = liveIsForThisFeature ? fetchLive : fetchHist

  const formatTime = (iso) => {
    try {
      return new Date(iso).toLocaleTimeString('en-US', { hour12: false })
    } catch {
      return iso
    }
  }

  return (
    <div data-testid="claude-log-section">
      <div className="flex items-center justify-between mb-2">
        <button
          onClick={() => setCollapsed(c => !c)}
          data-testid="claude-log-toggle"
          className="flex items-center gap-1.5 text-xs font-mono text-text-secondary uppercase tracking-wide hover:text-text-primary transition-colors"
        >
          <Terminal size={12} />
          Claude Log ({entries.length} entries)
          <ChevronDown size={12} className={`transition-transform ${collapsed ? '-rotate-90' : ''}`} />
        </button>
        <button
          onClick={handleRefresh}
          data-testid="claude-log-refresh"
          title="Refresh"
          className="p-1 rounded hover:bg-surface-light transition-colors"
        >
          <RefreshCw size={12} className="text-text-secondary" />
        </button>
      </div>
      {!collapsed && (
        <div
          ref={logContainerRef}
          onScroll={handleScroll}
          className="bg-background rounded border border-border overflow-y-auto max-h-[200px] custom-scrollbar"
          data-testid="claude-log-lines"
        >
          {fetchError ? (
            <p className="text-xs font-mono text-error p-2">{fetchError}</p>
          ) : entries.length === 0 ? (
            <p className="text-xs font-mono text-text-secondary p-2 italic">No output yet...</p>
          ) : (
            <div className="divide-y divide-border">
              {entries.map((entry, i) => (
                <div key={i} className="flex items-start gap-2 px-2 py-1 min-w-0">
                  <span className="text-xs font-mono text-text-secondary flex-shrink-0 pt-0.5">
                    {formatTime(entry.timestamp)}
                  </span>
                  <span
                    className={`text-xs font-mono px-1 rounded flex-shrink-0 ${
                      entry.entry_type === 'tool_use'
                        ? 'bg-blue-500/20 text-blue-400'
                        : entry.entry_type === 'thinking'
                        ? 'bg-purple-500/20 text-purple-400'
                        : 'bg-green-500/20 text-green-400'
                    }`}
                    data-testid="claude-log-stream-badge"
                  >
                    {entry.entry_type === 'tool_use'
                      ? (entry.tool_name?.split('__').pop() ?? 'tool')
                      : entry.entry_type === 'thinking'
                      ? 'think'
                      : 'text'}
                  </span>
                  <span className="text-xs font-mono text-text-primary break-all min-w-0">
                    {entry.text}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}


function DetailPanel({ feature, onClose, onUpdate, onDelete }) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isLaunching, setIsLaunching] = useState(false)
  const [launchMessage, setLaunchMessage] = useState(null)
  const [hiddenExecution, setHiddenExecution] = useState(true)
  const [comments, setComments] = useState([])
  const panelRef = useRef(null)

  useEffect(() => {
    fetchComments(feature.id)
      .then(setComments)
      .catch(() => setComments([]))
  }, [feature.id])

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleFieldSave = useCallback(async (field, value) => {
    setIsSaving(true)
    try {
      const updated = await updateFeature(feature.id, { [field]: value })
      onUpdate(updated)
    } catch (err) {
      console.error('Failed to update field:', err)
    } finally {
      setIsSaving(false)
    }
  }, [feature.id, onUpdate])

  const handleStepsSave = useCallback(async (steps) => {
    setIsSaving(true)
    try {
      const updated = await updateFeature(feature.id, { steps })
      onUpdate(updated)
    } catch (err) {
      console.error('Failed to update steps:', err)
    } finally {
      setIsSaving(false)
    }
  }, [feature.id, onUpdate])

  const handleDelete = async () => {
    try {
      await deleteFeatureApi(feature.id)
      onDelete(feature.id)
      onClose()
    } catch (err) {
      console.error('Failed to delete feature:', err)
    }
  }

  const handleLaunchClaude = async () => {
    setIsLaunching(true)
    setLaunchMessage(null)
    try {
      await launchClaudeApi(feature.id, hiddenExecution)
      setLaunchMessage({ type: 'success', text: 'Claude launched!' })
    } catch (err) {
      setLaunchMessage({ type: 'error', text: err.message || 'Failed to launch' })
    } finally {
      setIsLaunching(false)
      setTimeout(() => setLaunchMessage(null), 3000)
    }
  }

  const handleModelChange = useCallback(async (model) => {
    try {
      const updated = await updateFeature(feature.id, { model })
      onUpdate(updated)
    } catch (err) {
      console.error('Failed to update model:', err)
    }
  }, [feature.id, onUpdate])

  const statusLabel = feature.passes
    ? 'DONE'
    : feature.in_progress
    ? 'IN PROGRESS'
    : 'TODO'

  const statusColor = feature.passes
    ? '#22c55e'
    : feature.in_progress
    ? '#3b82f6'
    : '#f59e0b'

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
        data-testid="detail-panel-backdrop"
      />

      {/* Panel */}
      <div
        ref={panelRef}
        data-testid="detail-panel"
        className="fixed top-0 right-0 h-full w-full md:w-[420px] bg-surface border-l border-border z-50 flex flex-col shadow-2xl animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-text-secondary">
              #{feature.priority.toString().padStart(3, '0')}
            </span>
            <span
              className="px-2 py-0.5 rounded text-xs font-mono font-semibold"
              style={{ backgroundColor: `${statusColor}20`, color: statusColor }}
            >
              {statusLabel}
            </span>
            {isSaving && (
              <span className="text-xs font-mono text-text-secondary animate-pulse">
                saving...
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            data-testid="detail-panel-close"
            className="p-1.5 rounded hover:bg-surface-light transition-colors"
            aria-label="Close panel"
          >
            <X size={18} className="text-text-secondary hover:text-text-primary transition-colors" />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5 custom-scrollbar">
          {/* Title */}
          <div>
            <label className="block text-xs font-mono text-text-secondary mb-1 uppercase tracking-wide">
              Title
            </label>
            <EditableField
              value={feature.name}
              onSave={(v) => handleFieldSave('name', v)}
              className="text-text-primary font-semibold text-base"
              placeholder="Feature title"
            />
          </div>

          {/* Category */}
          <div>
            <label className="block text-xs font-mono text-text-secondary mb-1 uppercase tracking-wide">
              Category
            </label>
            <EditableField
              value={feature.category}
              onSave={(v) => handleFieldSave('category', v)}
              className="text-text-primary font-mono text-sm"
              placeholder="e.g. Frontend, Backend, API"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-mono text-text-secondary mb-1 uppercase tracking-wide">
              Description
            </label>
            <EditableField
              value={feature.description}
              onSave={(v) => handleFieldSave('description', v)}
              multiline
              className="text-text-primary text-sm leading-relaxed"
              placeholder="Describe what this feature should do..."
            />
          </div>

          {/* Steps */}
          <div>
            <label className="block text-xs font-mono text-text-secondary mb-2 uppercase tracking-wide">
              Steps ({feature.steps?.length ?? 0})
            </label>
            <EditableSteps
              steps={feature.steps ?? []}
              onSave={handleStepsSave}
            />
          </div>

          {/* Claude Log - shown for IN PROGRESS features or features with stored session logs */}
          <ClaudeLogSection featureId={feature.id} inProgress={feature.in_progress} claudeSessionId={feature.claude_session_id} />

          {/* Comments */}
          {comments.length > 0 && (
            <div data-testid="comments-section">
              <label className="block text-xs font-mono text-text-secondary mb-2 uppercase tracking-wide flex items-center gap-1.5">
                <MessageSquare size={12} />
                Comments ({comments.length})
              </label>
              <div className="space-y-2">
                {comments.map((comment) => (
                  <div
                    key={comment.id}
                    data-testid="comment-item"
                    className="bg-background rounded p-3 border border-border"
                  >
                    <p className="text-sm text-text-primary whitespace-pre-wrap break-words leading-relaxed">
                      {comment.content}
                    </p>
                    {comment.created_at && (
                      <p className="text-xs font-mono text-text-secondary mt-1.5">
                        {new Date(comment.created_at).toLocaleString()}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="border-t border-border pt-4">
            <div className="space-y-1.5 text-xs font-mono text-text-secondary">
              <div className="flex justify-between">
                <span>Priority</span>
                <span className="text-text-primary">#{feature.priority}</span>
              </div>
              <div className="flex justify-between">
                <span>ID</span>
                <span className="text-text-primary">{feature.id}</span>
              </div>
              {feature.created_at && (
                <div className="flex justify-between">
                  <span>Created</span>
                  <span className="text-text-primary">
                    {new Date(feature.created_at).toLocaleDateString()}
                  </span>
                </div>
              )}
              {feature.completed_at && (
                <div className="flex justify-between">
                  <span>Completed</span>
                  <span className="text-text-primary">
                    {new Date(feature.completed_at).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-border flex-shrink-0 space-y-2">
          {/* Launch Claude button - only for TODO and IN PROGRESS */}
          {!feature.passes && (
            <div>
              {/* Model selector */}
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-mono text-text-secondary flex-shrink-0">Model</span>
                <div className="flex gap-1 flex-1" data-testid="model-selector">
                  {MODEL_OPTIONS.map(({ value, label, title }) => (
                    <button
                      key={value}
                      onClick={() => handleModelChange(value)}
                      data-testid={`model-option-${value}`}
                      title={title}
                      className={`flex-1 py-1 rounded text-xs font-mono font-semibold border transition-all ${
                        (feature.model || 'sonnet') === value
                          ? 'border-primary bg-primary text-black'
                          : 'border-border text-text-secondary hover:border-primary hover:text-primary'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <label
                className="flex items-center gap-2 mb-2 cursor-pointer select-none"
                data-testid="hidden-execution-label"
              >
                <input
                  type="checkbox"
                  checked={hiddenExecution}
                  onChange={(e) => setHiddenExecution(e.target.checked)}
                  data-testid="hidden-execution-checkbox"
                  className="w-3.5 h-3.5 accent-primary cursor-pointer"
                />
                <span className="text-xs font-mono text-text-secondary">Hidden execution</span>
              </label>
              <button
                onClick={handleLaunchClaude}
                disabled={isLaunching}
                data-testid="launch-claude-btn"
                className="w-full py-2 rounded font-mono text-sm font-semibold border border-primary text-primary hover:bg-primary hover:text-black transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Terminal size={14} />
                {isLaunching ? 'Launching...' : 'Launch Claude'}
              </button>
              {launchMessage && (
                <p
                  data-testid="launch-claude-message"
                  className={`mt-1.5 text-xs font-mono text-center ${launchMessage.type === 'success' ? 'text-green-400' : 'text-error'}`}
                >
                  {launchMessage.text}
                </p>
              )}
            </div>
          )}

          {/* Delete */}
          {showDeleteConfirm ? (
            <div className="flex gap-2">
              <button
                onClick={handleDelete}
                data-testid="confirm-delete-btn"
                className="flex-1 py-2 rounded font-mono text-sm font-semibold bg-error text-white hover:opacity-80 transition-opacity"
              >
                Confirm Delete
              </button>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 rounded font-mono text-sm bg-surface-light text-text-secondary hover:text-text-primary transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              data-testid="delete-feature-btn"
              className="w-full py-2 rounded font-mono text-sm font-semibold border border-error text-error hover:bg-error hover:text-white transition-all flex items-center justify-center gap-2"
            >
              <Trash2 size={14} />
              Delete Feature
            </button>
          )}
        </div>
      </div>
    </>
  )
}

export default DetailPanel
