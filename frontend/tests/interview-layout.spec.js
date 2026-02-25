import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Mock SSE stream that immediately pushes one question event then stays open. */
async function mockInterviewQuestion(page, question = {
  text: 'Which framework do you prefer?',
  options: ['React', 'Vue', 'Svelte'],
}) {
  // Playwright fulfills the SSE route with a single event.
  // EventSource will see the event, then the connection closes and auto-reconnects —
  // but by that time the question is already rendered, which is all we need.
  await page.route('**/api/interview/question/stream', (route) => {
    const body = [
      `event: question`,
      `data: ${JSON.stringify(question)}`,
      ``,
      ``,
    ].join('\n')

    route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      headers: {
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
      body,
    })
  })

  // Silently accept answer POSTs
  await page.route('**/api/interview/answer', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'received', value: 'mock' }),
    })
  })
}

/** Navigate to /interview and wait for the page to load. */
async function gotoInterview(page) {
  await page.goto('/interview')
  await page.waitForSelector('[data-testid="interview-page"]', { timeout: 10000 })
}

// ---------------------------------------------------------------------------
// Mobile tests — 390×844 (iPhone 14)
// ---------------------------------------------------------------------------

test.describe('InterviewPage layout — mobile 390×844', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test.beforeEach(async ({ page }) => {
    await mockInterviewQuestion(page)
    await gotoInterview(page)
    // Wait until the question is rendered
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
  })

  test('page root covers the full viewport height', async ({ page }) => {
    const pageEl = page.getByTestId('interview-page')
    const box = await pageEl.boundingBox()
    expect(box).not.toBeNull()
    // min-h-screen means it should be >= viewport height
    expect(box.height).toBeGreaterThanOrEqual(844)
  })

  test('no horizontal scroll at 390px', async ({ page }) => {
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth)
    expect(scrollWidth).toBeLessThanOrEqual(390)
  })

  test('question heading is at least text-xl (20px) and bold', async ({ page }) => {
    const heading = page.getByTestId('survey-question')
    await expect(heading).toBeVisible()

    const { fontSize, fontWeight } = await heading.evaluate((el) => {
      const s = getComputedStyle(el)
      return { fontSize: parseFloat(s.fontSize), fontWeight: parseInt(s.fontWeight, 10) }
    })

    // text-xl = 1.25rem = 20px at default root font size
    expect(fontSize).toBeGreaterThanOrEqual(20)
    // font-semibold = 600, font-bold = 700
    expect(fontWeight).toBeGreaterThanOrEqual(600)
  })

  test('option buttons meet min-h-14 (56px) tap target at mobile', async ({ page }) => {
    const btns = await page.locator('[data-testid^="survey-option-"]').all()
    expect(btns.length).toBeGreaterThan(0)

    for (const btn of btns) {
      const box = await btn.boundingBox()
      expect(box).not.toBeNull()
      expect(box.height).toBeGreaterThanOrEqual(56)
    }
  })

  test('option buttons are full-width (w-full) at 390px', async ({ page }) => {
    const content = page.getByTestId('interview-content')
    const contentBox = await content.boundingBox()

    const btns = await page.locator('[data-testid^="survey-option-"]').all()
    for (const btn of btns) {
      const box = await btn.boundingBox()
      // Width should match the content container width (within 2px rounding)
      expect(box.width).toBeCloseTo(contentBox.width, -1)
    }
  })

  test('content container uses w-full (not narrower than viewport)', async ({ page }) => {
    const content = page.getByTestId('interview-content')
    const box = await content.boundingBox()
    // Content area should span most of the 390px width (allowing for px-4 = 16px padding each side)
    expect(box.width).toBeGreaterThanOrEqual(358) // 390 - 2*16
  })

  test('question text is visible and correct', async ({ page }) => {
    await expect(page.getByTestId('survey-question')).toContainText('Which framework do you prefer?')
  })

  test('waiting state is shown before question arrives', async ({ page }) => {
    // Create a fresh page that stalls the SSE stream before pushing a question
    const page2 = await page.context().newPage()
    await page2.route('**/api/interview/question/stream', () => {
      // Never fulfill — simulates waiting
    })
    await page2.goto('/interview')
    await page2.waitForSelector('[data-testid="interview-waiting"]', { timeout: 10000 })
    await expect(page2.getByTestId('interview-waiting')).toBeVisible()
    await page2.close()
  })
})

// ---------------------------------------------------------------------------
// Desktop tests — 1280×800
// ---------------------------------------------------------------------------

test.describe('InterviewPage layout — desktop 1280×800', () => {
  test.use({ viewport: { width: 1280, height: 800 } })

  test.beforeEach(async ({ page }) => {
    await mockInterviewQuestion(page)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
  })

  test('page root covers the full viewport height at 1280px', async ({ page }) => {
    const pageEl = page.getByTestId('interview-page')
    const box = await pageEl.boundingBox()
    expect(box.height).toBeGreaterThanOrEqual(800)
  })

  test('no horizontal scroll at 1280px', async ({ page }) => {
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth)
    expect(scrollWidth).toBeLessThanOrEqual(1280)
  })

  test('question heading is still at least text-xl on desktop', async ({ page }) => {
    const { fontSize } = await page.getByTestId('survey-question').evaluate((el) => {
      const s = getComputedStyle(el)
      return { fontSize: parseFloat(s.fontSize) }
    })
    expect(fontSize).toBeGreaterThanOrEqual(20)
  })

  test('option buttons still meet 56px minimum height on desktop', async ({ page }) => {
    const btns = await page.locator('[data-testid^="survey-option-"]').all()
    for (const btn of btns) {
      const box = await btn.boundingBox()
      expect(box.height).toBeGreaterThanOrEqual(56)
    }
  })

  test('content is centred within a max-w-2xl container on desktop', async ({ page }) => {
    const content = page.getByTestId('interview-content')
    const box = await content.boundingBox()
    // max-w-2xl = 672px
    expect(box.width).toBeLessThanOrEqual(672 + 2) // small rounding allowance
    // Should be horizontally centred — left offset > 0
    expect(box.x).toBeGreaterThan(0)
  })

  test('Other option text input and submit button are usable on desktop', async ({ page }) => {
    await page.getByTestId('survey-option-other').click()
    await expect(page.getByTestId('other-text-input')).toBeVisible()
    await page.getByTestId('other-text-input').fill('Custom desktop answer')
    await expect(page.getByTestId('other-submit-btn')).toBeEnabled()
  })
})

// ---------------------------------------------------------------------------
// Shared functional tests (run at default desktop viewport)
// ---------------------------------------------------------------------------

test.describe('InterviewPage functional behaviour', () => {
  test.beforeEach(async ({ page }) => {
    await mockInterviewQuestion(page)
    await gotoInterview(page)
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
  })

  test('renders the interview page container', async ({ page }) => {
    await expect(page.getByTestId('interview-page')).toBeVisible()
  })

  test('session-ended state is shown when SSE sends end event', async ({ page }) => {
    const page2 = await page.context().newPage()
    await page2.route('**/api/interview/question/stream', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        headers: { 'Cache-Control': 'no-cache' },
        body: 'event: end\ndata: {}\n\n',
      })
    })
    await page2.goto('/interview')
    await expect(page2.getByTestId('interview-ended')).toBeVisible({ timeout: 10000 })
    await expect(page2.getByText('Interview complete')).toBeVisible()
    await page2.close()
  })
})
