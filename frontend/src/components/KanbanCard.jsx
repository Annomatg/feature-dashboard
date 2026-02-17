import { FileText } from 'lucide-react'

function KanbanCard({
  feature,
  accentColor,
  index = 0,
  isSelected = false,
  onClick,
  lane,
  dragState,
  onDragStart,
  onDragEnd,
}) {
  const hasDescription = feature.description && feature.description.trim().length > 0

  const handleDragStart = (e) => {
    e.stopPropagation()
    dragState.current = { featureId: feature.id, feature, fromLane: lane }
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(feature.id))
    onDragStart?.()
    // Slight delay so browser captures card before opacity change
    requestAnimationFrame(() => {
      e.target.style.opacity = '0.4'
    })
  }

  const handleDragEnd = (e) => {
    e.target.style.opacity = ''
    dragState.current = null
    onDragEnd?.()
  }

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onClick={() => onClick?.(feature)}
      data-testid="kanban-card"
      data-feature-id={feature.id}
      className="bg-surface border rounded-lg p-4 transition-all duration-200 cursor-grab active:cursor-grabbing group relative select-none"
      style={{
        borderLeftWidth: '3px',
        borderLeftColor: accentColor,
        borderColor: isSelected ? accentColor : '#3d3d3d',
        boxShadow: isSelected
          ? `0 0 0 2px ${accentColor}40, 0 4px 12px rgba(0,0,0,0.3)`
          : 'none',
        animationDelay: `${index * 50}ms`,
        transform: isSelected ? 'translateY(-2px)' : 'none'
      }}
      onMouseEnter={(e) => {
        if (!isSelected) {
          e.currentTarget.style.borderColor = `${accentColor}80`
          e.currentTarget.style.boxShadow = `0 0 0 1px ${accentColor}20, 0 2px 8px rgba(0,0,0,0.2)`
        }
      }}
      onMouseLeave={(e) => {
        if (!isSelected) {
          e.currentTarget.style.borderColor = '#3d3d3d'
          e.currentTarget.style.boxShadow = 'none'
        }
      }}
    >
      {/* Priority & Category */}
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-xs text-text-secondary">
          #{feature.priority.toString().padStart(3, '0')}
        </span>
        <span
          className="px-2 py-0.5 rounded text-xs font-mono"
          style={{
            backgroundColor: `${accentColor}10`,
            color: accentColor
          }}
        >
          {feature.category}
        </span>
      </div>

      {/* Feature Name */}
      <div className="flex items-start gap-2 mb-2">
        <h3 className="text-text-primary font-semibold line-clamp-2 group-hover:text-white transition-colors flex-1">
          {feature.name}
        </h3>
        {hasDescription && (
          <FileText
            size={14}
            className="text-text-secondary flex-shrink-0 mt-0.5"
            style={{ color: `${accentColor}80` }}
          />
        )}
      </div>

      {/* Steps count */}
      {feature.steps && feature.steps.length > 0 && (
        <div className="flex items-center gap-2 mt-3">
          <div className="flex-1 h-px bg-surface-light" />
          <span className="text-xs font-mono text-text-secondary">
            {feature.steps.length} {feature.steps.length === 1 ? 'step' : 'steps'}
          </span>
        </div>
      )}
    </div>
  )
}

export default KanbanCard
