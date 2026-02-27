import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Stall the SSE stream forever (simulates no active session → idle state). */
async function stallSSE(page) {
  await page.route('**/api/interview/question/stream', () => {})
}

/** SSE stream that immediately sends one question and stays open. */
async function mockSSEWithQuestion(page, question = {
  text: 'What is your favourite colour?',
  options: ['Red', 'Blue', 'Green'],
}) {
  await page.route('**/api/interview/question/stream', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      headers: { 'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no' },
      body: `event: question\ndata: ${JSON.stringify(question)}\n\n`,
    })
  })
  await page.route('**/api/interview/answer', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"received"}' })
  })
}

/** Mock the debug endpoint with a given response. */
async function mockDebug(page, response = null) {
  await page.route('**/api/interview/debug', (route) => {
    if (response === null) {
      route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"No active session"}' })
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(response) })
    }
  })
}

/** Mock debug endpoint with sample log entries. */
async function mockDebugWithLog(page, active = true) {
  await mockDebug(page, {
    active,
    log: [
      { timestamp: '2026-02-27T10:00:00.000Z', event_type: 'session_start',   detail: { started_at: '2026-02-27T10:00:00Z' } },
      { timestamp: '2026-02-27T10:00:01.000Z', event_type: 'question_posted',  detail: { text: 'What is your goal?', options: ['A', 'B'] } },
      { timestamp: '2026-02-27T10:00:05.000Z', event_type: 'sse_connect',      detail: {} },
      { timestamp: '2026-02-27T10:00:10.000Z', event_type: 'answer_submitted', detail: { value: 'A' } },
    ],
  })
}

async function gotoInterview(page) {
  await page.goto('/interview')
  await page.waitForSelector('[data-testid="interview-page"]', { timeout: 10000 })
}

// ---------------------------------------------------------------------------
// Visibility: hide in idle, show when session is running
// ---------------------------------------------------------------------------

test.describe('InterviewDebugPanel — visibility rules', () => {
  test('debug panel is NOT shown in idle state (no active session)', async ({ page }) => {
    await stallSSE(page)
    await mockDebug(page, null)
    await gotoInterview(page)

    // Wait for idle state to appear (3 s timer)
    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })

    // Panel must not be in the DOM while idle
    await expect(page.getByTestId('interview-debug-panel')).not.toBeVisible()
  })

  test('debug panel IS shown when a question is active (not idle)', async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebugWithLog(page)
    await gotoInterview(page)

    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
    await expect(page.getByTestId('interview-debug-panel')).toBeVisible()
  })

  test('debug panel IS shown in waiting state (before idle timer fires)', async ({ page }) => {
    await stallSSE(page)
    await mockDebug(page, null)
    await gotoInterview(page)

    // Immediately after load, waiting state is shown (before 3 s idle timer)
    await expect(page.getByTestId('interview-waiting')).toBeVisible({ timeout: 2000 })
    await expect(page.getByTestId('interview-debug-panel')).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Collapsed / expanded toggle
// ---------------------------------------------------------------------------

test.describe('InterviewDebugPanel — collapse/expand', () => {
  test.beforeEach(async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebugWithLog(page)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
  })

  test('panel is collapsed by default (log entries not visible)', async ({ page }) => {
    await expect(page.getByTestId('interview-debug-entries')).not.toBeVisible()
  })

  test('clicking toggle expands the panel', async ({ page }) => {
    await page.getByTestId('interview-debug-toggle').click()
    await expect(page.getByTestId('interview-debug-entries')).toBeVisible()
  })

  test('clicking toggle again collapses the panel', async ({ page }) => {
    await page.getByTestId('interview-debug-toggle').click()
    await expect(page.getByTestId('interview-debug-entries')).toBeVisible()

    await page.getByTestId('interview-debug-toggle').click()
    await expect(page.getByTestId('interview-debug-entries')).not.toBeVisible()
  })

  test('toggle button shows correct chevron direction', async ({ page }) => {
    // Collapsed: chevron-up (pointing up, indicating "expand")
    const toggle = page.getByTestId('interview-debug-toggle')
    await expect(toggle).toBeVisible()

    // Expand
    await toggle.click()
    await expect(page.getByTestId('interview-debug-entries')).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Log entries display
// ---------------------------------------------------------------------------

test.describe('InterviewDebugPanel — log entries', () => {
  test.beforeEach(async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebugWithLog(page)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
    await page.getByTestId('interview-debug-toggle').click()
    await expect(page.getByTestId('interview-debug-entries')).toBeVisible()
  })

  test('log entries are rendered', async ({ page }) => {
    const entries = page.getByTestId('interview-debug-entry')
    await expect(entries).toHaveCount(4)
  })

  test('entry count badge shown in header', async ({ page }) => {
    await expect(page.getByTestId('interview-debug-count')).toContainText('4')
  })

  test('session_start badge is visible', async ({ page }) => {
    await expect(page.getByTestId('interview-debug-badge-session_start')).toBeVisible()
  })

  test('question_posted badge is visible', async ({ page }) => {
    await expect(page.getByTestId('interview-debug-badge-question_posted')).toBeVisible()
  })

  test('sse_connect badge is visible', async ({ page }) => {
    await expect(page.getByTestId('interview-debug-badge-sse_connect')).toBeVisible()
  })

  test('answer_submitted badge is visible', async ({ page }) => {
    await expect(page.getByTestId('interview-debug-badge-answer_submitted')).toBeVisible()
  })

  test('question_posted entry shows question text in detail', async ({ page }) => {
    // The "What is your goal?" text should appear in the detail column
    await expect(page.getByTestId('interview-debug-entries')).toContainText('What is your goal?')
  })

  test('answer_submitted entry shows answer value in detail', async ({ page }) => {
    await expect(page.getByTestId('interview-debug-entries')).toContainText('A')
  })

  test('empty state shown when no log entries', async ({ page }) => {
    // Re-mock with empty log
    await page.unrouteAll()
    await mockSSEWithQuestion(page)
    await mockDebug(page, { active: true, log: [] })
    await page.reload()
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
    await page.getByTestId('interview-debug-toggle').click()
    await expect(page.getByTestId('interview-debug-empty')).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Connection status indicator
// ---------------------------------------------------------------------------

test.describe('InterviewDebugPanel — connection status', () => {
  test('shows "Active" status when session is active', async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebug(page, { active: true, log: [] })
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })

    await expect(page.getByTestId('interview-debug-status')).toContainText('Active')
  })

  test('shows "Ended" status when session recently ended (active: false)', async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebug(page, { active: false, log: [] })
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })

    await expect(page.getByTestId('interview-debug-status')).toContainText('Ended')
  })

  test('shows "No session" status when debug returns 404', async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebug(page, null)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })

    await expect(page.getByTestId('interview-debug-status')).toContainText('No session')
  })
})

// ---------------------------------------------------------------------------
// Refresh button
// ---------------------------------------------------------------------------

test.describe('InterviewDebugPanel — refresh button', () => {
  test('refresh button is visible', async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebugWithLog(page)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })

    await expect(page.getByTestId('interview-debug-refresh')).toBeVisible()
  })

  test('clicking refresh triggers a new debug API call', async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebugWithLog(page)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })

    let refreshCalled = false
    await page.route('**/api/interview/debug', async (route) => {
      refreshCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ active: true, log: [] }),
      })
    })

    await page.getByTestId('interview-debug-refresh').click()
    // Give time for the refetch to fire
    await page.waitForTimeout(500)
    expect(refreshCalled).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Mobile layout
// ---------------------------------------------------------------------------

test.describe('InterviewDebugPanel — mobile layout (375px)', () => {
  test.use({ viewport: { width: 375, height: 667 } })

  test('no horizontal overflow at 375px', async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebugWithLog(page)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })

    const scrollWidth = await page.evaluate(() => document.body.scrollWidth)
    expect(scrollWidth).toBeLessThanOrEqual(375)
  })

  test('debug panel toggle is within viewport at 375px', async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebugWithLog(page)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="interview-debug-panel"]', { timeout: 10000 })

    const box = await page.getByTestId('interview-debug-toggle').boundingBox()
    expect(box).not.toBeNull()
    expect(box.x + box.width).toBeLessThanOrEqual(375)
  })

  test('expanded log area has max-height constraint on mobile', async ({ page }) => {
    await mockSSEWithQuestion(page)
    await mockDebugWithLog(page)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
    await page.getByTestId('interview-debug-toggle').click()

    const entries = page.getByTestId('interview-debug-entries')
    await expect(entries).toBeVisible()

    const { maxHeight } = await entries.evaluate((el) => ({
      maxHeight: getComputedStyle(el).maxHeight,
    }))
    // max-h-[150px] on mobile → 150px
    expect(parseInt(maxHeight)).toBeLessThanOrEqual(150)
  })
})
