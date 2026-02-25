import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Navigate to /interview and wait for the page shell to mount. */
async function gotoInterview(page) {
  await page.goto('/interview')
  await page.waitForSelector('[data-testid="interview-page"]', { timeout: 10000 })
}

/** Fulfill the SSE route with an event string body. */
function fulfillSSE(route, body) {
  route.fulfill({
    status: 200,
    contentType: 'text/event-stream; charset=utf-8',
    headers: { 'Cache-Control': 'no-cache', 'Connection': 'keep-alive' },
    body,
  })
}

// ---------------------------------------------------------------------------
// Waiting state — shown on initial load and after answer submission
// ---------------------------------------------------------------------------

test.describe('InterviewPage — waiting state', () => {
  test('shows a spinner and "Waiting for next question…" on initial load (no question yet)', async ({ page }) => {
    // Never fulfill — simulates server waiting to send a question
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('interview-spinner')).toBeVisible()
    await expect(page.getByText('Waiting for next question…')).toBeVisible()
  })

  test('spinner element uses the border-based animate-spin class', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await page.waitForSelector('[data-testid="interview-spinner"]', { timeout: 5000 })
    const spinnerClass = await page.getByTestId('interview-spinner').getAttribute('class')
    expect(spinnerClass).toContain('animate-spin')
    expect(spinnerClass).toContain('rounded-full')
    expect(spinnerClass).toContain('border-t-transparent')
  })

  test('waiting state does NOT show a progress percentage', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 5000 })
    // No percentage text — look for any % symbol in the waiting container
    const text = await page.getByTestId('interview-waiting').textContent()
    expect(text).not.toMatch(/%/)
  })

  test('waiting state replaces the SurveyCard immediately when a question arrives', async ({ page }) => {
    await page.route('**/api/interview/question/stream', (route) => {
      fulfillSSE(route,
        'event: question\n' +
        'data: {"text":"Pick one","options":["A","B"]}\n\n'
      )
    })
    await gotoInterview(page)

    // Waiting should disappear once the question event is processed
    await expect(page.getByTestId('survey-card')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('interview-waiting')).not.toBeVisible()
  })

  test('answered state shows spinner + "Waiting for next question…" (no SurveyCard)', async ({ page }) => {
    // Push one question, then accept the answer POST
    await page.route('**/api/interview/question/stream', (route) => {
      fulfillSSE(route,
        'event: question\n' +
        'data: {"text":"Pick one","options":["A","B"]}\n\n'
      )
    })

    // Hold the answer POST indefinitely so we can inspect the answered state
    let resolveAnswer
    const answerHeld = new Promise((res) => { resolveAnswer = res })
    await page.route('**/api/interview/answer', async (route) => {
      await answerHeld // wait until we release it
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"received"}' })
    })

    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })

    // Select an answer
    await page.getByTestId('survey-option-0').click()

    // Answered state should be visible while POST is held
    await expect(page.getByTestId('interview-answered')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('interview-spinner')).toBeVisible()
    await expect(page.getByText('Waiting for next question…')).toBeVisible()

    // No SurveyCard while waiting
    await expect(page.getByTestId('survey-card')).not.toBeVisible()

    // Release the held POST so cleanup happens
    resolveAnswer()
  })
})

// ---------------------------------------------------------------------------
// Reconnecting state
// ---------------------------------------------------------------------------

test.describe('InterviewPage — reconnecting state', () => {
  test('shows "Reconnecting…" and a warning spinner when SSE connection drops', async ({ page }) => {
    // First request: immediately close without any events (triggers onerror)
    // Subsequent requests: stall (so we stay in reconnecting)
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        // Return an empty 200 with no body — connection closes, triggers onerror
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          headers: { 'Cache-Control': 'no-cache' },
          body: '',
        })
      } else {
        // Stall — don't fulfill so reconnect attempt hangs (keeps reconnecting state)
      }
    })

    await gotoInterview(page)

    await expect(page.getByTestId('interview-reconnecting')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('interview-spinner')).toBeVisible()
    await expect(page.getByText('Reconnecting…')).toBeVisible()
  })

  test('reconnecting spinner uses warning color (border-warning class)', async ({ page }) => {
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          headers: { 'Cache-Control': 'no-cache' },
          body: '',
        })
      }
      // subsequent calls stall
    })

    await gotoInterview(page)
    await page.waitForSelector('[data-testid="interview-reconnecting"]', { timeout: 10000 })

    const spinnerClass = await page.getByTestId('interview-spinner').getAttribute('class')
    expect(spinnerClass).toContain('border-warning')
  })

  test('reconnecting state clears when SSE sends a question after reconnect', async ({ page }) => {
    // First call: empty body → onerror fires in 'waiting' state → 'reconnecting'
    // Second call (auto-reconnect by EventSource): push a real question → 'active'
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          headers: { 'Cache-Control': 'no-cache' },
          body: '',
        })
      } else {
        fulfillSSE(route,
          'event: question\n' +
          'data: {"text":"After reconnect question","options":["Yes","No"]}\n\n'
        )
      }
    })

    await gotoInterview(page)

    // Should eventually show the question (reconnecting clears)
    await expect(page.getByTestId('survey-card')).toBeVisible({ timeout: 15000 })
    await expect(page.getByTestId('interview-reconnecting')).not.toBeVisible()
    await expect(page.getByTestId('survey-question')).toContainText('After reconnect question')
  })

  test('reconnecting state does NOT show a progress percentage', async ({ page }) => {
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        route.fulfill({
          status: 200, contentType: 'text/event-stream',
          headers: { 'Cache-Control': 'no-cache' }, body: '',
        })
      }
    })

    await gotoInterview(page)
    await page.waitForSelector('[data-testid="interview-reconnecting"]', { timeout: 10000 })

    const text = await page.getByTestId('interview-reconnecting').textContent()
    expect(text).not.toMatch(/%/)
  })
})
