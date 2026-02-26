import { ChevronLeft, ChevronRight } from 'lucide-react'
import { LANE_KEYS } from '../hooks/useMobileDrag'

const LANE_LABELS = { todo: 'TODO', inProgress: 'IN PROGRESS', done: 'DONE' }

/**
 * MobileDragOverlay — rendered on top of the board during a mobile touch drag.
 *
 * Shows:
 *   • A semi-transparent ghost card that follows the user's finger.
 *   • Left / right edge indicators with a progress bar that fill up as the
 *     user holds their finger near an edge (lane switch countdown).
 *   • The name of the lane that will be switched to on each edge.
 */
function MobileDragOverlay({ feature, ghostPos, accentColor, edgeSide, edgeProgress, activeMobileLane }) {
  if (!feature) return null

  const laneIdx   = LANE_KEYS.indexOf(activeMobileLane)
  const prevLabel = laneIdx > 0 ? LANE_LABELS[LANE_KEYS[laneIdx - 1]] : null
  const nextLabel = laneIdx < LANE_KEYS.length - 1 ? LANE_LABELS[LANE_KEYS[laneIdx + 1]] : null

  return (
    <>
      {/* Ghost card — follows the finger */}
      <div
        data-testid="mobile-drag-ghost"
        style={{
          position: 'fixed',
          left: ghostPos.x - 160,
          top:  ghostPos.y - 40,
          width: 300,
          pointerEvents: 'none',
          zIndex: 9999,
          opacity: 0.88,
          transform: 'rotate(2deg) scale(1.04)',
          borderRadius: 8,
          backgroundColor: '#1a1a1a',
          borderWidth: 1,
          borderStyle: 'solid',
          borderColor: accentColor,
          borderLeftWidth: 3,
          borderLeftColor: accentColor,
          boxShadow: `0 12px 40px rgba(0,0,0,0.6), 0 0 0 2px ${accentColor}40`,
          padding: '10px 12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#a3a3a3' }}>
            #{feature.id}
          </span>
          <span
            style={{
              fontFamily: 'monospace',
              fontSize: 11,
              padding: '1px 6px',
              borderRadius: 4,
              backgroundColor: `${accentColor}15`,
              color: accentColor,
              maxWidth: 120,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {feature.category}
          </span>
        </div>
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: '#f5f5f5',
            lineHeight: 1.4,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {feature.name}
        </div>
      </div>

      {/* Left edge indicator (switch to previous lane) */}
      {edgeSide === 'left' && prevLabel && (
        <div
          data-testid="mobile-drag-edge-left"
          style={{
            position: 'fixed',
            left: 0, top: 0, bottom: 0,
            width: 64,
            zIndex: 9998,
            pointerEvents: 'none',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            background: `linear-gradient(to right, ${accentColor}50, transparent)`,
          }}
        >
          <ChevronLeft size={28} style={{ color: accentColor }} />
          <span style={{ fontFamily: 'monospace', fontSize: 10, color: accentColor, textAlign: 'center', writingMode: 'vertical-lr', transform: 'rotate(180deg)' }}>
            {prevLabel}
          </span>
          <ProgressBar progress={edgeProgress} color={accentColor} />
        </div>
      )}

      {/* Right edge indicator (switch to next lane) */}
      {edgeSide === 'right' && nextLabel && (
        <div
          data-testid="mobile-drag-edge-right"
          style={{
            position: 'fixed',
            right: 0, top: 0, bottom: 0,
            width: 64,
            zIndex: 9998,
            pointerEvents: 'none',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            background: `linear-gradient(to left, ${accentColor}50, transparent)`,
          }}
        >
          <ChevronRight size={28} style={{ color: accentColor }} />
          <span style={{ fontFamily: 'monospace', fontSize: 10, color: accentColor, textAlign: 'center', writingMode: 'vertical-lr' }}>
            {nextLabel}
          </span>
          <ProgressBar progress={edgeProgress} color={accentColor} />
        </div>
      )}
    </>
  )
}

function ProgressBar({ progress, color }) {
  return (
    <div
      style={{
        width: 4,
        height: 80,
        borderRadius: 2,
        backgroundColor: `${color}25`,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: '100%',
          height: `${progress * 100}%`,
          backgroundColor: color,
          borderRadius: 2,
          transition: 'height 0.05s linear',
        }}
      />
    </div>
  )
}

export default MobileDragOverlay
