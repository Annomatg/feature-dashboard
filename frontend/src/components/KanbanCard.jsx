import { useRef } from 'react'
import { FileText, GitCommit } from 'lucide-react'

// Detect touch-only devices once at module load time.
// On touch devices the HTML5 drag-and-drop API is not triggered by touch events,
// so we disable draggable and the grab cursor to avoid a confusing UX.
const isTouchDevice =
  typeof window !== 'undefined' &&
  (navigator.maxTouchPoints > 0 || 'ontouchstart' in window)

// Long press duration (ms) before mobile drag activates
const LONG_PRESS_MS = 500
// Max pixels of movement before a press is no longer considered a long press
const LONG_PRESS_MOVE_THRESHOLD = 10

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
  /**
   * Mobile drag-and-drop callback.
   * Called after a long-press: (feature, touchX, touchY) => void
   * When provided, replaces the old bottom-sheet long-press behaviour.
   */
  onMobileDragStart,
  /** True while this specific card is being touch-dragged (dims the card in-place) */
  isMobileDragging = false,
  /** Latest Claude session log text shown for in-progress features */
  claudeLogSnippet = null,
  /** Feature ID the snippet belongs to (only show snippet on this card) */
  claudeLogFeatureId = null,
}) {
  const hasDescription = feature.description && feature.description.trim().length > 0

  // Long-press state (refs to avoid re-renders)
  const longPressTimer   = useRef(null)
  const touchStartPos    = useRef(null)
  const longPressFired   = useRef(false)

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

  // Touch handlers for long-press → mobile drag
  const handleTouchStart = (e) => {
    const touch = e.touches[0]
    touchStartPos.current = { x: touch.clientX, y: touch.clientY }
    longPressFired.current = false
    longPressTimer.current = setTimeout(() => {
      longPressFired.current = true
      longPressTimer.current = null
      // Optional haptic feedback on devices that support it
      navigator.vibrate?.(10)
      onMobileDragStart?.(feature, touchStartPos.current.x, touchStartPos.current.y)
    }, LONG_PRESS_MS)
  }

  const handleTouchMove = (e) => {
    if (!longPressTimer.current || !touchStartPos.current) return
    const touch = e.touches[0]
    const dx = Math.abs(touch.clientX - touchStartPos.current.x)
    const dy = Math.abs(touch.clientY - touchStartPos.current.y)
    if (dx > LONG_PRESS_MOVE_THRESHOLD || dy > LONG_PRESS_MOVE_THRESHOLD) {
      clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }

  const handleTouchEnd = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }

  // Prevent click from opening detail panel when a long press just fired
  const handleClick = () => {
    if (longPressFired.current) {
      longPressFired.current = false
      return
    }
    onClick?.(feature)
  }

  return (
    <div
      draggable={!isTouchDevice}
      onDragStart={!isTouchDevice ? handleDragStart : undefined}
      onDragEnd={!isTouchDevice ? handleDragEnd : undefined}
      onTouchStart={onMobileDragStart ? handleTouchStart : undefined}
      onTouchMove={onMobileDragStart ? handleTouchMove : undefined}
      onTouchEnd={onMobileDragStart ? handleTouchEnd : undefined}
      onClick={handleClick}
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
        transform: isSelected ? 'translateY(-2px)' : 'none',
        opacity: isMobileDragging ? 0.3 : 1,
        transition: isMobileDragging ? 'opacity 0.15s ease' : undefined,
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
          {feature.commit_count > 0 && (
            <span
              className="flex items-center gap-0.5"
              title={`${feature.commit_count} commit${feature.commit_count !== 1 ? 's' : ''}`}
              data-testid="commit-indicator"
            >
              <GitCommit size={14} style={{ color: `${accentColor}80` }} />
              <span className="font-mono text-xs" style={{ color: `${accentColor}80` }}>
                {feature.commit_count}
              </span>
            </span>
          )}
        </div>
      </div>

      {/* Footer: claude log (left) + steps count (right) */}
      {(() => {
        // Only show claude log snippet if this card's feature id matches
        const activeSnippet = feature.in_progress && claudeLogSnippet && feature.id === claudeLogFeatureId ? claudeLogSnippet : null
        const hasFooter = activeSnippet || (feature.steps && feature.steps.length > 0)
        if (!hasFooter) return null
        return (
          <div className="flex items-center gap-2 mt-3">
            {activeSnippet ? (
              <span
                className="text-xs text-blue-400 truncate flex-1 min-w-0 italic"
                title={activeSnippet}
                data-testid="claude-log-snippet"
              >
                {activeSnippet}
              </span>
            ) : (
              <div className="flex-1 h-px bg-surface-light" />
            )}
            {feature.steps && feature.steps.length > 0 && (
              <span className="text-xs font-mono text-text-secondary flex-shrink-0">
                {feature.steps.length} {feature.steps.length === 1 ? 'step' : 'steps'}
              </span>
            )}
          </div>
        )
      })()}
    </div>
  )
}

export default KanbanCard
