import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Trash2, Check, RotateCcw, Plus, ChevronUp, ChevronDown } from 'lucide-react'

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
          <textarea
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

// Editable steps list
function EditableSteps({ steps, onSave }) {
  const [editingIndex, setEditingIndex] = useState(null)
  const [draft, setDraft] = useState('')
  const [newStep, setNewStep] = useState('')
  const editRef = useRef(null)
  const newStepRef = useRef(null)

  useEffect(() => {
    if (editingIndex !== null) {
      editRef.current?.focus()
      editRef.current?.select()
    }
  }, [editingIndex])

  const startEdit = (index) => {
    setEditingIndex(index)
    setDraft(steps[index])
  }

  const saveEdit = () => {
    if (editingIndex === null) return
    const updated = [...steps]
    if (draft.trim()) {
      updated[editingIndex] = draft.trim()
    } else {
      updated.splice(editingIndex, 1)
    }
    setEditingIndex(null)
    setDraft('')
    onSave(updated)
  }

  const cancelEdit = () => {
    setEditingIndex(null)
    setDraft('')
  }

  const removeStep = (index) => {
    const updated = steps.filter((_, i) => i !== index)
    onSave(updated)
  }

  const moveStep = (index, direction) => {
    const updated = [...steps]
    const targetIndex = direction === 'up' ? index - 1 : index + 1
    if (targetIndex < 0 || targetIndex >= steps.length) return
    ;[updated[index], updated[targetIndex]] = [updated[targetIndex], updated[index]]
    onSave(updated)
  }

  const addStep = () => {
    if (!newStep.trim()) return
    onSave([...steps, newStep.trim()])
    setNewStep('')
    newStepRef.current?.focus()
  }

  const handleNewStepKey = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addStep()
    }
  }

  return (
    <div>
      <div className="space-y-1 mb-2">
        {steps.map((step, index) => (
          <div key={index} className="group flex items-start gap-1.5">
            <span className="font-mono text-xs text-text-secondary mt-2 w-5 flex-shrink-0">
              {index + 1}.
            </span>
            <div className="flex-1 min-w-0">
              {editingIndex === index ? (
                <div>
                  <input
                    ref={editRef}
                    type="text"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onBlur={saveEdit}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit()
                      if (e.key === 'Escape') { e.stopPropagation(); cancelEdit() }
                    }}
                    className="w-full bg-background border border-primary rounded px-2 py-1 text-sm text-text-primary focus:outline-none"
                  />
                </div>
              ) : (
                <div
                  onClick={() => startEdit(index)}
                  className="text-sm text-text-primary cursor-text rounded px-2 py-1 hover:bg-surface-light transition-colors"
                >
                  {step}
                </div>
              )}
            </div>
            <div className="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
              <button
                onClick={() => moveStep(index, 'up')}
                disabled={index === 0}
                className="p-0.5 rounded hover:bg-surface-light disabled:opacity-30 transition-colors"
                title="Move up"
              >
                <ChevronUp size={12} className="text-text-secondary" />
              </button>
              <button
                onClick={() => moveStep(index, 'down')}
                disabled={index === steps.length - 1}
                className="p-0.5 rounded hover:bg-surface-light disabled:opacity-30 transition-colors"
                title="Move down"
              >
                <ChevronDown size={12} className="text-text-secondary" />
              </button>
            </div>
            <button
              onClick={() => removeStep(index)}
              className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-surface-light transition-all flex-shrink-0 mt-0.5"
              title="Remove step"
            >
              <Trash2 size={12} className="text-error" />
            </button>
          </div>
        ))}
      </div>

      {/* Add new step */}
      <div className="flex gap-2 mt-2">
        <input
          ref={newStepRef}
          type="text"
          value={newStep}
          onChange={(e) => setNewStep(e.target.value)}
          onKeyDown={handleNewStepKey}
          placeholder="Add a step (press Enter)..."
          className="flex-1 bg-background border border-border rounded px-2 py-1.5 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-primary transition-colors"
        />
        <button
          onClick={addStep}
          disabled={!newStep.trim()}
          className="p-1.5 rounded border border-border hover:bg-surface-light disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          title="Add step"
        >
          <Plus size={14} className="text-text-secondary" />
        </button>
      </div>
    </div>
  )
}

function DetailPanel({ feature, onClose, onUpdate, onDelete }) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const panelRef = useRef(null)

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
        className="fixed top-0 right-0 h-full w-[420px] bg-surface border-l border-border z-50 flex flex-col shadow-2xl animate-slide-in-right"
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

        {/* Footer - Delete */}
        <div className="px-5 py-4 border-t border-border flex-shrink-0">
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
