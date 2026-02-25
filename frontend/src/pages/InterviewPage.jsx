import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SurveyCard from '../components/SurveyCard'

/**
 * Spinner — matches the border-based animate-spin used in KanbanBoard and SettingsPanel.
 */
function Spinner({ size = 8, colorClass = 'border-primary', testId }) {
  return (
    <div
      className={`w-${size} h-${size} border-4 ${colorClass} border-t-transparent rounded-full animate-spin`}
      data-testid={testId}
      aria-label="Loading"
    />
  )
}

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
 *
 * Status machine:
 *   waiting      → SSE connected, no question yet
 *   active       → question received, waiting for user answer
 *   answered     → answer submitted, waiting for server ACK + next question
 *   reconnecting → SSE connection dropped, auto-reconnecting
 *   ended        → session terminated by server
 *   error        → unrecoverable error (bad data, POST failure)
 */
function InterviewPage() {
  const navigate = useNavigate()
  const [question, setQuestion] = useState(null) // { text, options }
  const [status, setStatus] = useState('waiting')
  const [errorMsg, setErrorMsg] = useState('')
  const [featuresCreated, setFeaturesCreated] = useState(0)
  const [sessionKey, setSessionKey] = useState(0) // increment to reconnect SSE

  // Set page title on mount, restore on unmount
  useEffect(() => {
    const previous = document.title
    document.title = 'Feature Interview | Feature Dashboard'
    return () => { document.title = previous }
  }, [])

  useEffect(() => {
    const src = new EventSource('/api/interview/question/stream')

    // After 3 s with no question, transition waiting → idle so the user
    // sees instructions instead of a plain spinner.
    const idleTimer = setTimeout(() => {
      setStatus((prev) => (prev === 'waiting' ? 'idle' : prev))
    }, 3000)

    src.onopen = () => {
      // On (re)open: if we were reconnecting, return to waiting state
      setStatus((prev) => (prev === 'reconnecting' ? 'waiting' : prev))
    }

    src.addEventListener('question', (e) => {
      clearTimeout(idleTimer)
      try {
        const data = JSON.parse(e.data)
        setQuestion({ text: data.text, options: data.options })
        setStatus('active')
      } catch {
        setErrorMsg('Received malformed question data.')
        setStatus('error')
      }
    })

    src.addEventListener('session-timeout', () => {
      clearTimeout(idleTimer)
      setStatus('timedout')
      src.close()
    })

    src.addEventListener('end', (e) => {
      try {
        const data = JSON.parse(e.data || '{}')
        setFeaturesCreated(data.features_created ?? 0)
      } catch {
        setFeaturesCreated(0)
      }
      setStatus('ended')
      src.close()
    })

    // heartbeat — keep-alive, no action needed
    src.addEventListener('heartbeat', () => {})

    src.onerror = () => {
      // EventSource reconnects automatically — show transient "Reconnecting…" state.
      // Do not interrupt an active question (user still needs to answer it), and
      // do not overwrite terminal states (ended / error).
      setStatus((prev) => {
        if (prev === 'active' || prev === 'ended' || prev === 'error') return prev
        return 'reconnecting'
      })
    }

    return () => {
      clearTimeout(idleTimer)
      src.close()
    }
  }, [sessionKey])

  const handleAnswer = async (answer) => {
    setStatus('answered')
    try {
      await fetch('/api/interview/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: answer }),
      })
      // Answer ACKed — wait for the next question via SSE
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

          {/* Waiting for first / next question */}
          {status === 'waiting' && (
            <div
              className="flex flex-col items-center gap-4 text-center"
              data-testid="interview-waiting"
            >
              <Spinner testId="interview-spinner" />
              <p className="text-text-secondary text-base">
                Waiting for next question…
              </p>
            </div>
          )}

          {/* No active session — waiting for Claude to start */}
          {status === 'idle' && (
            <div
              className="flex flex-col items-center gap-4 text-center px-2"
              data-testid="interview-idle"
            >
              <p className="text-text-primary text-base font-semibold">
                Waiting for Claude to start an interview...
              </p>
              <p className="text-text-secondary text-sm leading-relaxed">
                Run the <span className="font-mono text-primary">/interview-feature</span> skill in Claude Code on your PC to begin
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

          {/* Answer submitted — waiting for server ACK + next question */}
          {status === 'answered' && (
            <div
              className="flex flex-col items-center gap-4 text-center"
              data-testid="interview-answered"
            >
              <Spinner testId="interview-spinner" />
              <p className="text-text-secondary text-base">
                Waiting for next question…
              </p>
            </div>
          )}

          {/* SSE dropped — auto-reconnecting */}
          {status === 'reconnecting' && (
            <div
              className="flex flex-col items-center gap-4 text-center"
              data-testid="interview-reconnecting"
            >
              <Spinner colorClass="border-warning" testId="interview-spinner" />
              <p className="text-warning text-base font-medium">
                Reconnecting…
              </p>
            </div>
          )}

          {/* Session timed out */}
          {status === 'timedout' && (
            <div
              className="flex flex-col items-center gap-6 text-center"
              data-testid="interview-timedout"
            >
              <div>
                <h2 className="text-xl font-bold text-text-primary mb-2">
                  Session timed out
                </h2>
                <p className="text-text-secondary text-base">
                  No answer received — the session has expired.
                </p>
              </div>
              <button
                onClick={() => {
                  setStatus('waiting')
                  setQuestion(null)
                  setFeaturesCreated(0)
                  setSessionKey((k) => k + 1)
                }}
                className="px-6 py-3 rounded-lg border border-border text-text-secondary text-sm font-mono font-semibold hover:border-text-secondary hover:text-text-primary transition-colors"
                data-testid="interview-new-session-btn"
              >
                Start New Interview
              </button>
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
                <p
                  className="text-text-secondary text-base"
                  data-testid="interview-features-count"
                >
                  {featuresCreated} feature{featuresCreated !== 1 ? 's' : ''} created
                </p>
              </div>
              <div className="flex flex-col gap-3 w-full max-w-xs">
                <button
                  onClick={() => navigate('/')}
                  className="px-6 py-3 rounded-lg bg-primary text-white text-sm font-mono font-semibold hover:opacity-80 transition-opacity"
                  data-testid="interview-view-board-btn"
                >
                  View Board
                </button>
                <button
                  onClick={() => {
                    setStatus('waiting')
                    setQuestion(null)
                    setFeaturesCreated(0)
                    setSessionKey((k) => k + 1)
                  }}
                  className="px-6 py-3 rounded-lg border border-border text-text-secondary text-sm font-mono font-semibold hover:border-text-secondary hover:text-text-primary transition-colors"
                  data-testid="interview-new-session-btn"
                >
                  Start New Interview
                </button>
              </div>
            </div>
          )}

          {/* Unrecoverable error */}
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
