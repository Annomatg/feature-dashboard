import { useState, useRef, useCallback, forwardRef, useImperativeHandle } from 'react'

/**
 * GhostTextInput — wraps a text <input> with inline ghost-text autocomplete.
 *
 * On desktop (>= md / 768 px) it fetches the top suggestion from
 * /api/autocomplete/name for the token currently being typed at the cursor,
 * then renders the suffix as a semi-transparent overlay so it looks like an
 * inline hint.  Pressing Tab accepts the suggestion.
 *
 * On mobile (< md) the overlay is hidden via Tailwind's `hidden md:flex`.
 */
const GhostTextInput = forwardRef(function GhostTextInput(
  { value, onChange, className, onKeyDown, ...props },
  ref
) {
  const [ghostSuffix, setGhostSuffix] = useState('')
  const inputRef = useRef(null)
  const abortRef = useRef(null)

  // Forward the ref to the underlying input element
  useImperativeHandle(ref, () => inputRef.current)

  // Fetch the top autocomplete suggestion for a given token prefix
  const fetchSuggestion = useCallback(async (token) => {
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()
    try {
      const res = await fetch(
        `/api/autocomplete/name?prefix=${encodeURIComponent(token)}`,
        { signal: abortRef.current.signal }
      )
      const data = await res.json()
      if (data.suggestions?.length > 0) {
        const top = data.suggestions[0]
        if (top.toLowerCase().startsWith(token.toLowerCase())) {
          setGhostSuffix(top.slice(token.length))
          return
        }
      }
      setGhostSuffix('')
    } catch (e) {
      if (e.name !== 'AbortError') setGhostSuffix('')
    }
  }, [])

  const handleChange = (e) => {
    const newValue = e.target.value
    const cursorPos = e.target.selectionStart
    onChange(e)
    setGhostSuffix('')

    // Extract the token immediately before the cursor (last non-whitespace run)
    const textBeforeCursor = newValue.slice(0, cursorPos)
    const match = textBeforeCursor.match(/\S+$/)
    const token = match ? match[0] : ''

    if (token.length >= 3) {
      fetchSuggestion(token)
    }
  }

  const handleKeyDown = (e) => {
    if (ghostSuffix && e.key === 'Tab') {
      e.preventDefault()
      const newValue = value + ghostSuffix
      onChange({ target: { value: newValue } })
      setGhostSuffix('')
      // Position cursor after the inserted token once React has re-rendered
      requestAnimationFrame(() => {
        if (inputRef.current) {
          inputRef.current.setSelectionRange(newValue.length, newValue.length)
        }
      })
    }
    onKeyDown?.(e)
  }

  const handleBlur = () => setGhostSuffix('')

  // Only show ghost text when cursor is at the very end of the value
  const cursorAtEnd =
    !inputRef.current || inputRef.current.selectionStart === value.length
  const showGhost = Boolean(ghostSuffix && cursorAtEnd)

  return (
    <div className="relative">
      {showGhost && (
        <div
          aria-hidden="true"
          data-testid="name-ghost-text"
          className="hidden md:flex absolute inset-0 px-3 py-2 text-sm pointer-events-none items-center overflow-hidden"
        >
          {/* Transparent span positions the ghost suffix after the typed text */}
          <span className="text-transparent whitespace-pre select-none">{value}</span>
          <span className="text-text-secondary opacity-40 whitespace-pre select-none">{ghostSuffix}</span>
        </div>
      )}
      <input
        ref={inputRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        className={className}
        {...props}
      />
    </div>
  )
})

export default GhostTextInput
