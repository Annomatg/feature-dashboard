import { X } from 'lucide-react'

const LANES = [
  { key: 'todo', label: 'TODO', color: '#f59e0b' },
  { key: 'inProgress', label: 'IN PROGRESS', color: '#3b82f6' },
  { key: 'done', label: 'DONE', color: '#22c55e' },
]

/**
 * MobileMoveSheet — bottom sheet shown after a long press on a kanban card.
 * Lets the user move the card to a different lane on touch devices.
 */
function MobileMoveSheet({ feature, fromLane, onMove, onClose }) {
  return (
    <>
      {/* Backdrop */}
      <div
        data-testid="mobile-move-sheet-backdrop"
        className="fixed inset-0 bg-black/60 z-40"
        onClick={onClose}
      />

      {/* Bottom sheet */}
      <div
        data-testid="mobile-move-sheet"
        className="fixed bottom-0 left-0 right-0 z-50 rounded-t-2xl border-t p-4"
        style={{ backgroundColor: '#1a1a1a', borderColor: '#3d3d3d' }}
      >
        {/* Drag handle */}
        <div className="w-12 h-1 bg-surface-light rounded-full mx-auto mb-4" />

        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1 min-w-0 pr-3">
            <p className="text-xs font-mono text-text-secondary mb-1 uppercase tracking-wider">
              Move card
            </p>
            <h3 className="text-sm font-semibold text-text-primary line-clamp-2 leading-snug">
              {feature.name}
            </h3>
          </div>
          <button
            onClick={onClose}
            data-testid="mobile-move-sheet-close"
            className="flex-shrink-0 p-1.5 rounded text-text-secondary hover:text-text-primary transition-colors"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Lane buttons */}
        <div className="space-y-2 pb-2">
          {LANES.map(({ key, label, color }) => {
            const isCurrent = key === fromLane
            return (
              <button
                key={key}
                disabled={isCurrent}
                onClick={() => {
                  if (!isCurrent) onMove(key)
                }}
                data-testid={`move-to-${key}`}
                className="w-full py-3 px-4 rounded-lg font-mono text-sm font-semibold flex items-center gap-3 transition-all duration-150"
                style={{
                  backgroundColor: isCurrent ? `${color}08` : `${color}15`,
                  color: isCurrent ? `${color}50` : color,
                  border: `1px solid ${isCurrent ? color + '20' : color + '40'}`,
                  cursor: isCurrent ? 'default' : 'pointer',
                }}
              >
                <div
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: isCurrent ? `${color}30` : color }}
                />
                {label}
                {isCurrent && (
                  <span className="ml-auto text-xs font-normal opacity-60">current</span>
                )}
              </button>
            )
          })}
        </div>
      </div>
    </>
  )
}

export default MobileMoveSheet
