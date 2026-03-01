import { test, expect } from '@playwright/test'

/**
 * E2E tests for the inline ghost-text autocomplete on the feature description
 * textarea.
 *
 * The ghost text overlay (data-testid="description-ghost-text") is only visible
 * on desktop (>= md / 768px).  The test database is seeded with DescriptionToken
 * entries so that /api/autocomplete/description returns real suggestions.
 */

test.describe('Description field ghost text (desktop)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')
  })

  test('ghost text appears when typing 3+ chars in NewFeatureCard description', async ({ page }) => {
    // Open the new-feature card in the TODO lane
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await expect(descTextarea).toBeVisible()

    // Type "fea" — matches the seeded token "feature"
    await descTextarea.fill('fea')

    // Ghost text overlay should appear on desktop
    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // The overlay should contain the suffix "ture" (completing "feature")
    await expect(ghost).toContainText('ture')
  })

  test('ghost text disappears when description textarea is cleared', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Clear the textarea — ghost text should vanish
    await descTextarea.fill('')
    await expect(ghost).not.toBeVisible()
  })

  test('ghost text not shown when description prefix is shorter than 3 chars', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')

    // Two chars — should not trigger ghost text
    await descTextarea.fill('fe')

    // Wait briefly to ensure no async ghost text appears
    await page.waitForTimeout(300)
    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).not.toBeVisible()
  })

  test('Tab key accepts the ghost text suggestion in description field', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Press Tab to accept the suggestion
    await descTextarea.press('Tab')

    // Textarea should now contain the completed token "feature"
    await expect(descTextarea).toHaveValue('feature')

    // Ghost text should be gone after acceptance
    await expect(ghost).not.toBeVisible()
  })

  test('Tab key positions cursor after the inserted token in description field', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Press Tab to accept the suggestion
    await descTextarea.press('Tab')

    await expect(descTextarea).toHaveValue('feature')

    // Cursor should be positioned at the end of the accepted token
    const cursorPos = await descTextarea.evaluate(el => el.selectionStart)
    expect(cursorPos).toBe('feature'.length)
  })

  test('ghost text not visible on mobile viewport in description field', async ({ page }) => {
    // Set a narrow (mobile) viewport — below the md breakpoint (768px)
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    // Wait to allow any async fetch to resolve
    await page.waitForTimeout(500)

    // Ghost element uses "hidden md:block" — it is display:none on mobile
    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).not.toBeVisible()
  })

  test('ghost text appears in DetailPanel description edit mode', async ({ page }) => {
    // Click on the first feature card to open the detail panel
    const firstCard = page.locator('[data-testid="kanban-card"]').first()
    await firstCard.click()

    // Wait for detail panel to open
    const detailPanel = page.locator('[data-testid="detail-panel"]')
    await expect(detailPanel).toBeVisible()

    // Click on the description field to enter edit mode
    const descSection = detailPanel.locator('label:has-text("Description")').locator('..')
    const descDisplay = descSection.locator('.cursor-text')
    await descDisplay.click()

    // The description textarea should now be visible
    const descTextarea = detailPanel.locator('textarea')
    await expect(descTextarea).toBeVisible()

    // Clear and type a token prefix that matches a seeded description token
    await descTextarea.fill('imp')

    // Ghost text overlay should appear on desktop
    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // The overlay should contain the suffix "lement" (completing "implement")
    await expect(ghost).toContainText('lement')
  })
})
