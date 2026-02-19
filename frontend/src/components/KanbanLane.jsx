import { useState, useRef } from 'react'
import { Plus } from 'lucide-react'
import KanbanCard from './KanbanCard'
import NewFeatureCard from './NewFeatureCard'

// Format a date string into a human-readable group label
function getDateGroupLabel(dateStr) {
  if (!dateStr) return 'Unknown'

  const date = new Date(dateStr)
  const today = new Date()

  const isSameDay = (a, b) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()

  if (isSameDay(date, today)) return 'Today'

  // Check days ago within the current week (up to 6 days back)
  for (let daysAgo = 1; daysAgo <= 6; daysAgo++) {
    const past = new Date(today)
    past.setDate(today.getDate() - daysAgo)
    if (isSameDay(date, past)) {
      return daysAgo === 1
        ? 'Yesterday'
        : date.toLocaleDateString('en-US', { weekday: 'long' }) // e.g. "Monday"
    }
  }

  // Older than 6 days — format as "Feb 14"
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// Group features by their completed_at date label
function groupByDate(features) {
  const groups = []
  const seen = new Map()

  for (const feature of features) {
    const label = getDateGroupLabel(feature.completed_at)
    if (!seen.has(label)) {
      seen.set(label, groups.length)
      groups.push({ label, features: [] })
    }
    groups[seen.get(label)].features.push(feature)
  }

  return groups
}

function KanbanLane({
  title,
  count,
  features,
  accentColor,
  onAddClick,
  selectedFeatureId,
  onCardClick,
  isAddingFeature,
  onSaveFeature,
  onCancelAdd,
  lane,
  onMoveToLane,
  onReorder,
  dragState,
  onDragStart,
  onDragEnd,
  isDoneLane = false,
  hasMore = false,
  onShowMore,
  isLoadingMore = false,
}) {
  const [isDragOver, setIsDragOver] = useState(false)
  // featureId being hovered over during same-lane drag (for drop indicator)
  const [dropTargetId, setDropTargetId] = useState(null)
  // 'before' | 'after' — where the drop indicator shows relative to dropTargetId
  const [dropPosition, setDropPosition] = useState(null)

  // Refs so handleDrop always reads the latest value (avoids stale closure)
  const dropTargetIdRef = useRef(null)
  const dropPositionRef = useRef(null)

  const handleDragOver = (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setIsDragOver(true)
  }

  const handleDragLeave = (e) => {
    // Only clear if leaving the lane container entirely
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setIsDragOver(false)
      setDropTargetId(null)
      setDropPosition(null)
      dropTargetIdRef.current = null
      dropPositionRef.current = null
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()

    // Read refs before clearing state
    const currentDropTargetId = dropTargetIdRef.current
    const currentDropPosition = dropPositionRef.current

    setIsDragOver(false)
    setDropTargetId(null)
    setDropPosition(null)
    dropTargetIdRef.current = null
    dropPositionRef.current = null

    const state = dragState.current
    if (!state) return

    const { feature, fromLane } = state

    if (fromLane !== lane) {
      // Cross-lane drop: move to this lane
      onMoveToLane(feature, lane)
      return
    }

    // Same-lane drop: place feature at the exact drop position
    if (currentDropTargetId && currentDropTargetId !== feature.id) {
      const insertBefore = currentDropPosition === 'before'
      onReorder(feature, currentDropTargetId, insertBefore)
    }
  }

  const updateDropTarget = (e, targetFeatureId) => {
    e.preventDefault()
    if (!dragState.current) return
    if (dragState.current.fromLane !== lane) return
    if (targetFeatureId === dragState.current.featureId) return

    const rect = e.currentTarget.getBoundingClientRect()
    const midY = rect.top + rect.height / 2
    const pos = e.clientY < midY ? 'before' : 'after'

    dropTargetIdRef.current = targetFeatureId
    dropPositionRef.current = pos
    setDropTargetId(targetFeatureId)
    setDropPosition(pos)
  }

  const dateGroups = isDoneLane ? groupByDate(features) : null

  return (
    <div
      className="flex flex-col h-full min-w-0 animate-slide-in"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Lane Header */}
      <div className="flex-shrink-0 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div
              className="w-1 h-8 rounded-full transition-all duration-150"
              style={{
                backgroundColor: accentColor,
                boxShadow: isDragOver ? `0 0 8px ${accentColor}80` : 'none'
              }}
            />
            <h2 className="text-xl font-bold font-mono uppercase tracking-wider text-text-primary">
              {title}
            </h2>
            <div
              className="px-2.5 py-1 rounded font-mono text-sm font-semibold"
              style={{
                backgroundColor: `${accentColor}15`,
                color: accentColor,
                border: `1px solid ${accentColor}40`
              }}
            >
              {count}
            </div>
          </div>

          <button
            onClick={onAddClick}
            className="p-2 rounded transition-all duration-200 hover:bg-surface-light group"
            style={{ border: '1px solid #3d3d3d' }}
            aria-label={`Add feature to ${title}`}
          >
            <Plus
              size={18}
              className="text-text-secondary group-hover:text-text-primary transition-colors"
            />
          </button>
        </div>

        {/* Divider — glows when drag target */}
        <div
          className="h-px transition-all duration-150"
          style={{
            background: isDragOver
              ? `linear-gradient(90deg, ${accentColor} 0%, ${accentColor}40 100%)`
              : `linear-gradient(90deg, ${accentColor}60 0%, transparent 100%)`
          }}
        />
      </div>

      {/* Scrollable Feature List */}
      <div
        className="flex-1 overflow-y-auto custom-scrollbar pr-2 rounded-lg transition-all duration-150"
        style={{
          outline: isDragOver ? `1px dashed ${accentColor}60` : 'none',
          outlineOffset: '-4px'
        }}
      >
        {/* New Feature Card */}
        {isAddingFeature && (
          <div className="mb-3">
            <NewFeatureCard
              lane={lane}
              onSave={onSaveFeature}
              onCancel={onCancelAdd}
              accentColor={accentColor}
            />
          </div>
        )}

        {/* Done lane: date-grouped features */}
        {isDoneLane ? (
          features.length === 0 && !isAddingFeature ? (
            <div className="text-center py-12 px-4">
              <div className="text-4xl mb-3 opacity-20">○</div>
              <p className="text-text-secondary text-sm font-mono">
                No features yet
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {dateGroups.map((group) => (
                <div key={group.label}>
                  {/* Date group header */}
                  <div
                    className="sticky top-0 z-10 py-1.5 px-2 mb-2 mt-1"
                    style={{ background: 'var(--color-background, #0f0f0f)' }}
                  >
                    <span
                      className="text-xs font-mono font-semibold uppercase tracking-widest"
                      style={{ color: `${accentColor}90` }}
                      data-testid="done-date-group"
                    >
                      {group.label}
                    </span>
                    <div
                      className="h-px mt-1"
                      style={{ background: `${accentColor}25` }}
                    />
                  </div>

                  {/* Features in this group */}
                  <div className="space-y-3 mb-4">
                    {group.features.map((feature, index) => (
                      <div
                        key={feature.id}
                        onDragEnter={(e) => updateDropTarget(e, feature.id)}
                        onDragOver={(e) => updateDropTarget(e, feature.id)}
                      >
                        {dropTargetId === feature.id && dropPosition === 'before' && (
                          <div
                            className="h-0.5 rounded-full mb-1"
                            style={{ backgroundColor: accentColor }}
                          />
                        )}
                        <KanbanCard
                          feature={feature}
                          accentColor={accentColor}
                          index={index}
                          isSelected={selectedFeatureId === feature.id}
                          onClick={onCardClick}
                          lane={lane}
                          dragState={dragState}
                          onDragStart={onDragStart}
                          onDragEnd={onDragEnd}
                        />
                        {dropTargetId === feature.id && dropPosition === 'after' && (
                          <div
                            className="h-0.5 rounded-full mt-1"
                            style={{ backgroundColor: accentColor }}
                          />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {/* Show more button */}
              {hasMore && (
                <button
                  onClick={onShowMore}
                  disabled={isLoadingMore}
                  data-testid="show-more-done"
                  className="w-full py-2.5 px-4 rounded font-mono text-sm transition-all duration-200 disabled:opacity-50"
                  style={{
                    color: accentColor,
                    border: `1px solid ${accentColor}40`,
                    backgroundColor: `${accentColor}08`,
                  }}
                  onMouseEnter={(e) => {
                    if (!isLoadingMore) e.currentTarget.style.backgroundColor = `${accentColor}18`
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = `${accentColor}08`
                  }}
                >
                  {isLoadingMore ? 'Loading...' : 'Show more'}
                </button>
              )}
            </div>
          )
        ) : (
          /* Non-done lanes: flat list */
          features.length === 0 && !isAddingFeature ? (
            <div className="text-center py-12 px-4">
              <div className="text-4xl mb-3 opacity-20">○</div>
              <p className="text-text-secondary text-sm font-mono">
                No features yet
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {features.map((feature, index) => (
                <div
                  key={feature.id}
                  onDragEnter={(e) => updateDropTarget(e, feature.id)}
                  onDragOver={(e) => updateDropTarget(e, feature.id)}
                >
                  {/* Drop indicator above */}
                  {dropTargetId === feature.id && dropPosition === 'before' && (
                    <div
                      className="h-0.5 rounded-full mb-1"
                      style={{ backgroundColor: accentColor }}
                    />
                  )}
                  <KanbanCard
                    feature={feature}
                    accentColor={accentColor}
                    index={index}
                    isSelected={selectedFeatureId === feature.id}
                    onClick={onCardClick}
                    lane={lane}
                    dragState={dragState}
                    onDragStart={onDragStart}
                    onDragEnd={onDragEnd}
                  />
                  {/* Drop indicator below */}
                  {dropTargetId === feature.id && dropPosition === 'after' && (
                    <div
                      className="h-0.5 rounded-full mt-1"
                      style={{ backgroundColor: accentColor }}
                    />
                  )}
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  )
}

export default KanbanLane
