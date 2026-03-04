import { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from 'react'

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
 * On mobile (< md) the ghost overlay is hidden via Tailwind's `hidden md:block`,
 * and instead a horizontal chip list (data-testid="description-suggestion-list")
 * is rendered below the textarea.  Tapping a chip accepts the suggestion.
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
  const blurTimerRef = useRef(null)

  // Cancel blur timer on unmount to avoid state-update-after-unmount
  useEffect(() => {
    return () => {
      if (blurTimerRef.current) clearTimeout(blurTimerRef.current)
    }
  }, [])

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
      if (!res.ok) {
        // Treat HTTP errors (4xx, 5xx) as failures - show no suggestions
        setSuggestions([])
        setSuggestionIndex(0)
        setTokenLength(0)
        return
      }
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

    // Cancel any pending blur-clear so new suggestions can appear
    if (blurTimerRef.current) {
      clearTimeout(blurTimerRef.current)
      blurTimerRef.current = null
    }

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
      } else if (e.key === 'Escape') {
        e.preventDefault()
        setSuggestions([])
        setSuggestionIndex(0)
        setTokenLength(0)
      } else if (e.key === 'Enter') {
        // Enter should dismiss suggestions but allow normal form submission
        setSuggestions([])
        setSuggestionIndex(0)
        setTokenLength(0)
      }
    }
    onKeyDown?.(e)
  }

  const handleBlur = (e) => {
    // On mobile the chip list needs time to receive a tap before we clear
    // suggestions — use a short delay so the click handler can fire first.
    // On desktop the list is hidden (md:hidden) so the delay is harmless.
    blurTimerRef.current = setTimeout(() => {
      setSuggestions([])
      setSuggestionIndex(0)
      setTokenLength(0)
      blurTimerRef.current = null
      onBlur?.(e)
    }, 200)
  }

  // Accept a suggestion from the mobile chip list
  const handleSuggestionClick = (suggestion) => {
    // Cancel the blur timer so suggestions aren't cleared before we apply
    if (blurTimerRef.current) {
      clearTimeout(blurTimerRef.current)
      blurTimerRef.current = null
    }
    const suffix = suggestion.slice(tokenLength)
    const newValue = value + suffix
    onChange({ target: { value: newValue } })
    setSuggestions([])
    setSuggestionIndex(0)
    setTokenLength(0)
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.setSelectionRange(newValue.length, newValue.length)
        textareaRef.current.focus()
      }
    })
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
          <span className="text-gray-500 select-none">{ghostSuffix}</span>
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
      {/* Mobile suggestion chips — hidden on desktop via md:hidden */}
      {suggestions.length > 0 && (
        <div
          data-testid="description-suggestion-list"
          className="flex flex-wrap gap-1.5 mt-2 p-2 bg-surface border border-border rounded shadow-lg md:hidden"
          role="listbox"
          aria-label="Description suggestions"
        >
          {suggestions.slice(0, 5).map((suggestion, i) => (
            <button
              key={suggestion}
              type="button"
              role="option"
              aria-selected={i === suggestionIndex}
              className={`px-2.5 py-1.5 text-xs font-mono rounded border transition-colors ${
                i === suggestionIndex
                  ? 'bg-primary text-black border-primary'
                  : 'bg-background border-border text-text-secondary hover:text-text-primary hover:border-primary/50'
              }`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => handleSuggestionClick(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
    </div>
  )
})

export default GhostTextArea
