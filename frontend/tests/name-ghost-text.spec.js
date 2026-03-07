import { test, expect } from '@playwright/test'

/**
 * E2E tests for the inline ghost-text autocomplete on the feature name input.
 *
 * The ghost text overlay (data-testid="name-ghost-text") is only visible on
 * desktop (>= md / 768px).  The test database is seeded with NameToken entries
 * so that /api/autocomplete/name returns real suggestions.
 */

test.describe('Name field ghost text visual distinction', () => {
  test('ghost text has distinct color from typed text', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    // Open the new-feature card
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Get the computed color of the ghost text suffix span
    const ghostSuffixSpan = ghost.locator('span').nth(1) // Second span contains the ghost suffix
    const ghostColor = await ghostSuffixSpan.evaluate(el => getComputedStyle(el).color)

    // Get the computed color of the input text
    const inputColor = await titleInput.evaluate(el => getComputedStyle(el).color)

    // Ghost text color should be different from input text color
    // Input text is white (#ffffff or rgb(255, 255, 255))
    // Ghost text should be gray-500 (#6b7280 or rgb(107, 114, 128))
    expect(ghostColor).not.toBe(inputColor)

    // Verify ghost text has the expected gray color (text-gray-500 = #6b7280)
    // RGB values: 107, 114, 128
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

  test('ghost text uses same font as input', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    const ghostSuffixSpan = ghost.locator('span').nth(1)
    const ghostFont = await ghostSuffixSpan.evaluate(el => getComputedStyle(el).fontFamily)
    const inputFont = await titleInput.evaluate(el => getComputedStyle(el).fontFamily)

    // Both should use the same font family (Inter/sans-serif)
    expect(ghostFont).toBe(inputFont)
  })
})

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

    // Input should start with the completed token "Feature" followed by a space.
    // When a bigram exists (two-word suggestion), the value may be "Feature word2 "
    // instead of just "Feature " — both are valid accepted states.
    const value = await titleInput.inputValue()
    expect(value).toMatch(/^Feature\s/)

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

    const value = await titleInput.inputValue()
    expect(value).toMatch(/^Feature\s/)

    // Cursor should be positioned at the end of the accepted suggestion (including trailing space)
    const cursorPos = await titleInput.evaluate(el => el.selectionStart)
    expect(cursorPos).toBe(value.length)
  })

  test('ArrowDown cycles to the next suggestion', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // First suggestion: "Feature" → suffix "ture"
    await expect(ghost).toContainText('ture')

    // Press ArrowDown — should cycle to second suggestion "Features" → suffix "tures"
    await titleInput.press('ArrowDown')
    await expect(ghost).toContainText('tures')
  })

  test('ArrowUp cycles back to the previous suggestion', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // First suggestion: "Feature"
    await expect(ghost).toContainText('ture')

    // ArrowDown to second suggestion "Features"
    await titleInput.press('ArrowDown')
    await expect(ghost).toContainText('tures')

    // ArrowUp back to first suggestion "Feature"
    await titleInput.press('ArrowUp')
    await expect(ghost).toContainText('ture')
  })

  test('ArrowDown wraps around after last suggestion', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Get the first ghost text content
    await expect(ghost).toContainText('ture')

    // Count suggestions by cycling until we wrap back to the first
    // Cycle until we see "ture" again (without "s") after pressing ArrowDown multiple times
    let wrappedBack = false
    for (let i = 0; i < 10; i++) {
      await titleInput.press('ArrowDown')
      const text = await ghost.textContent()
      if (text?.includes('ture') && !text?.includes('tures')) {
        wrappedBack = true
        break
      }
    }
    expect(wrappedBack).toBe(true)
  })

  test('Tab accepts the currently cycled suggestion', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Cycle to second suggestion "Features"
    await titleInput.press('ArrowDown')
    await expect(ghost).toContainText('tures')

    // Accept with Tab — input should start with "Features" followed by a space.
    // A two-word suggestion (e.g. "Features word2 ") is also valid.
    await titleInput.press('Tab')
    const value = await titleInput.inputValue()
    expect(value).toMatch(/^Features\s/)
    await expect(ghost).not.toBeVisible()
  })

  test('ESC dismisses ghost text without changing input value', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Press ESC — ghost text should disappear, input value unchanged
    await titleInput.press('Escape')

    await expect(ghost).not.toBeVisible()
    await expect(titleInput).toHaveValue('Fea')
  })

  test('Enter dismisses ghost text without accepting suggestion', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).toBeVisible({ timeout: 3000 })

    // Press Enter — ghost text should disappear, input value should stay as "Fea"
    // (suggestion should NOT be accepted)
    await titleInput.press('Enter')

    await expect(ghost).not.toBeVisible()
    await expect(titleInput).toHaveValue('Fea')
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

test.describe('Name field mobile suggestion list', () => {
  test('shows suggestion list below input on mobile when typing 3+ chars', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await expect(titleInput).toBeVisible()

    // Type "Fea" — matches seeded tokens "feature" and "features"
    await titleInput.fill('Fea')

    // Suggestion list should appear below the input on mobile
    const suggestionList = page.locator('[data-testid="name-suggestion-list"]')
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

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const suggestionList = page.locator('[data-testid="name-suggestion-list"]')
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

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const suggestionList = page.locator('[data-testid="name-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // At most 5 chips should be shown
    const chips = suggestionList.locator('button')
    expect(await chips.count()).toBeLessThanOrEqual(5)
  })

  test('tapping a suggestion chip fills the name input on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const suggestionList = page.locator('[data-testid="name-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // Read the first chip's text before clicking
    const firstChip = suggestionList.locator('button').first()
    const chipText = await firstChip.textContent()

    // Click the chip
    await firstChip.click()

    // Input should now contain the suggestion text (case-insensitive — the DB token
    // is lowercase but typed prefix retains original case, so comparison is case-insensitive)
    const inputValue = await titleInput.inputValue()
    expect(inputValue.toLowerCase()).toContain(chipText.toLowerCase())

    // Suggestion list should be gone after selection
    await expect(suggestionList).not.toBeVisible()
  })

  test('suggestion list disappears when input is cleared on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const suggestionList = page.locator('[data-testid="name-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // Clear the input
    await titleInput.fill('')

    // Suggestion list should disappear
    await expect(suggestionList).not.toBeVisible()
  })

  test('suggestion list does not appear when prefix is shorter than 3 chars on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    // Only 2 chars — should not trigger suggestions
    await titleInput.fill('Fe')

    await page.waitForTimeout(300)

    const suggestionList = page.locator('[data-testid="name-suggestion-list"]')
    await expect(suggestionList).not.toBeVisible()
  })

  test('suggestion list is hidden on desktop viewport', async ({ page }) => {
    // Desktop viewport — suggestion list uses md:hidden
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    await page.waitForTimeout(500)

    const suggestionList = page.locator('[data-testid="name-suggestion-list"]')
    await expect(suggestionList).not.toBeVisible()
  })

  test('suggestion list is positioned below the input on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await titleInput.fill('Fea')

    const suggestionList = page.locator('[data-testid="name-suggestion-list"]')
    await expect(suggestionList).toBeVisible({ timeout: 3000 })

    // Verify the suggestion list is below (higher Y coordinate) the input
    const inputBox = await titleInput.boundingBox()
    const listBox = await suggestionList.boundingBox()

    expect(listBox.y).toBeGreaterThan(inputBox.y + inputBox.height - 5)
  })
})
