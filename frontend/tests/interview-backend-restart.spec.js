/**
 * E2E tests: Interview page — ephemeral session state behaviour.
 *
 * Feature #80: "Interview session state is ephemeral (no DB persistence)"
 *
 * Tests verify:
 * 1. No interview state is persisted in browser storage (localStorage / sessionStorage)
 * 2. Navigating away and back gives a clean initial state (no stale question)
 * 3. After SSE reconnect, a fresh question from a new session is displayed correctly
 * 4. Idle instructions are shown on initial load when no session is active
 *
 * Note: The "reconnect → idle" transition requires keeping an SSE connection open
 * with no events for 3+ seconds, which is not achievable with Playwright's
 * route.fulfill() API (it closes the connection after the body is sent).
 * That behaviour is instead verified by:
 *   - backend/test_interview_ephemeral.py (unit tests for ephemeral state)
 *   - frontend/tests/interview-idle-state.spec.js (idle timer fires correctly on initial load)
 *   - frontend/tests/interview-waiting-state.spec.js (reconnecting state transitions)
 */

import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function gotoInterview(page) {
  await page.goto('/interview')
  await page.waitForSelector('[data-testid="interview-page"]', { timeout: 10000 })
}

// ---------------------------------------------------------------------------
// 1. No browser-side persistence (localStorage / sessionStorage)
// ---------------------------------------------------------------------------

test.describe('InterviewPage — no client-side persistence', () => {
  test('no interview state is stored in localStorage after page load', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    // Wait for the page to settle (idle state appears after 3s)
    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })

    const keys = await page.evaluate(() => Object.keys(localStorage))
    const interviewKeys = keys.filter((k) => k.toLowerCase().includes('interview'))
    expect(interviewKeys).toHaveLength(0)
  })

  test('no interview state is stored in sessionStorage after page load', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page.getByTestId('interview-idle')).toBeVisible({ timeout: 6000 })

    const keys = await page.evaluate(() => Object.keys(sessionStorage))
    const interviewKeys = keys.filter((k) => k.toLowerCase().includes('interview'))
    expect(interviewKeys).toHaveLength(0)
  })

  test('no interview state is stored in localStorage after answering a question', async ({ page }) => {
    // Hold the answer POST so the component stays in 'answered' state long enough to check storage
    let resolveAnswer
    const answerHeld = new Promise((res) => { resolveAnswer = res })

    await page.route('**/api/interview/question/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        headers: { 'Cache-Control': 'no-cache' },
        body: 'event: question\ndata: {"text":"What feature?","options":["A","B"]}\n\n',
      })
    })
    await page.route('**/api/interview/answer', async (route) => {
      await answerHeld
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"received"}' })
    })

    await gotoInterview(page)
    await expect(page.getByTestId('survey-card')).toBeVisible({ timeout: 10000 })

    // Answer the question — POST is held so component stays in 'answered' state
    await page.getByTestId('survey-option-0').click()
    await expect(page.getByTestId('interview-answered')).toBeVisible({ timeout: 5000 })

    // Still no browser storage used
    const lsKeys = await page.evaluate(() => Object.keys(localStorage))
    const ssKeys = await page.evaluate(() => Object.keys(sessionStorage))
    expect(lsKeys.filter((k) => k.toLowerCase().includes('interview'))).toHaveLength(0)
    expect(ssKeys.filter((k) => k.toLowerCase().includes('interview'))).toHaveLength(0)

    // Release the held POST for clean teardown
    resolveAnswer()
  })
})

// ---------------------------------------------------------------------------
// 2. Navigating away and back starts fresh (no React state persistence)
// ---------------------------------------------------------------------------

test.describe('InterviewPage — clean state on remount', () => {
  test('navigating away and back shows waiting state (no stale question)', async ({ page }) => {
    // Push a question on first load
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream; charset=utf-8',
          headers: { 'Cache-Control': 'no-cache' },
          body: 'event: question\ndata: {"text":"First question","options":["Yes","No"]}\n\n',
        })
      } else {
        // Stall second connection — no new session active
      }
    })
    await page.route('**/api/interview/answer', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"received"}' })
    })

    await gotoInterview(page)
    await expect(page.getByTestId('survey-card')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('survey-question')).toContainText('First question')

    // Navigate to the home page
    await page.goto('/')
    await page.waitForSelector('body')

    // Navigate back to /interview — React remounts the component, status resets to 'waiting'
    await gotoInterview(page)

    // The stale question must NOT appear immediately (state is reset on remount)
    await expect(page.getByTestId('survey-card')).not.toBeVisible({ timeout: 2000 })
    // Waiting state (or idle after 3s) should appear instead
    await expect(
      page.getByTestId('interview-waiting').or(page.getByTestId('interview-idle'))
    ).toBeVisible({ timeout: 6000 })
  })

  test('page title is restored when navigating away from interview', async ({ page }) => {
    await page.route('**/api/interview/question/stream', () => {})
    await gotoInterview(page)

    await expect(page).toHaveTitle('Feature Interview | Feature Dashboard')

    // Navigate away — title should revert
    await page.goto('/')
    await page.waitForSelector('body')
    const title = await page.title()
    expect(title).not.toContain('Feature Interview')
  })
})

// ---------------------------------------------------------------------------
// 3. After reconnect, fresh question from new session is shown correctly
// ---------------------------------------------------------------------------

test.describe('InterviewPage — fresh session after backend restart', () => {
  test('question received after reconnect shows active state (no stale reconnecting UI)', async ({ page }) => {
    /**
     * Simulates a backend restart: first SSE connection closes immediately,
     * then a new connection delivers a fresh question from the restarted backend.
     */
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        // Simulate backend restart: connection drops immediately
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          headers: { 'Cache-Control': 'no-cache' },
          body: '',
        })
      } else {
        // New backend session starts immediately with a question
        route.fulfill({
          status: 200,
          contentType: 'text/event-stream; charset=utf-8',
          headers: { 'Cache-Control': 'no-cache', Connection: 'keep-alive' },
          body: 'event: question\ndata: {"text":"Post-restart question","options":["Continue","Stop"]}\n\n',
        })
      }
    })
    await page.route('**/api/interview/answer', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"received"}' })
    })

    await gotoInterview(page)

    // After reconnect, fresh question from the new session is shown
    await expect(page.getByTestId('survey-card')).toBeVisible({ timeout: 15000 })
    await expect(page.getByTestId('survey-question')).toContainText('Post-restart question')

    // No stale "Reconnecting…" banner — the session is live
    await expect(page.getByTestId('interview-reconnecting')).not.toBeVisible()
  })

  test('session-ended event after reconnect shows clean completion screen', async ({ page }) => {
    /**
     * After a backend restart, a quick interview (question → end) is completed.
     * The ended state should show the correct features_created count.
     */
    let callCount = 0
    await page.route('**/api/interview/question/stream', (route) => {
      callCount++
      if (callCount === 1) {
        // First connection: drops immediately (restart simulation)
        route.fulfill({
          status: 200, contentType: 'text/event-stream',
          headers: { 'Cache-Control': 'no-cache' }, body: '',
        })
      } else {
        // Second connection: sends end event immediately (session concluded)
        route.fulfill({
          status: 200, contentType: 'text/event-stream; charset=utf-8',
          headers: { 'Cache-Control': 'no-cache' },
          body: 'event: end\ndata: {"features_created": 2}\n\n',
        })
      }
    })

    await gotoInterview(page)

    // Completion screen should appear with the correct count
    await expect(page.getByTestId('interview-ended')).toBeVisible({ timeout: 15000 })
    await expect(page.getByTestId('interview-features-count')).toContainText('2 features')
  })
})
