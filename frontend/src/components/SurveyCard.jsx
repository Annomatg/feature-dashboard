import { useState, useRef, useEffect } from 'react'

/**
 * SurveyCard — interview UI component.
 *
 * Props:
 *   question    { text: string, options: string[] }
 *   onAnswer    (answer: string) => void   called once when the user commits an answer
 *   accentColor string (optional, defaults to primary blue)
 */
function SurveyCard({ question, onAnswer, accentColor = '#3b82f6' }) {
  const [selected, setSelected] = useState(null)
  const [submitted, setSubmitted] = useState(false)
  const [otherText, setOtherText] = useState('')
  const otherInputRef = useRef(null)

  // Auto-focus the Other input when it becomes visible
  useEffect(() => {
    if (selected === '__other__' && otherInputRef.current) {
      otherInputRef.current.focus()
    }
  }, [selected])

  const handleSelect = (option) => {
    if (submitted) return
    setSelected(option)

    // Non-Other options submit immediately
    if (option !== '__other__') {
      setSubmitted(true)
      onAnswer?.(option)
    }
  }

  const handleOtherSubmit = () => {
    const value = otherText.trim()
    if (!value || submitted) return
    setSubmitted(true)
    onAnswer?.(value)
  }

  const handleOtherKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleOtherSubmit()
    }
  }

  const options = question?.options ?? []

  return (
    <div
      className="w-full max-w-2xl mx-auto"
      data-testid="survey-card"
    >
      {/* Question heading */}
      <h2
        className="text-xl font-semibold text-text-primary mb-6 leading-snug"
        data-testid="survey-question"
      >
        {question?.text}
      </h2>

      {/* Option cards */}
      <div className="flex flex-col gap-3" role="group" aria-label="Answer options">
        {options.map((option, index) => {
          const isSelected = selected === option
          const isDisabled = submitted && !isSelected

          return (
            <button
              key={index}
              onClick={() => handleSelect(option)}
              disabled={isDisabled}
              aria-pressed={isSelected}
              data-testid={`survey-option-${index}`}
              className="w-full text-left rounded-lg border px-5 py-4 text-sm font-medium transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-background disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                minHeight: '56px',
                borderColor: isSelected ? accentColor : '#3d3d3d',
                backgroundColor: isSelected ? `${accentColor}18` : '#2d2d2d',
                color: isSelected ? '#ffffff' : '#a3a3a3',
                boxShadow: isSelected
                  ? `0 0 0 2px ${accentColor}60`
                  : 'none',
                focusRingColor: accentColor,
              }}
              onMouseEnter={(e) => {
                if (!isDisabled && !isSelected) {
                  e.currentTarget.style.borderColor = `${accentColor}60`
                  e.currentTarget.style.color = '#ffffff'
                  e.currentTarget.style.backgroundColor = `${accentColor}0a`
                }
              }}
              onMouseLeave={(e) => {
                if (!isDisabled && !isSelected) {
                  e.currentTarget.style.borderColor = '#3d3d3d'
                  e.currentTarget.style.color = '#a3a3a3'
                  e.currentTarget.style.backgroundColor = '#2d2d2d'
                }
              }}
            >
              {option}
            </button>
          )
        })}

        {/* Other option */}
        {(() => {
          const isOtherSelected = selected === '__other__'
          const isOtherDisabled = submitted && !isOtherSelected

          return (
            <div className="flex flex-col gap-2">
              <button
                onClick={() => handleSelect('__other__')}
                disabled={isOtherDisabled}
                aria-pressed={isOtherSelected}
                data-testid="survey-option-other"
                className="w-full text-left rounded-lg border px-5 py-4 text-sm font-medium transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-background disabled:opacity-40 disabled:cursor-not-allowed"
                style={{
                  minHeight: '56px',
                  borderColor: isOtherSelected ? accentColor : '#3d3d3d',
                  backgroundColor: isOtherSelected ? `${accentColor}18` : '#2d2d2d',
                  color: isOtherSelected ? '#ffffff' : '#a3a3a3',
                  boxShadow: isOtherSelected ? `0 0 0 2px ${accentColor}60` : 'none',
                }}
                onMouseEnter={(e) => {
                  if (!isOtherDisabled && !isOtherSelected) {
                    e.currentTarget.style.borderColor = `${accentColor}60`
                    e.currentTarget.style.color = '#ffffff'
                    e.currentTarget.style.backgroundColor = `${accentColor}0a`
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isOtherDisabled && !isOtherSelected) {
                    e.currentTarget.style.borderColor = '#3d3d3d'
                    e.currentTarget.style.color = '#a3a3a3'
                    e.currentTarget.style.backgroundColor = '#2d2d2d'
                  }
                }}
              >
                Other…
              </button>

              {/* Free-text input revealed when Other is selected */}
              {isOtherSelected && (
                <div className="flex gap-2 mt-1 animate-slide-in" data-testid="other-input-container">
                  <input
                    ref={otherInputRef}
                    type="text"
                    value={otherText}
                    onChange={(e) => setOtherText(e.target.value)}
                    onKeyDown={handleOtherKeyDown}
                    placeholder="Type your answer…"
                    disabled={submitted}
                    data-testid="other-text-input"
                    className="flex-1 bg-background border border-border rounded px-4 py-3 text-sm text-text-primary placeholder-text-secondary focus:outline-none transition-colors disabled:opacity-40"
                    style={{
                      borderColor: '#3d3d3d',
                    }}
                    onFocus={(e) => { e.target.style.borderColor = accentColor }}
                    onBlur={(e) => { e.target.style.borderColor = '#3d3d3d' }}
                  />
                  <button
                    onClick={handleOtherSubmit}
                    disabled={!otherText.trim() || submitted}
                    data-testid="other-submit-btn"
                    className="px-5 py-3 rounded text-sm font-semibold font-mono transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{
                      backgroundColor: otherText.trim() && !submitted ? accentColor : '#3d3d3d',
                      color: otherText.trim() && !submitted ? '#000' : '#666',
                      border: `1px solid ${otherText.trim() && !submitted ? accentColor : '#3d3d3d'}`,
                    }}
                  >
                    Submit
                  </button>
                </div>
              )}
            </div>
          )
        })()}
      </div>
    </div>
  )
}

export default SurveyCard
