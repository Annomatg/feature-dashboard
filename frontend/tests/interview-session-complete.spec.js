import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Navigate to /interview and wait for the page shell to mount. */
async function gotoInterview(page) {
  await page.goto('/interview')
  await page.waitForSelector('[data-testid="interview-page"]', { timeout: 10000 })
}

/**
 * Fulfill the SSE route with a session `end` event carrying an optional
 * `features_created` count in the payload.
 */
async function mockEndEvent(page, featuresCreated = 0) {
  await page.route('**/api/interview/question/stream', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      headers: { 'Cache-Control': 'no-cache', 'Connection': 'keep-alive' },
      body: `event: end\ndata: ${JSON.stringify({ features_created: featuresCreated })}\n\n`,
    })
  })
}

// ---------------------------------------------------------------------------
// Completion screen — appearance
// ---------------------------------------------------------------------------

test.describe('InterviewPage — session complete screen', () => {
  test('shows checkmark icon and "Interview complete" heading on end event', async ({ page }) => {
    await mockEndEvent(page, 0)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-ended')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('Interview complete')).toBeVisible()
    // Checkmark is rendered as ✓ text inside the circle div
    await expect(page.getByTestId('interview-ended')).toContainText('✓')
  })

  test('shows correct feature count from end event payload (plural)', async ({ page }) => {
    await mockEndEvent(page, 3)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-features-count')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('interview-features-count')).toContainText('3 features created')
  })

  test('shows singular "feature" when count is 1', async ({ page }) => {
    await mockEndEvent(page, 1)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-features-count')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('interview-features-count')).toContainText('1 feature created')
  })

  test('shows 0 features when end event payload has no count', async ({ page }) => {
    // Legacy payload with empty data object
    await page.route('**/api/interview/question/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        headers: { 'Cache-Control': 'no-cache' },
        body: 'event: end\ndata: {}\n\n',
      })
    })
    await gotoInterview(page)

    await expect(page.getByTestId('interview-features-count')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('interview-features-count')).toContainText('0 features created')
  })

  test('shows "View Board" button on completion screen', async ({ page }) => {
    await mockEndEvent(page, 2)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-view-board-btn')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('interview-view-board-btn')).toContainText('View Board')
  })

  test('shows "Start New Interview" button on completion screen', async ({ page }) => {
    await mockEndEvent(page, 2)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-new-session-btn')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('interview-new-session-btn')).toContainText('Start New Interview')
  })
})

// ---------------------------------------------------------------------------
// Navigation — "View Board" button
// ---------------------------------------------------------------------------

test.describe('InterviewPage — View Board navigation', () => {
  test('"View Board" button navigates to the main board route (/)', async ({ page }) => {
    await mockEndEvent(page, 1)
    await gotoInterview(page)

    await expect(page.getByTestId('interview-view-board-btn')).toBeVisible({ timeout: 10000 })
    await page.getByTestId('interview-view-board-btn').click()

    // Should navigate away from /interview to the dashboard
    await expect(page).toHaveURL('/', { timeout: 5000 })
  })
})

// ---------------------------------------------------------------------------
// "Start New Interview" — reset and reconnect
// ---------------------------------------------------------------------------

test.describe('InterviewPage — Start New Interview', () => {
  test('"Start New Interview" replaces completion screen with waiting state', async ({ page }) => {
    // First SSE call: send end event → completion screen
    // Second SSE call (after reset): stall → waiting state
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream; charset=utf-8',
          headers: { 'Cache-Control': 'no-cache' },
          body: `event: end\ndata: ${JSON.stringify({ features_created: 2 })}\n\n`,
        })
      }
      // Second and subsequent calls: stall (simulates waiting for new Claude session)
    })

    await gotoInterview(page)

    // Wait for completion screen
    await expect(page.getByTestId('interview-ended')).toBeVisible({ timeout: 10000 })

    // Click "Start New Interview"
    await page.getByTestId('interview-new-session-btn').click()

    // Completion screen should be gone, waiting state should appear
    await expect(page.getByTestId('interview-ended')).not.toBeVisible()
    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 5000 })
  })

  test('"Start New Interview" resets feature count to 0', async ({ page }) => {
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream; charset=utf-8',
          headers: { 'Cache-Control': 'no-cache' },
          body: `event: end\ndata: ${JSON.stringify({ features_created: 5 })}\n\n`,
        })
      }
      // Subsequent calls: stall
    })

    await gotoInterview(page)

    // Verify 5 features shown on first completion
    await expect(page.getByTestId('interview-features-count')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('interview-features-count')).toContainText('5 features created')

    // Reset
    await page.getByTestId('interview-new-session-btn').click()

    // Waiting state — no features count displayed
    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('interview-features-count')).not.toBeVisible()
  })
})
