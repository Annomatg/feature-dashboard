import { useState, useRef, useCallback, forwardRef, useImperativeHandle } from 'react'

/**
 * GhostTextArea — wraps a <textarea> with inline ghost-text autocomplete.
 *
 * On desktop (>= md / 768 px) it fetches up to 5 suggestions from
 * /api/autocomplete/description for the token currently being typed at the
 * cursor, then renders the suffix as a semi-transparent overlay so it looks
 * like an inline hint.  Pressing Tab accepts the suggestion.
 *
 * ArrowDown/ArrowUp cycle through alternative suggestions when multiple are
 * available. The cycle wraps around.
 *
 * On mobile (< md) the overlay is hidden via Tailwind's `hidden md:block`.
 */
const GhostTextArea = forwardRef(function GhostTextArea(
  { value, onChange, className, onKeyDown, onBlur, rows = 4, ...props },
  ref
) {
  const [suggestions, setSuggestions] = useState([])
  const [suggestionIndex, setSuggestionIndex] = useState(0)
  const [tokenLength, setTokenLength] = useState(0)
  const textareaRef = useRef(null)
  const abortRef = useRef(null)

  // Forward the ref to the underlying textarea element
  useImperativeHandle(ref, () => textareaRef.current)

  // Derive ghost suffix from the active suggestion
  const activeSuggestion = suggestions[suggestionIndex] ?? ''
  const ghostSuffix = activeSuggestion ? activeSuggestion.slice(tokenLength) : ''

  // Fetch autocomplete suggestions for a given token prefix
  const fetchSuggestion = useCallback(async (token) => {
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()
    try {
      const res = await fetch(
        `/api/autocomplete/description?prefix=${encodeURIComponent(token)}`,
        { signal: abortRef.current.signal }
      )
      const data = await res.json()
      const valid = (data.suggestions ?? []).filter(s =>
        s.toLowerCase().startsWith(token.toLowerCase())
      )
      setSuggestions(valid)
      setSuggestionIndex(0)
      setTokenLength(token.length)
    } catch (e) {
      if (e.name !== 'AbortError') {
        setSuggestions([])
        setSuggestionIndex(0)
        setTokenLength(0)
      }
    }
  }, [])

  const handleChange = (e) => {
    const newValue = e.target.value
    const cursorPos = e.target.selectionStart
    onChange(e)
    setSuggestions([])
    setSuggestionIndex(0)
    setTokenLength(0)

    // Extract the token immediately before the cursor (last non-whitespace run)
    const textBeforeCursor = newValue.slice(0, cursorPos)
    const match = textBeforeCursor.match(/\S+$/)
    const token = match ? match[0] : ''

    if (token.length >= 3) {
      fetchSuggestion(token)
    }
  }

  const handleKeyDown = (e) => {
    if (suggestions.length > 0) {
      if (e.key === 'Tab') {
        e.preventDefault()
        const chosen = suggestions[suggestionIndex]
        if (chosen) {
          const newValue = value + ghostSuffix
          onChange({ target: { value: newValue } })
          setSuggestions([])
          setSuggestionIndex(0)
          setTokenLength(0)
          // Position cursor after the inserted token once React has re-rendered
          requestAnimationFrame(() => {
            if (textareaRef.current) {
              textareaRef.current.setSelectionRange(newValue.length, newValue.length)
            }
          })
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSuggestionIndex(i => (i + 1) % suggestions.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSuggestionIndex(i => (i - 1 + suggestions.length) % suggestions.length)
      }
    }
    onKeyDown?.(e)
  }

  const handleBlur = (e) => {
    setSuggestions([])
    setSuggestionIndex(0)
    setTokenLength(0)
    onBlur?.(e)
  }

  // Only show ghost text when cursor is at the very end of the value
  const cursorAtEnd =
    !textareaRef.current || textareaRef.current.selectionStart === value.length
  const showGhost = Boolean(ghostSuffix && cursorAtEnd)

  return (
    <div className="relative">
      {showGhost && (
        <div
          aria-hidden="true"
          data-testid="description-ghost-text"
          className="hidden md:block absolute inset-0 pointer-events-none overflow-hidden text-sm"
          style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
        >
          {/* Transparent span positions the ghost suffix after the typed text */}
          <span className="text-transparent select-none">{value}</span>
          <span className="text-text-secondary opacity-40 select-none">{ghostSuffix}</span>
        </div>
      )}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        className={className}
        rows={rows}
        {...props}
      />
    </div>
  )
})

export default GhostTextArea
