import { useState, useEffect, useRef } from 'react'
import { X, Plus, Trash2 } from 'lucide-react'

const MODEL_OPTIONS = [
  { value: 'haiku', label: 'Haiku', title: 'Fastest, most efficient' },
  { value: 'sonnet', label: 'Sonnet', title: 'Balanced (default)' },
  { value: 'opus', label: 'Opus', title: 'Most capable' },
]

function NewFeatureCard({ lane, onSave, onCancel, accentColor }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [steps, setSteps] = useState([])
  const [currentStep, setCurrentStep] = useState('')
  const [model, setModel] = useState('sonnet')
  const [addToTop, setAddToTop] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const titleInputRef = useRef(null)

  // Auto-focus title field when component mounts
  useEffect(() => {
    titleInputRef.current?.focus()
  }, [])

  const handleAddStep = () => {
    if (currentStep.trim()) {
      setSteps([...steps, currentStep.trim()])
      setCurrentStep('')
    }
  }

  const handleRemoveStep = (index) => {
    setSteps(steps.filter((_, i) => i !== index))
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleAddStep()
    }
  }

  const handleSave = async () => {
    if (!title.trim()) return

    setIsSaving(true)
    try {
      await onSave({
        name: title.trim(),
        description: description.trim() || '',
        category: category.trim() || 'General',
        steps: steps.length > 0 ? steps : [],
        model,
        addToTop,
        lane
      })
    } catch (error) {
      console.error('Failed to save feature:', error)
    } finally {
      setIsSaving(false)
    }
  }

  const canSave = title.trim().length > 0 && !isSaving

  return (
    <div
      className="bg-surface border rounded-lg p-4 shadow-lg animate-slide-in"
      style={{
        borderLeftWidth: '3px',
        borderLeftColor: accentColor,
        borderColor: `${accentColor}60`,
        boxShadow: `0 0 0 1px ${accentColor}40, 0 4px 12px rgba(0,0,0,0.3)`
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-mono font-semibold text-text-primary">
          NEW FEATURE
        </h3>
        <button
          onClick={onCancel}
          className="p-1 rounded hover:bg-surface-light transition-colors"
          aria-label="Cancel"
        >
          <X size={16} className="text-text-secondary hover:text-text-primary" />
        </button>
      </div>

      {/* Title (required) */}
      <div className="mb-3">
        <label className="block text-xs font-mono text-text-secondary mb-1">
          Title <span className="text-error">*</span>
        </label>
        <input
          ref={titleInputRef}
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Enter feature title..."
          className="w-full bg-background border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-primary transition-colors"
          maxLength={255}
        />
      </div>

      {/* Category (optional) */}
      <div className="mb-3">
        <label className="block text-xs font-mono text-text-secondary mb-1">
          Category
        </label>
        <input
          type="text"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="e.g., Frontend, Backend, API..."
          className="w-full bg-background border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-primary transition-colors"
          maxLength={100}
        />
      </div>

      {/* Description (optional) */}
      <div className="mb-3">
        <label className="block text-xs font-mono text-text-secondary mb-1">
          Description
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe what this feature should do..."
          className="w-full bg-background border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-primary transition-colors resize-none"
          rows={3}
        />
      </div>

      {/* Steps (optional) */}
      <div className="mb-3">
        <label className="block text-xs font-mono text-text-secondary mb-1">
          Steps
        </label>

        {/* Existing steps */}
        {steps.length > 0 && (
          <div className="mb-2 space-y-1">
            {steps.map((step, index) => (
              <div
                key={index}
                className="flex items-center gap-2 bg-background rounded px-2 py-1.5 group"
              >
                <span className="text-xs font-mono text-text-secondary">
                  {index + 1}.
                </span>
                <span className="flex-1 text-sm text-text-primary">
                  {step}
                </span>
                <button
                  onClick={() => handleRemoveStep(index)}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:bg-surface-light rounded transition-all"
                  aria-label="Remove step"
                >
                  <Trash2 size={12} className="text-error" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Add step input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={currentStep}
            onChange={(e) => setCurrentStep(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Add a step (press Enter)..."
            className="flex-1 bg-background border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-primary transition-colors"
          />
          <button
            onClick={handleAddStep}
            disabled={!currentStep.trim()}
            className="px-3 py-2 rounded border border-border hover:bg-surface-light disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="Add step"
          >
            <Plus size={16} className="text-text-secondary" />
          </button>
        </div>
      </div>

      {/* Model selector */}
      <div className="mb-3">
        <label className="block text-xs font-mono text-text-secondary mb-1">
          Model
        </label>
        <div className="flex gap-1" data-testid="model-selector">
          {MODEL_OPTIONS.map(({ value, label, title }) => (
            <button
              key={value}
              type="button"
              onClick={() => setModel(value)}
              data-testid={`model-option-${value}`}
              title={title}
              className={`flex-1 py-1.5 rounded text-xs font-mono font-semibold border transition-all ${
                model === value
                  ? 'border-primary bg-primary text-black'
                  : 'border-border text-text-secondary hover:border-primary hover:text-primary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Priority toggle */}
      <div className="mb-4">
        <label className="flex items-center gap-2 cursor-pointer group">
          <input
            type="checkbox"
            checked={addToTop}
            onChange={(e) => setAddToTop(e.target.checked)}
            className="w-4 h-4 rounded border-border bg-background checked:bg-primary checked:border-primary focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background cursor-pointer"
          />
          <span className="text-xs font-mono text-text-secondary group-hover:text-text-primary transition-colors">
            Add to top of list (high priority)
          </span>
        </label>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 pt-3 border-t border-border">
        <button
          onClick={handleSave}
          disabled={!canSave}
          className="flex-1 px-4 py-2 rounded font-mono text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            backgroundColor: canSave ? accentColor : '#2a2a2a',
            color: canSave ? '#000' : '#666',
            border: `1px solid ${canSave ? accentColor : '#3d3d3d'}`
          }}
        >
          {isSaving ? 'Saving...' : 'Save'}
        </button>
        <button
          onClick={onCancel}
          disabled={isSaving}
          className="px-4 py-2 rounded font-mono text-sm font-semibold bg-background border border-border text-text-secondary hover:bg-surface-light hover:text-text-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

export default NewFeatureCard
