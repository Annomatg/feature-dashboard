import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Navigate to /interview and wait for the page shell to mount. */
async function gotoInterview(page) {
  await page.goto('/interview')
  await page.waitForSelector('[data-testid="interview-page"]', { timeout: 10000 })
}

// ---------------------------------------------------------------------------
// Idle state — appears after 3 s with no question
// ---------------------------------------------------------------------------

test.describe('InterviewPage — idle state (no active session)', () => {
  test('shows idle state after 3 s when SSE connects but no question arrives', async ({ page }) => {
    // Stall SSE — never send any event
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    // Must appear within 6 s (3 s timer + rendering headroom)
    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })
  })

  test('idle state shows "Plan Features" heading and description textarea', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })
    await expect(page.getByTestId('interview-idle')).toContainText('Plan Features')
    await expect(page.getByTestId('interview-description')).toBeVisible()
  })

  test('idle state shows Start Planning button disabled when textarea is empty', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })
    await expect(page.getByTestId('interview-start-btn')).toBeDisabled()
  })

  test('Start Planning button enables when description is typed', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })
    await page.getByTestId('interview-description').fill('Add user login feature')
    await expect(page.getByTestId('interview-start-btn')).toBeEnabled()
  })

  test('waiting spinner is shown initially (before 3 s idle timer fires)', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    // Check immediately — waiting state should be visible before the 3 s elapses
    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 2000 })
    // Idle state must NOT be visible yet
    await expect(page.getByTestId('interview-idle')).not.toBeVisible()
  })

  test('idle state replaces waiting spinner (spinner is gone when idle shows)', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })
    await expect(page.getByTestId('interview-waiting')).not.toBeVisible()
  })

  test('submitting description calls /api/interview/start and transitions to waiting', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await page.route('**/api/interview/start', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"launched":true}' })
    })
    await gotoInterview(page)

    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })
    await page.getByTestId('interview-description').fill('Add user login feature')
    await page.getByTestId('interview-start-btn').click()

    // Idle disappears; spinner appears
    await expect(page.getByTestId('interview-idle')).not.toBeVisible({ timeout: 3000 })
    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 3000 })
  })

  test('idle form does NOT re-appear after session started (waiting for first question)', async ({ page }) => {
    // SSE never delivers a question — simulates Claude thinking
    await page.route('**/api/interview/question/stream', () => {})
    await page.route('**/api/interview/start', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"launched":true}' })
    })
    await gotoInterview(page)

    // Wait for idle, fill, start
    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })
    await page.getByTestId('interview-description').fill('Add user login feature')
    await page.getByTestId('interview-start-btn').click()

    // Waiting state appears
    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 3000 })

    // Wait well past the 3 s idle timer — idle must NOT reappear
    await page.waitForTimeout(4000)
    await expect(page.getByTestId('interview-idle')).not.toBeVisible()
    await expect(page.getByTestId('interview-waiting')).toBeVisible()
  })

  test('idle form does NOT re-appear while waiting for next question after answer', async ({ page }) => {
    // Strategy: stall the first SSE connection so idle appears, then manually
    // fulfill it with a question after the user starts the session.
    // This verifies that sessionStarted=true prevents idle from re-appearing
    // while the user waits for Claude's follow-up question.
    const sseRoutes = []
    await page.route('**/api/interview/question/stream', (route) => {
      sseRoutes.push(route)
      // Stall all SSE requests — we will fulfill them manually
    })
    await page.route('**/api/interview/answer', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"received"}' })
    })
    await page.route('**/api/interview/start', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"launched":true}' })
    })
    await gotoInterview(page)

    // SSE stalls → idle appears after 3 s
    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })

    // User fills form and starts session (sessionStarted = true internally)
    await page.getByTestId('interview-description').fill('Some feature')
    await page.getByTestId('interview-start-btn').click()
    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 3000 })

    // Deliver a question via the stalled SSE connection
    sseRoutes[0].fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      headers: { 'Cache-Control': 'no-cache' },
      body: 'event: question\ndata: {"text":"What is your goal?","options":["A","B"]}\n\n',
    })

    // Question appears → user answers
    await expect(page.getByTestId('survey-card')).toBeVisible({ timeout: 5000 })
    await page.getByTestId('survey-option-0').click()

    // Now waiting for Claude's next question — wait well past the 3 s idle timer.
    // The idle form must NOT reappear (sessionStarted=true guards against this).
    await page.waitForTimeout(4000)
    await expect(page.getByTestId('interview-idle')).not.toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// SSE stays open — question received during idle triggers transition to active
// ---------------------------------------------------------------------------

test.describe('InterviewPage — idle → active transition', () => {
  test('receiving a question during idle immediately shows the SurveyCard', async ({ page }) => {
    // First call: stall long enough for idle to appear, then fulfill with a question
    let fulfill
    await page.route('**/api/interview/question/stream', (route) => {
      fulfill = route
    })
    // Silently accept answer POSTs
    await page.route('**/api/interview/answer', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"received"}' })
    })

    await gotoInterview(page)

    // Wait for idle
    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })

    // Now deliver a question via the stalled SSE
    fulfill.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      headers: { 'Cache-Control': 'no-cache' },
      body: 'event: question\ndata: {"text":"Which category?","options":["A","B","C"]}\n\n',
    })

    // Idle screen should disappear and the survey card should appear
    await expect(page.getByTestId('survey-card')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('interview-idle')).not.toBeVisible()
    await expect(page.getByTestId('survey-question')).toContainText('Which category?')
  })

  test('a question arriving before 3 s goes straight to active (no idle shown)', async ({ page }) => {
    // Deliver a question immediately — idle timer must be cancelled
    await page.route('**/api/interview/question/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        headers: { 'Cache-Control': 'no-cache' },
        body: 'event: question\ndata: {"text":"Fast question","options":["Yes","No"]}\n\n',
      })
    })
    await page.route('**/api/interview/answer', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"received"}' })
    })

    await gotoInterview(page)

    await expect(page.getByTestId('survey-card')).toBeVisible({ timeout: 5000 })
    // Idle state must never appear
    await expect(page.getByTestId('interview-idle')).not.toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Mobile readability — idle state at 390px
// ---------------------------------------------------------------------------

test.describe('InterviewPage — idle state mobile readability', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('idle state is visible without scrolling at 390×844', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })

    // Both text elements must be in the viewport (no scrolling needed)
    const idle = page.getByTestId('interview-idle')
    const box = await idle.boundingBox()
    expect(box).not.toBeNull()
    // Idle block top must be within the 844px viewport height
    expect(box.y + box.height).toBeLessThanOrEqual(844)
  })

  test('no horizontal scroll in idle state at 390px', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth)
    expect(scrollWidth).toBeLessThanOrEqual(390)
  })
})
