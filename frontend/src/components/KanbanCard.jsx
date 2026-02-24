import { FileText, MessageSquare } from 'lucide-react'

// Detect touch-only devices once at module load time.
// On touch devices the HTML5 drag-and-drop API is not triggered by touch events,
// so we disable draggable and the grab cursor to avoid a confusing UX.
const isTouchDevice =
  typeof window !== 'undefined' &&
  (navigator.maxTouchPoints > 0 || 'ontouchstart' in window)

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
      draggable={!isTouchDevice}
      onDragStart={!isTouchDevice ? handleDragStart : undefined}
      onDragEnd={!isTouchDevice ? handleDragEnd : undefined}
      onClick={() => onClick?.(feature)}
      data-testid="kanban-card"
      data-feature-id={feature.id}
      className={`bg-surface border rounded-lg p-3 md:p-4 transition-all duration-200 group relative select-none ${
        isTouchDevice ? 'cursor-pointer' : 'cursor-grab active:cursor-grabbing'
      }`}
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
      {/* ID, Priority & Category */}
      <div className="flex items-center justify-between mb-2 gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-shrink-0">
          <span className="font-mono text-xs text-text-secondary" title="Task ID">
            #{feature.id}
          </span>
          <span className="font-mono text-xs text-text-secondary opacity-50" title="Priority">
            P{feature.priority}
          </span>
        </div>
        <span
          className="px-2 py-0.5 rounded text-xs font-mono truncate max-w-[100px] md:max-w-[160px]"
          style={{
            backgroundColor: `${accentColor}10`,
            color: accentColor
          }}
          title={feature.category}
        >
          {feature.category}
        </span>
      </div>

      {/* Feature Name */}
      <div className="flex items-start gap-2 mb-2">
        <h3 className="text-sm text-text-primary font-semibold line-clamp-2 group-hover:text-white transition-colors flex-1 min-w-0">
          {feature.name}
        </h3>
        <div className="flex items-center gap-1 flex-shrink-0 mt-0.5">
          {hasDescription && (
            <FileText
              size={14}
              style={{ color: `${accentColor}80` }}
            />
          )}
          {feature.comment_count > 0 && (
            <span
              className="flex items-center gap-0.5"
              title={`${feature.comment_count} comment${feature.comment_count !== 1 ? 's' : ''}`}
              data-testid="comment-indicator"
            >
              <MessageSquare size={14} style={{ color: `${accentColor}80` }} />
              <span className="font-mono text-xs" style={{ color: `${accentColor}80` }}>
                {feature.comment_count}
              </span>
            </span>
          )}
        </div>
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
