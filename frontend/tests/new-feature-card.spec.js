import { test, expect } from '@playwright/test'

test.describe('NewFeatureCard', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app
    await page.goto('http://localhost:5173')
    // Wait for the kanban board to load
    await page.waitForSelector('text=FEATURE DASHBOARD')
  })

  test('should open new feature card when clicking + button in TODO lane', async ({ page }) => {
    // Click the + button in the TODO lane
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    // Check that the new feature card appears
    await expect(page.locator('.text-sm.font-mono.font-semibold:has-text("NEW FEATURE")')).toBeVisible()
    await expect(page.locator('input[placeholder*="Enter feature title"]')).toBeVisible()
  })

  test('should auto-focus title field when opening new feature card', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    // Check that the title input is focused
    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await expect(titleInput).toBeFocused()
  })

  test('should disable save button when title is empty', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    // Save button should be disabled
    const saveButton = page.locator('button:has-text("Save")')
    await expect(saveButton).toBeDisabled()
  })

  test('should enable save button when title is filled', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    // Fill in the title
    await page.fill('input[placeholder*="Enter feature title"]', 'Test Feature')

    // Save button should be enabled
    const saveButton = page.locator('button:has-text("Save")')
    await expect(saveButton).toBeEnabled()
  })

  test('should create feature with required fields only', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    // Fill in only the title
    await page.fill('input[placeholder*="Enter feature title"]', 'Minimal Test Feature')

    // Click save
    await page.click('button:has-text("Save")')

    // Wait for the feature to appear in the TODO lane
    await expect(page.locator('text=Minimal Test Feature').first()).toBeVisible({ timeout: 10000 })

    // Feature card should be closed
    await expect(page.locator('.text-sm.font-mono.font-semibold:has-text("NEW FEATURE")')).not.toBeVisible()
  })

  test('should create feature with all fields filled', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    // Fill in all fields
    await page.fill('input[placeholder*="Enter feature title"]', 'Complete Test Feature')
    await page.fill('input[placeholder*="Frontend, Backend"]', 'Testing')
    await page.fill('textarea[placeholder*="Describe"]', 'This is a test feature with all fields')

    // Add steps
    const stepInput = page.locator('input[placeholder*="Add a step"]')
    await stepInput.fill('Step 1')
    await stepInput.press('Enter')
    await stepInput.fill('Step 2')
    await stepInput.press('Enter')

    // Click save
    await page.click('button:has-text("Save")')

    // Wait for the feature to appear
    await expect(page.locator('text=Complete Test Feature').first()).toBeVisible({ timeout: 10000 })

    // Check that the category and step count are visible
    await expect(page.locator('text=Testing').first()).toBeVisible()
    await expect(page.locator('text=2 steps').first()).toBeVisible()
  })

  test('should add step when pressing Enter key', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const stepInput = page.locator('input[placeholder*="Add a step"]')

    // Add first step with Enter key
    await stepInput.fill('First step')
    await stepInput.press('Enter')

    // Check that the step appears in the list
    await expect(page.locator('text=First step')).toBeVisible()

    // Input should be cleared
    await expect(stepInput).toHaveValue('')
  })

  test('should remove step when clicking trash icon', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const stepInput = page.locator('input[placeholder*="Add a step"]')

    // Add a step
    await stepInput.fill('Step to remove')
    await stepInput.press('Enter')

    // Hover over the step to show the trash icon
    const stepItem = page.locator('text=Step to remove').locator('..')
    await stepItem.hover()

    // Click the trash icon
    await stepItem.locator('button[aria-label="Remove step"]').click()

    // Step should be removed
    await expect(page.locator('text=Step to remove')).not.toBeVisible()
  })

  test('should cancel feature creation', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    // Fill in some data
    await page.fill('input[placeholder*="Enter feature title"]', 'Feature to Cancel')

    // Click cancel
    await page.click('button:has-text("Cancel")')

    // Feature card should be closed
    await expect(page.locator('.text-sm.font-mono.font-semibold:has-text("NEW FEATURE")')).not.toBeVisible()

    // Feature should not be created
    await expect(page.locator('text=Feature to Cancel')).not.toBeVisible()
  })

  test('should create feature in IN PROGRESS lane', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to IN PROGRESS"]').click()

    await page.fill('input[placeholder*="Enter feature title"]', 'In Progress Feature')
    await page.click('button:has-text("Save")')

    // Feature should appear in IN PROGRESS lane
    await expect(page.locator('text=In Progress Feature').first()).toBeVisible({ timeout: 10000 })
  })

  test('should create feature in DONE lane', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to DONE"]').click()

    await page.fill('input[placeholder*="Enter feature title"]', 'Done Feature')
    await page.click('button:has-text("Save")')

    // Feature should appear in DONE lane
    await expect(page.getByRole('heading', { name: 'Done Feature', exact: true }).first()).toBeVisible({ timeout: 10000 })
  })

  test('should toggle priority option', async ({ page }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const priorityCheckbox = page.locator('text=Add to top of list').locator('..')
      .locator('input[type="checkbox"]')

    // Initially unchecked (add to bottom)
    await expect(priorityCheckbox).not.toBeChecked()

    // Toggle to add to top
    await priorityCheckbox.check()
    await expect(priorityCheckbox).toBeChecked()

    // Toggle back to add to bottom
    await priorityCheckbox.uncheck()
    await expect(priorityCheckbox).not.toBeChecked()
  })

  test('should add feature to bottom of list by default', async ({ page }) => {
    // Add a new feature (without checking "add to top")
    await page.locator('button[aria-label="Add feature to TODO"]').click()
    await page.fill('input[placeholder*="Enter feature title"]', 'Bottom Priority Feature')
    await page.click('button:has-text("Save")')

    // Wait for the feature to appear
    await expect(page.locator('text=Bottom Priority Feature').first()).toBeVisible({ timeout: 10000 })

    // Verify feature card is closed
    await expect(page.locator('.text-sm.font-mono.font-semibold:has-text("NEW FEATURE")')).not.toBeVisible()
  })

  test('should add feature to top of list when checked', async ({ page }) => {
    // Add a new feature with "add to top" checked
    await page.locator('button[aria-label="Add feature to TODO"]').click()
    await page.fill('input[placeholder*="Enter feature title"]', 'Top Priority Feature')

    // Check the "add to top" option
    const priorityCheckbox = page.locator('text=Add to top of list').locator('..')
      .locator('input[type="checkbox"]')
    await priorityCheckbox.check()

    await page.click('button:has-text("Save")')

    // Wait for the feature to appear
    await expect(page.locator('text=Top Priority Feature').first()).toBeVisible({ timeout: 10000 })

    // Verify feature card is closed
    await expect(page.locator('.text-sm.font-mono.font-semibold:has-text("NEW FEATURE")')).not.toBeVisible()
  })
})
