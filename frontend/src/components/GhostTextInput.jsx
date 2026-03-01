import { useState, useRef, useCallback, forwardRef, useImperativeHandle } from 'react'

/**
 * GhostTextInput — wraps a text <input> with inline ghost-text autocomplete.
 *
 * On desktop (>= md / 768 px) it fetches up to 5 suggestions from
 * /api/autocomplete/name for the token currently being typed at the cursor,
 * then renders the suffix as a semi-transparent overlay so it looks like an
 * inline hint.  Pressing Tab accepts the suggestion.
 *
 * ArrowDown/ArrowUp cycle through alternative suggestions when multiple are
 * available. The cycle wraps around.
 *
 * On mobile (< md) the overlay is hidden via Tailwind's `hidden md:flex`.
 */
const GhostTextInput = forwardRef(function GhostTextInput(
  { value, onChange, className, onKeyDown, ...props },
  ref
) {
  const [suggestions, setSuggestions] = useState([])
  const [suggestionIndex, setSuggestionIndex] = useState(0)
  const [tokenLength, setTokenLength] = useState(0)
  const inputRef = useRef(null)
  const abortRef = useRef(null)

  // Forward the ref to the underlying input element
  useImperativeHandle(ref, () => inputRef.current)

  // Derive ghost suffix from the active suggestion
  const activeSuggestion = suggestions[suggestionIndex] ?? ''
  const ghostSuffix = activeSuggestion ? activeSuggestion.slice(tokenLength) : ''

  // Fetch autocomplete suggestions for a given token prefix
  const fetchSuggestion = useCallback(async (token) => {
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()
    try {
      const res = await fetch(
        `/api/autocomplete/name?prefix=${encodeURIComponent(token)}`,
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
            if (inputRef.current) {
              inputRef.current.setSelectionRange(newValue.length, newValue.length)
            }
          })
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSuggestionIndex(i => (i + 1) % suggestions.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSuggestionIndex(i => (i - 1 + suggestions.length) % suggestions.length)
      } else if (e.key === 'Escape') {
        e.preventDefault()
        setSuggestions([])
        setSuggestionIndex(0)
        setTokenLength(0)
      }
    }
    onKeyDown?.(e)
  }

  const handleBlur = () => {
    setSuggestions([])
    setSuggestionIndex(0)
    setTokenLength(0)
  }

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
