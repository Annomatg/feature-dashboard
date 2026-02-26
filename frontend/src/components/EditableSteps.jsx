import { useState, useEffect, useRef } from 'react'
import { Trash2, Plus, ChevronUp, ChevronDown } from 'lucide-react'

// Shared editable steps list used in both NewFeatureCard and DetailPanel
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
                  title="Click to edit"
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
                aria-label="Move step up"
              >
                <ChevronUp size={12} className="text-text-secondary" />
              </button>
              <button
                onClick={() => moveStep(index, 'down')}
                disabled={index === steps.length - 1}
                className="p-0.5 rounded hover:bg-surface-light disabled:opacity-30 transition-colors"
                title="Move down"
                aria-label="Move step down"
              >
                <ChevronDown size={12} className="text-text-secondary" />
              </button>
            </div>
            <button
              onClick={() => removeStep(index)}
              className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-surface-light transition-all flex-shrink-0 mt-0.5"
              title="Remove step"
              aria-label="Remove step"
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
          aria-label="Add step"
        >
          <Plus size={14} className="text-text-secondary" />
        </button>
      </div>
    </div>
  )
}

export default EditableSteps
