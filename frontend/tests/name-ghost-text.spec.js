import { test, expect } from '@playwright/test'

/**
 * E2E tests for the inline ghost-text autocomplete on the feature name input.
 *
 * The ghost text overlay (data-testid="name-ghost-text") is only visible on
 * desktop (>= md / 768px).  The test database is seeded with NameToken entries
 * so that /api/autocomplete/name returns real suggestions.
 */

test.describe('Name field ghost text (desktop)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')
  })

  test('ghost text appears when typing 3+ chars that match a token', async ({ page }) => {
    // Open the new-feature card in the TODO lane
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await expect(titleInput).toBeVisible()

    // Type "Fea" — matches the seeded token "Feature"
    await titleInput.fill('Fea')

    // Ghost text overlay should appear on desktop
    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // The overlay should contain the suffix "ture" (completing "Feature")
    await expect(ghost).toContainText('ture')
  })

  test('ghost text disappears when input is cleared', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Clear the input — ghost text should vanish
    await titleInput.fill('')
    await expect(ghost).not.toBeVisible()
  })

  test('ghost text not shown when prefix is shorter than 3 chars', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')

    // Two chars — should not trigger ghost text
    await titleInput.fill('Fe')

    // Wait briefly to ensure no async ghost text appears
    await page.waitForTimeout(300)
    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).not.toBeVisible()
  })

  test('Tab key accepts the ghost text suggestion', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Press Tab to accept the suggestion
    await titleInput.press('Tab')

    // Input should now contain the completed token "Feature"
    await expect(titleInput).toHaveValue('Feature')

    // Ghost text should be gone after acceptance
    await expect(ghost).not.toBeVisible()
  })

  test('Tab key positions cursor after the inserted token', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Press Tab to accept the suggestion
    await titleInput.press('Tab')

    await expect(titleInput).toHaveValue('Feature')

    // Cursor should be positioned at the end of the accepted token
    const cursorPos = await titleInput.evaluate(el => el.selectionStart)
    expect(cursorPos).toBe('Feature'.length)
  })

  test('ghost text not visible on mobile viewport', async ({ page }) => {
    // Set a narrow (mobile) viewport — below the md breakpoint (768px)
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    // Wait to allow any async fetch to resolve
    await page.waitForTimeout(500)

    // Ghost element uses "hidden md:flex" — it is display:none on mobile
    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).not.toBeVisible()
  })
})
