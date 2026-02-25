import { useState } from 'react'
import SurveyCard from '../components/SurveyCard'

const SAMPLE_QUESTION = {
  text: 'Which frontend framework do you prefer?',
  options: ['React', 'Vue', 'Svelte', 'Angular'],
}

/**
 * Minimal test page that renders a SurveyCard with sample data.
 * Used exclusively for E2E testing.
 */
function SurveyCardTestPage() {
  const [lastAnswer, setLastAnswer] = useState(null)

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-8">
      <div className="w-full max-w-2xl">
        <SurveyCard
          question={SAMPLE_QUESTION}
          onAnswer={(answer) => setLastAnswer(answer)}
          accentColor="#3b82f6"
        />
        {lastAnswer !== null && (
          <p
            className="mt-8 text-sm text-text-secondary font-mono text-center"
            data-testid="last-answer"
          >
            Answer: {lastAnswer}
          </p>
        )}
      </div>
    </div>
  )
}

export default SurveyCardTestPage
