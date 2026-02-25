import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Navigate to /interview and wait for the page shell to mount. */
async function gotoInterview(page) {
  await page.goto('/interview')
  await page.waitForSelector('[data-testid="interview-page"]', { timeout: 10000 })
}

/** Mock the SSE stream to immediately send a session-timeout event. */
async function mockSessionTimeout(page) {
  await page.route('**/api/interview/question/stream', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      headers: { 'Cache-Control': 'no-cache', 'Connection': 'keep-alive' },
      body: 'event: session-timeout\ndata: {}\n\n',
    })
  })
}

// ---------------------------------------------------------------------------
// Timeout screen — appearance
// ---------------------------------------------------------------------------

test.describe('InterviewPage — session timeout', () => {
  test('shows timeout screen when SSE sends session-timeout event', async ({ page }) => {
    await mockSessionTimeout(page)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-timedout')).toBeVisible({ timeout: 5000 })
  })

  test('timeout heading reads "Session timed out"', async ({ page }) => {
    await mockSessionTimeout(page)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-timedout')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('interview-timedout')).toContainText('Session timed out')
  })

  test('timeout screen shows "no answer received" message', async ({ page }) => {
    await mockSessionTimeout(page)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-timedout')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('interview-timedout')).toContainText('No answer received')
  })

  test('timeout screen shows "Start New Interview" button', async ({ page }) => {
    await mockSessionTimeout(page)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-timedout')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('interview-new-session-btn')).toBeVisible()
    await expect(page.getByTestId('interview-new-session-btn')).toContainText('Start New Interview')
  })

  test('timeout screen does NOT show survey card', async ({ page }) => {
    await mockSessionTimeout(page)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-timedout')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('survey-card')).not.toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// "Start New Interview" recovery from timeout
// ---------------------------------------------------------------------------

test.describe('InterviewPage — recover from timeout', () => {
  test('"Start New Interview" replaces timeout screen with waiting state', async ({ page }) => {
    // First call: timeout event; second call (after reset): stall
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream; charset=utf-8',
          headers: { 'Cache-Control': 'no-cache' },
          body: 'event: session-timeout\ndata: {}\n\n',
        })
      }
      // Subsequent calls: stall — simulates waiting for next session
    })

    await gotoInterview(page)
    await expect(page.getByTestId('interview-timedout')).toBeVisible({ timeout: 5000 })

    await page.getByTestId('interview-new-session-btn').click()

    await expect(page.getByTestId('interview-timedout')).not.toBeVisible()
    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 5000 })
  })

  test('a new question after recovery shows the survey card', async ({ page }) => {
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream; charset=utf-8',
          headers: { 'Cache-Control': 'no-cache' },
          body: 'event: session-timeout\ndata: {}\n\n',
        })
      } else {
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream; charset=utf-8',
          headers: { 'Cache-Control': 'no-cache' },
          body: 'event: question\ndata: {"text":"Post-timeout question","options":["A","B"]}\n\n',
        })
      }
    })
    await page.route('**/api/interview/answer', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"received"}' })
    })

    await gotoInterview(page)
    await expect(page.getByTestId('interview-timedout')).toBeVisible({ timeout: 5000 })

    await page.getByTestId('interview-new-session-btn').click()

    await expect(page.getByTestId('survey-card')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('survey-question')).toContainText('Post-timeout question')
  })
})

// ---------------------------------------------------------------------------
// Mobile readability — 390px
// ---------------------------------------------------------------------------

test.describe('InterviewPage — timeout screen mobile', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('timeout screen is visible within viewport at 390×844', async ({ page }) => {
    await mockSessionTimeout(page)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-timedout')).toBeVisible({ timeout: 5000 })
    const box = await page.getByTestId('interview-timedout').boundingBox()
    expect(box).not.toBeNull()
    expect(box.y + box.height).toBeLessThanOrEqual(844)
  })

  test('no horizontal scroll on timeout screen at 390px', async ({ page }) => {
    await mockSessionTimeout(page)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-timedout')).toBeVisible({ timeout: 5000 })
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth)
    expect(scrollWidth).toBeLessThanOrEqual(390)
  })
})
