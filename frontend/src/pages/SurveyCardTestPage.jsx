import { useState } from 'react'
import SurveyCard from '../components/SurveyCard'

const QUESTIONS = {
  default: {
    text: 'Which frontend framework do you prefer?',
    options: ['React', 'Vue', 'Svelte', 'Angular'],
  },
  'type-in': {
    text: 'What is the name of this feature?',
    options: ['(type in browser)'],
  },
  'mixed': {
    text: 'Choose a category or describe your own:',
    options: ['Backend', 'Frontend', '(type in browser)'],
  },
  'markdown': {
    text: 'Here are three directions:\n\n1. **Easy deployment** - Roll out this MCP\n2. **Refactoring plan** - Analyze your project\n3. **New code checker** - Check new changes\n\nWhich direction interests you most?',
    options: ['Easy deployment', 'Refactoring plan', 'New code checker'],
  },
}

/**
 * Minimal test page that renders a SurveyCard with sample data.
 * Used exclusively for E2E testing.
 * Query param ?q= selects the question variant (default, type-in, mixed).
 */
function SurveyCardTestPage() {
  const [lastAnswer, setLastAnswer] = useState(null)
  const q = new URLSearchParams(window.location.search).get('q') ?? 'default'
  const question = QUESTIONS[q] ?? QUESTIONS.default

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-8">
      <div className="w-full max-w-2xl">
        <SurveyCard
          question={question}
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
