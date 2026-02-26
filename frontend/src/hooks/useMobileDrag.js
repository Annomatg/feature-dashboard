/**
 * useMobileDrag — touch drag-and-drop for mobile Kanban boards.
 *
 * Behaviour:
 *   1. Long-press (500 ms) on a card activates drag mode.
 *   2. Moving up / down repositions the card within the current lane.
 *   3. Moving to the left or right screen edge for 1 s switches to the
 *      adjacent lane; the timer resets after each switch.
 *   4. Auto-scroll kicks in when the finger is within 80 px of the top or
 *      bottom of the lane's scroll container.
 *   5. Releasing the finger applies the move / reorder.
 *
 * Usage (from KanbanBoard):
 *   const mobileDrag = useMobileDrag({ onMoveToLane, onReorder, activeMobileLane, setActiveMobileLane })
 *   // Pass mobileDrag.startDrag to each KanbanLane → KanbanCard
 *   // Render <MobileDragOverlay> with mobileDrag props
 *   // Pass mobileDrag.insertBeforeId / mobileDrag.dragFeature to each lane
 */

import { useRef, useState } from 'react'

export const LANE_KEYS = ['todo', 'inProgress', 'done']

const EDGE_WIDTH    = 60    // px from left/right screen edge that triggers lane-switch zone
const EDGE_SWITCH_MS = 1000  // ms to hold at edge before switching lane
const SCROLL_ZONE   = 80    // px from top/bottom of scroll container that triggers auto-scroll
const SCROLL_SPEED  = 4     // px scrolled per animation frame

/**
 * Determine where to insert the dragged card.
 * Returns { beforeId: number | null }
 *   - number  → insert before this feature id
 *   - null    → insert after the last card (at the end)
 */
function getInsertPosition(touchY, laneKey, excludeFeatureId) {
  const laneEl = document.querySelector(`[data-lane-key="${laneKey}"]`)
  if (!laneEl) return { beforeId: null }

  const cards = Array.from(laneEl.querySelectorAll('[data-feature-id]'))
    .filter(el => Number(el.dataset.featureId) !== excludeFeatureId)

  for (const card of cards) {
    const rect = card.getBoundingClientRect()
    if (touchY < rect.top + rect.height / 2) {
      return { beforeId: Number(card.dataset.featureId) }
    }
  }

  return { beforeId: null }
}

export function useMobileDrag({ onMoveToLane, onReorder, activeMobileLane, setActiveMobileLane }) {
  // ── React state (drives re-renders / UI) ──────────────────────────────────
  const [isDragging,    setIsDragging]    = useState(false)
  const [dragFeature,   setDragFeature]   = useState(null)
  const [ghostPos,      setGhostPos]      = useState({ x: 0, y: 0 })
  // undefined → no indicator shown; null → at end; number → before that id
  const [insertBeforeId, setInsertBeforeId] = useState(undefined)
  const [edgeSide,      setEdgeSide]      = useState(null) // 'left' | 'right' | null
  const [edgeProgress,  setEdgeProgress]  = useState(0)   // 0–1

  // ── Mutable refs (readable inside event handlers without stale closures) ──
  const stateRef = useRef({
    active:       false,
    feature:      null,
    fromLane:     null,
    insertBefore: undefined,
    edgeSide:     null,
    edgeStartMs:  null,
    activeLane:   activeMobileLane,
    hasMoved:     false, // true only after at least one touchmove fires post-startDrag
  })

  // Keep activeLane ref in sync every render (no useEffect needed)
  stateRef.current.activeLane = activeMobileLane

  // Timer / RAF handles
  const edgeTimerRef   = useRef(null)
  const edgeRafRef     = useRef(null)
  const scrollRafRef   = useRef(null)

  // Stable wrapper refs so we can add/remove the same function from window
  const touchMoveWrapRef = useRef(null)
  const touchEndWrapRef  = useRef(null)

  // ── Helpers ───────────────────────────────────────────────────────────────

  const clearEdgeTimer = () => {
    if (edgeTimerRef.current)  { clearTimeout(edgeTimerRef.current);  edgeTimerRef.current = null }
    if (edgeRafRef.current)    { cancelAnimationFrame(edgeRafRef.current); edgeRafRef.current = null }
    stateRef.current.edgeSide    = null
    stateRef.current.edgeStartMs = null
    setEdgeSide(null)
    setEdgeProgress(0)
  }

  const clearScrollRAF = () => {
    if (scrollRafRef.current) { cancelAnimationFrame(scrollRafRef.current); scrollRafRef.current = null }
  }

  const armEdge = (side) => {
    if (stateRef.current.edgeSide === side) return // already armed

    clearEdgeTimer()
    stateRef.current.edgeSide    = side
    stateRef.current.edgeStartMs = Date.now()
    setEdgeSide(side)

    // Animate progress bar 0 → 1 over EDGE_SWITCH_MS
    const animateProgress = () => {
      if (!stateRef.current.edgeSide) return
      const p = Math.min((Date.now() - stateRef.current.edgeStartMs) / EDGE_SWITCH_MS, 1)
      setEdgeProgress(p)
      if (p < 1) edgeRafRef.current = requestAnimationFrame(animateProgress)
    }
    edgeRafRef.current = requestAnimationFrame(animateProgress)

    edgeTimerRef.current = setTimeout(() => {
      edgeTimerRef.current = null

      const cur  = stateRef.current.activeLane
      const idx  = LANE_KEYS.indexOf(cur)
      const next = side === 'left' ? idx - 1 : idx + 1

      if (next >= 0 && next < LANE_KEYS.length) {
        setActiveMobileLane(LANE_KEYS[next])
      }

      // Reset so the timer can arm again for the next switch
      stateRef.current.edgeSide    = null
      stateRef.current.edgeStartMs = null
      setEdgeSide(null)
      setEdgeProgress(0)
    }, EDGE_SWITCH_MS)
  }

  // ── Global touch handlers (assigned to window while dragging) ─────────────

  const onTouchMove = (e) => {
    if (!stateRef.current.active) return
    e.preventDefault() // prevent page scroll during drag

    const touch = e.touches[0]
    const x = touch.clientX
    const y = touch.clientY

    stateRef.current.hasMoved = true
    setGhostPos({ x, y })

    // Insert indicator
    const lane   = stateRef.current.activeLane
    const insert = getInsertPosition(y, lane, stateRef.current.feature?.id)
    stateRef.current.insertBefore = insert.beforeId
    setInsertBeforeId(insert.beforeId)

    // Edge detection → lane switch
    const vw = window.innerWidth
    if (x < EDGE_WIDTH)         armEdge('left')
    else if (x > vw - EDGE_WIDTH) armEdge('right')
    else                        clearEdgeTimer()

    // Auto-scroll
    clearScrollRAF()
    const laneEl   = document.querySelector(`[data-lane-key="${lane}"]`)
    const scrollEl = laneEl?.querySelector('[data-scroll]')
    if (scrollEl) {
      const rect     = scrollEl.getBoundingClientRect()
      const nearTop  = y < rect.top  + SCROLL_ZONE
      const nearBot  = y > rect.bottom - SCROLL_ZONE

      if (nearTop || nearBot) {
        const doScroll = () => {
          if (!stateRef.current.active) return
          scrollEl.scrollTop += nearTop ? -SCROLL_SPEED : SCROLL_SPEED
          // Re-evaluate insert position after scroll
          const ni = getInsertPosition(y, stateRef.current.activeLane, stateRef.current.feature?.id)
          stateRef.current.insertBefore = ni.beforeId
          setInsertBeforeId(ni.beforeId)
          scrollRafRef.current = requestAnimationFrame(doScroll)
        }
        scrollRafRef.current = requestAnimationFrame(doScroll)
      }
    }
  }

  const onTouchEnd = () => {
    if (!stateRef.current.active) return

    stateRef.current.active = false
    clearEdgeTimer()
    clearScrollRAF()

    // Remove global listeners
    if (touchMoveWrapRef.current) window.removeEventListener('touchmove', touchMoveWrapRef.current)
    if (touchEndWrapRef.current)  {
      window.removeEventListener('touchend',   touchEndWrapRef.current)
      window.removeEventListener('touchcancel', touchEndWrapRef.current)
    }

    const { feature, fromLane, insertBefore, hasMoved } = stateRef.current
    const currentLane = stateRef.current.activeLane

    if (feature && hasMoved) {
      if (fromLane !== currentLane) {
        // Cross-lane → move
        onMoveToLane(feature, currentLane)
      } else {
        // Same lane → reorder
        if (insertBefore !== undefined) {
          if (insertBefore !== null && insertBefore !== feature.id) {
            onReorder(feature, insertBefore, true)  // insert before
          } else if (insertBefore === null) {
            // Insert after the last card
            const laneEl = document.querySelector(`[data-lane-key="${currentLane}"]`)
            const cards  = Array.from(laneEl?.querySelectorAll('[data-feature-id]') || [])
              .filter(el => Number(el.dataset.featureId) !== feature.id)
            const last = cards[cards.length - 1]
            if (last) onReorder(feature, Number(last.dataset.featureId), false)
          }
        }
      }
    }

    // Reset all state
    stateRef.current.feature      = null
    stateRef.current.fromLane     = null
    stateRef.current.insertBefore = undefined
    setIsDragging(false)
    setDragFeature(null)
    setInsertBeforeId(undefined)
    setEdgeSide(null)
    setEdgeProgress(0)
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Called by KanbanCard when a long-press completes.
   * @param {object} feature   - The feature object being dragged
   * @param {string} lane      - The lane key the card lives in
   * @param {number} touchX    - Initial touch clientX
   * @param {number} touchY    - Initial touch clientY
   */
  const startDrag = (feature, lane, touchX, touchY) => {
    stateRef.current.active      = true
    stateRef.current.feature     = feature
    stateRef.current.fromLane    = lane
    stateRef.current.hasMoved    = false
    // activeLane is already synced via stateRef.current.activeLane = activeMobileLane

    // Initial insert position
    const insert = getInsertPosition(touchY, lane, feature.id)
    stateRef.current.insertBefore = insert.beforeId
    setInsertBeforeId(insert.beforeId)

    setIsDragging(true)
    setDragFeature(feature)
    setGhostPos({ x: touchX, y: touchY })

    // Create fresh stable wrappers pointing at the current handlers
    // (using named functions so they can be removed later)
    touchMoveWrapRef.current = (e) => onTouchMove(e)
    touchEndWrapRef.current  = (e) => onTouchEnd(e)

    window.addEventListener('touchmove',   touchMoveWrapRef.current, { passive: false })
    window.addEventListener('touchend',    touchEndWrapRef.current,  { passive: true  })
    window.addEventListener('touchcancel', touchEndWrapRef.current,  { passive: true  })
  }

  return {
    isDragging,
    dragFeature,
    ghostPos,
    /** undefined = hidden; null = after last card; number = before that featureId */
    insertBeforeId,
    edgeSide,
    edgeProgress,
    startDrag,
  }
}
