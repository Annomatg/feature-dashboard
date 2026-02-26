/**
 * useSwipeLane — detects horizontal swipe gestures to switch Kanban lanes on mobile.
 *
 * Behaviour:
 *   - Swipe left  → advance to the next lane  (todo → inProgress → done)
 *   - Swipe right → go back to the previous lane (done → inProgress → todo)
 *   - Ignores swipes when a drag operation is in progress.
 *   - Ignores mostly-vertical movements (scroll).
 *
 * Usage:
 *   const { onTouchStart, onTouchEnd } = useSwipeLane({ activeMobileLane, setActiveMobileLane, isDragging })
 *   <div data-testid="kanban-lanes" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>...</div>
 */

import { useRef } from 'react'

export const LANE_KEYS = ['todo', 'inProgress', 'done']

const MIN_SWIPE_DISTANCE = 60   // px horizontal distance to trigger a lane switch
const MAX_VERTICAL_RATIO = 0.6  // |dy|/|dx| must be below this to count as horizontal

/**
 * @param {object} options
 * @param {string}   options.activeMobileLane   - Current active lane key
 * @param {function} options.setActiveMobileLane - State setter for the active lane
 * @param {boolean}  options.isDragging          - Suppresses swipe while a card drag is active
 */
export function useSwipeLane({ activeMobileLane, setActiveMobileLane, isDragging }) {
  const touchStart = useRef(null)

  const onTouchStart = (e) => {
    if (isDragging) return
    const touch = e.touches[0]
    touchStart.current = { x: touch.clientX, y: touch.clientY }
  }

  const onTouchEnd = (e) => {
    if (isDragging || touchStart.current === null) return

    const touch = e.changedTouches[0]
    const dx = touch.clientX - touchStart.current.x
    const dy = touch.clientY - touchStart.current.y

    touchStart.current = null

    const absDx = Math.abs(dx)
    const absDy = Math.abs(dy)

    // Must travel the minimum distance horizontally, and the gesture must be
    // more horizontal than vertical.
    if (absDx < MIN_SWIPE_DISTANCE) return
    if (absDy / absDx > MAX_VERTICAL_RATIO) return

    const idx = LANE_KEYS.indexOf(activeMobileLane)

    if (dx < 0) {
      // Swipe left → next lane
      const next = idx + 1
      if (next < LANE_KEYS.length) setActiveMobileLane(LANE_KEYS[next])
    } else {
      // Swipe right → previous lane
      const prev = idx - 1
      if (prev >= 0) setActiveMobileLane(LANE_KEYS[prev])
    }
  }

  return { onTouchStart, onTouchEnd }
}
