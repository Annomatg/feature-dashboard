import { test, expect } from '@playwright/test'

/**
 * E2E tests for the inline ghost-text autocomplete on the feature description
 * textarea.
 *
 * The ghost text overlay (data-testid="description-ghost-text") is only visible
 * on desktop (>= md / 768px).  The test database is seeded with DescriptionToken
 * entries so that /api/autocomplete/description returns real suggestions.
 */

test.describe('Description field ghost text visual distinction', () => {
  test('ghost text has distinct color from typed text', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    // Open the new-feature card
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Get the computed color of the ghost text suffix span
    const ghostSuffixSpan = ghost.locator('span').nth(1) // Second span contains the ghost suffix
    const ghostColor = await ghostSuffixSpan.evaluate(el => getComputedStyle(el).color)

    // Get the computed color of the textarea text
    const textareaColor = await descTextarea.evaluate(el => getComputedStyle(el).color)

    // Ghost text color should be different from textarea text color
    expect(ghostColor).not.toBe(textareaColor)

    // Verify ghost text has the expected gray color (text-gray-500 = #6b7280)
    const ghostRgb = ghostColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/)
    expect(ghostRgb).not.toBeNull()
    const r = parseInt(ghostRgb[1])
    const g = parseInt(ghostRgb[2])
    const b = parseInt(ghostRgb[3])
    // Allow some tolerance for color rendering
    expect(r).toBeGreaterThanOrEqual(100)
    expect(r).toBeLessThanOrEqual(120)
    expect(g).toBeGreaterThanOrEqual(107)
    expect(g).toBeLessThanOrEqual(127)
    expect(b).toBeGreaterThanOrEqual(120)
    expect(b).toBeLessThanOrEqual(140)
  })

  test('ghost text uses same font as textarea', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    const ghostSuffixSpan = ghost.locator('span').nth(1)
    const ghostFont = await ghostSuffixSpan.evaluate(el => getComputedStyle(el).fontFamily)
    const textareaFont = await descTextarea.evaluate(el => getComputedStyle(el).fontFamily)

    // Both should use the same font family (Inter/sans-serif)
    expect(ghostFont).toBe(textareaFont)
  })
})

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

    // Textarea should now contain the completed token "feature" with a trailing space
    await expect(descTextarea).toHaveValue('feature ')

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

    await expect(descTextarea).toHaveValue('feature ')

    // Cursor should be positioned at the end of the accepted token (including trailing space)
    const cursorPos = await descTextarea.evaluate(el => el.selectionStart)
    expect(cursorPos).toBe('feature '.length)
  })

  test('ArrowDown cycles to next suggestion in description field', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('imp')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // First suggestion: "implement" → suffix "lement"
    await expect(ghost).toContainText('lement')

    // Press ArrowDown — should cycle to second suggestion "implementation" → suffix "lementation"
    await descTextarea.press('ArrowDown')
    await expect(ghost).toContainText('lementation')
  })

  test('ArrowUp cycles back to previous suggestion in description field', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('imp')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // First suggestion: "implement"
    await expect(ghost).toContainText('lement')

    // ArrowDown to "implementation"
    await descTextarea.press('ArrowDown')
    await expect(ghost).toContainText('lementation')

    // ArrowUp back to "implement"
    await descTextarea.press('ArrowUp')
    await expect(ghost).toContainText('lement')
  })

  test('Tab accepts the currently cycled suggestion in description field', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('imp')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Cycle to second suggestion "implementation"
    await descTextarea.press('ArrowDown')
    await expect(ghost).toContainText('lementation')

    // Accept with Tab — textarea should contain "implementation" with a trailing space
    await descTextarea.press('Tab')
    await expect(descTextarea).toHaveValue('implementation ')
    await expect(ghost).not.toBeVisible()
  })

  test('ESC dismisses ghost text in description field without changing value', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Press ESC — ghost text should disappear, textarea value unchanged
    await descTextarea.press('Escape')

    await expect(ghost).not.toBeVisible()
    await expect(descTextarea).toHaveValue('fea')
  })

  test('Enter dismisses ghost text in description field without accepting suggestion', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Press Enter — ghost text should disappear
    // For textarea, Enter adds a newline (normal behavior)
    // The suggestion should NOT be accepted (value should not become "feature..." or similar)
    await descTextarea.press('Enter')

    await expect(ghost).not.toBeVisible()
    // Value should start with 'fea' - either 'fea\n' (normal Enter in textarea) or 'fea' depending on form handling
    const value = await descTextarea.inputValue()
    expect(value.startsWith('fea')).toBe(true)
    // Should NOT contain the full suggestion (e.g., "feature" or "features")
    expect(value).not.toContain('feature')
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

  test('ghost text not shown on mobile when description prefix is shorter than 3 chars', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fe')

    await page.waitForTimeout(300)
    const suggestionList = page.locator('[data-testid="description-suggestion-list"]')
    await expect(suggestionList).not.toBeVisible()
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

test.describe('Description field mobile suggestion list', () => {
  test('shows suggestion list below textarea on mobile when typing 3+ chars', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await expect(descTextarea).toBeVisible()

    // Type "fea" — matches seeded description tokens
    await descTextarea.fill('fea')

    // Suggestion list should appear below the textarea on mobile
    const suggestionList = page.locator('[data-testid="description-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // Should show at least one suggestion chip
    const chips = suggestionList.locator('button')
    expect(await chips.count()).toBeGreaterThanOrEqual(1)
  })

  test('suggestion list uses dark theme styling on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const suggestionList = page.locator('[data-testid="description-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // Verify container has dark background (bg-surface = #2d2d2d)
    const containerBg = await suggestionList.evaluate(el => getComputedStyle(el).backgroundColor)
    // Expect dark background: rgb(45, 45, 45) = #2d2d2d
    const bgMatch = containerBg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/)
    expect(bgMatch).not.toBeNull()
    const r = parseInt(bgMatch[1])
    const g = parseInt(bgMatch[2])
    const b = parseInt(bgMatch[3])
    // Dark background should have low RGB values
    expect(r).toBeLessThanOrEqual(60)
    expect(g).toBeLessThanOrEqual(60)
    expect(b).toBeLessThanOrEqual(60)

    // Verify container has a border
    const containerBorder = await suggestionList.evaluate(el => getComputedStyle(el).borderWidth)
    expect(parseFloat(containerBorder)).toBeGreaterThan(0)

    // Verify first chip has dark background
    const firstChip = suggestionList.locator('button').first()
    const chipBg = await firstChip.evaluate(el => getComputedStyle(el).backgroundColor)
    const chipBgMatch = chipBg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/)
    expect(chipBgMatch).not.toBeNull()
    // Chip background should be dark (bg-background = #1a1a1a or bg-surface = #2d2d2d)
    const chipR = parseInt(chipBgMatch[1])
    expect(chipR).toBeLessThanOrEqual(60)
  })

  test('suggestion list shows up to 5 chips on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const suggestionList = page.locator('[data-testid="description-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // At most 5 chips should be shown
    const chips = suggestionList.locator('button')
    expect(await chips.count()).toBeLessThanOrEqual(5)
  })

  test('tapping a suggestion chip fills the description textarea on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const suggestionList = page.locator('[data-testid="description-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // Read the first chip's text before clicking
    const firstChip = suggestionList.locator('button').first()
    const chipText = await firstChip.textContent()

    // Click the chip
    await firstChip.click()

    // Textarea should now contain the suggestion text
    const textareaValue = await descTextarea.inputValue()
    expect(textareaValue.toLowerCase()).toContain(chipText.toLowerCase())

    // Suggestion list should be gone after selection
    await expect(suggestionList).not.toBeVisible()
  })

  test('suggestion list disappears when textarea is cleared on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const suggestionList = page.locator('[data-testid="description-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // Clear the textarea
    await descTextarea.fill('')

    // Suggestion list should disappear
    await expect(suggestionList).not.toBeVisible()
  })

  test('suggestion list does not appear when prefix is shorter than 3 chars on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    // Only 2 chars — should not trigger suggestions
    await descTextarea.fill('fe')

    await page.waitForTimeout(300)

    const suggestionList = page.locator('[data-testid="description-suggestion-list"]')
    await expect(suggestionList).not.toBeVisible()
  })

  test('suggestion list is hidden on desktop viewport', async ({ page }) => {
    // Desktop viewport — suggestion list uses md:hidden
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    await page.waitForTimeout(500)

    const suggestionList = page.locator('[data-testid="description-suggestion-list"]')
    await expect(suggestionList).not.toBeVisible()
  })

  test('suggestion list is positioned below the textarea on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descTextarea = page.locator('textarea[placeholder*="Describe"]')
    await descTextarea.fill('fea')

    const suggestionList = page.locator('[data-testid="description-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // Verify the suggestion list is below (higher Y coordinate) the textarea
    const textareaBox = await descTextarea.boundingBox()
    const listBox = await suggestionList.boundingBox()

    expect(listBox.y).toBeGreaterThan(textareaBox.y + textareaBox.height - 5)
  })
})
