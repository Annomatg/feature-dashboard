import { test, expect } from '@playwright/test'

/**
 * E2E tests verifying that features created via the interview flow appear
 * on the Kanban board without any manual refresh.
 *
 * The interview skill commits features directly to the database via the MCP
 * tool. The board picks them up via TanStack Query's refetchInterval (5 s),
 * so features should appear within the polling window.
 *
 * Tests simulate "interview auto-commit" by posting features directly to the
 * REST API (port 8001, isolated test database) — the same database the board
 * reads from — which is equivalent to an external MCP write.
 *
 * Uses isolated test database (port 8001).
 */

const API = 'http://localhost:8001'

async function createFeature(request, overrides = {}) {
  const response = await request.post(`${API}/api/features`, {
    data: {
      category: 'InterviewRefresh',
      name: 'Interview Board Refresh Test',
      description: 'Created to verify interview auto-commit board refresh',
      steps: ['Verify feature appears in TODO lane without manual refresh'],
      ...overrides,
    },
  })
  expect(response.ok()).toBeTruthy()
  return response.json()
}

async function deleteFeature(request, id) {
  await request.delete(`${API}/api/features/${id}`)
}

test.describe('Interview → Board: features appear without manual refresh', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 })
  })

  test('feature created while board is open appears in TODO lane via polling', async ({ page, request }) => {
    // Board is already open. Simulate the interview skill committing a feature
    // (MCP tool → DB) by posting directly to the REST API.
    const feature = await createFeature(request, {
      name: 'Interview Auto-Commit Feature (board open)',
    })

    // The board polls every 5 s; allow up to 8 s for the card to appear.
    await expect(
      page
        .locator('[data-testid="kanban-card"]')
        .filter({ hasText: 'Interview Auto-Commit Feature (board open)' })
    ).toBeVisible({ timeout: 8000 })

    await deleteFeature(request, feature.id)
  })

  test('multiple features created during interview all appear in TODO lane', async ({ page, request }) => {
    // Simulate an interview session that creates 3 features in succession.
    const names = [
      'Interview Feature Alpha',
      'Interview Feature Beta',
      'Interview Feature Gamma',
    ]

    const created = await Promise.all(
      names.map((name) => createFeature(request, { name }))
    )

    // All cards should appear on the board within the polling window.
    for (const name of names) {
      await expect(
        page.locator('[data-testid="kanban-card"]').filter({ hasText: name })
      ).toBeVisible({ timeout: 8000 })
    }

    await Promise.all(created.map((f) => deleteFeature(request, f.id)))
  })

  test('feature appears immediately when navigating from /interview to board', async ({ page, request }) => {
    // Simulate: user is on /interview, interview completes, user clicks "View Board".
    // Create the feature first (as the interview skill would).
    const feature = await createFeature(request, {
      name: 'Feature Created Before View-Board Navigation',
    })

    // Navigate to the board (simulates clicking the "View Board" button).
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 })

    // On navigation, TanStack Query fetches fresh data immediately; the feature
    // should appear without waiting for the poll interval.
    await expect(
      page
        .locator('[data-testid="kanban-card"]')
        .filter({ hasText: 'Feature Created Before View-Board Navigation' })
    ).toBeVisible({ timeout: 5000 })

    await deleteFeature(request, feature.id)
  })
})
