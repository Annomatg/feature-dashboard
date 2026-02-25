import { useState, useEffect } from 'react'
import SurveyCard from '../components/SurveyCard'

/**
 * InterviewPage — /interview
 *
 * Connects to the backend SSE stream and renders questions as SurveyCards.
 * Layout is optimised for comfortable one-handed use at 390px width.
 *
 * SSE events handled:
 *   question  — { text, options[] } — render SurveyCard
 *   end       — session terminated
 *   heartbeat — ignored (keep-alive)
 */
function InterviewPage() {
  const [question, setQuestion] = useState(null) // { text, options }
  // 'waiting' | 'active' | 'answered' | 'ended' | 'error'
  const [status, setStatus] = useState('waiting')
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    const src = new EventSource('/api/interview/question/stream')

    src.addEventListener('question', (e) => {
      try {
        const data = JSON.parse(e.data)
        setQuestion({ text: data.text, options: data.options })
        setStatus('active')
      } catch {
        setErrorMsg('Received malformed question data.')
        setStatus('error')
      }
    })

    src.addEventListener('end', () => {
      setStatus('ended')
      src.close()
    })

    src.addEventListener('heartbeat', () => {
      // keep-alive — no action needed
    })

    src.onerror = () => {
      // EventSource reconnects automatically; only surface an error if we never
      // received a question yet, so the user isn't left staring at a blank page.
      setStatus((prev) => {
        if (prev === 'waiting') {
          setErrorMsg('Connection to server lost. Please refresh the page.')
          return 'error'
        }
        return prev
      })
    }

    return () => src.close()
  }, [])

  const handleAnswer = async (answer) => {
    setStatus('answered')
    try {
      await fetch('/api/interview/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: answer }),
      })
      // Wait for the next question via SSE; reset to waiting state
      setQuestion(null)
      setStatus('waiting')
    } catch {
      setErrorMsg('Failed to submit answer. Please refresh the page.')
      setStatus('error')
    }
  }

  return (
    <div
      className="min-h-screen bg-background flex flex-col overflow-x-hidden"
      data-testid="interview-page"
    >
      {/* Centred content area — grows to fill the viewport */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-8 w-full">
        <div className="w-full max-w-2xl" data-testid="interview-content">

          {/* Waiting for next question */}
          {status === 'waiting' && (
            <div
              className="flex flex-col items-center gap-4 text-center"
              data-testid="interview-waiting"
            >
              {/* Pulsing indicator */}
              <div className="flex gap-1.5">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-2 h-2 rounded-full bg-primary animate-pulse"
                    style={{ animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </div>
              <p className="text-text-secondary text-base">
                Waiting for next question…
              </p>
            </div>
          )}

          {/* Active question */}
          {status === 'active' && question && (
            <SurveyCard
              question={question}
              onAnswer={handleAnswer}
              accentColor="#3b82f6"
            />
          )}

          {/* Submitting answer */}
          {status === 'answered' && (
            <div
              className="flex flex-col items-center gap-4 text-center"
              data-testid="interview-answered"
            >
              <div className="flex gap-1.5">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-2 h-2 rounded-full bg-success animate-pulse"
                    style={{ animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </div>
              <p className="text-text-secondary text-base">
                Answer received — waiting for next question…
              </p>
            </div>
          )}

          {/* Session ended */}
          {status === 'ended' && (
            <div
              className="flex flex-col items-center gap-6 text-center"
              data-testid="interview-ended"
            >
              <div
                className="w-16 h-16 rounded-full flex items-center justify-center text-3xl"
                style={{ backgroundColor: '#22c55e18', border: '2px solid #22c55e60' }}
              >
                ✓
              </div>
              <div>
                <h2 className="text-xl font-bold text-text-primary mb-2">
                  Interview complete
                </h2>
                <p className="text-text-secondary text-base">
                  Your answers have been recorded. You can close this tab.
                </p>
              </div>
            </div>
          )}

          {/* Error state */}
          {status === 'error' && (
            <div
              className="flex flex-col items-center gap-4 text-center"
              data-testid="interview-error"
            >
              <p className="text-error text-base font-medium">{errorMsg}</p>
              <button
                onClick={() => window.location.reload()}
                className="px-6 py-3 rounded-lg border border-error text-error text-sm font-mono font-semibold hover:bg-error hover:text-white transition-colors"
              >
                Refresh
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

export default InterviewPage
