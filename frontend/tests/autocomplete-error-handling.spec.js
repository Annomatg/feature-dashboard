import { test, expect } from '@playwright/test'

/**
 * E2E tests for API error handling in autocomplete.
 *
 * When the /api/autocomplete/* endpoints return HTTP errors (5xx, network failure),
 * the form should continue to work normally without showing any error toasts.
 */

test.describe('Autocomplete API error handling', () => {
  test('name field continues to work when autocomplete API returns 500', async ({ page }) => {
    // Mock the name autocomplete endpoint to return 500
    await page.route('**/api/autocomplete/name*', async route => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' })
    })

    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    // Open the new-feature card
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    await expect(titleInput).toBeVisible()

    // Type 3+ chars to trigger autocomplete fetch
    await titleInput.fill('Fea')

    // Wait for the fetch to complete (and fail)
    await page.waitForTimeout(500)

    // Input should still be functional - can type more
    await titleInput.fill('Feature test name')
    await expect(titleInput).toHaveValue('Feature test name')

    // No ghost text should appear (since API error)
    const ghost = page.locator('[data-testid="name-ghost-text"]')
    await expect(ghost).not.toBeVisible()

    // Verify no error toast messages are visible
    await expect(page.getByText('Internal Server Error', { exact: true })).not.toBeVisible()
  })

  test('description field continues to work when autocomplete API returns 500', async ({ page }) => {
    // Mock the description autocomplete endpoint to return 500
    await page.route('**/api/autocomplete/description*', async route => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' })
    })

    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    // Open the new-feature card
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descInput = page.locator('textarea[placeholder*="Describe"]')
    await expect(descInput).toBeVisible()

    // Type 3+ chars to trigger autocomplete fetch
    await descInput.fill('Tes')

    // Wait for the fetch to complete (and fail)
    await page.waitForTimeout(500)

    // Input should still be functional - can type more
    await descInput.fill('Test description for feature')
    await expect(descInput).toHaveValue('Test description for feature')

    // No ghost text should appear (since API error)
    const ghost = page.locator('[data-testid="description-ghost-text"]')
    await expect(ghost).not.toBeVisible()

    // Verify no error toast messages are visible
    await expect(page.getByText('Internal Server Error', { exact: true })).not.toBeVisible()
  })

  test('both name and description fields work when autocomplete APIs return 500', async ({ page }) => {
    // Mock both autocomplete endpoints to return 500
    await page.route('**/api/autocomplete/name*', async route => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' })
    })
    await page.route('**/api/autocomplete/description*', async route => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' })
    })

    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    // Open the new-feature card
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    const descInput = page.locator('textarea[placeholder*="Describe"]')

    await expect(titleInput).toBeVisible()
    await expect(descInput).toBeVisible()

    // Fill in both fields
    await titleInput.fill('Test feature name')
    await descInput.fill('Test feature description')

    // Verify values are correctly set
    await expect(titleInput).toHaveValue('Test feature name')
    await expect(descInput).toHaveValue('Test feature description')

    // Verify no error toast messages are visible
    await expect(page.getByText('Internal Server Error', { exact: true })).not.toBeVisible()
  })

  test('name field handles network failure gracefully', async ({ page }) => {
    // Mock the name autocomplete endpoint to fail with network error
    await page.route('**/api/autocomplete/name*', async route => {
      await route.abort('failed')
    })

    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    // Open the new-feature card
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')

    // Type 3+ chars to trigger autocomplete fetch
    await titleInput.fill('Fea')

    // Wait for the fetch to fail
    await page.waitForTimeout(500)

    // Input should still be functional
    await titleInput.fill('Feature after network error')
    await expect(titleInput).toHaveValue('Feature after network error')

    // No error messages should be visible (network errors don't have a specific message to check)
    // The form works which is the main verification
  })

  test('description field handles network failure gracefully', async ({ page }) => {
    // Mock the description autocomplete endpoint to fail with network error
    await page.route('**/api/autocomplete/description*', async route => {
      await route.abort('failed')
    })

    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    // Open the new-feature card
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const descInput = page.locator('textarea[placeholder*="Describe"]')

    // Type 3+ chars to trigger autocomplete fetch
    await descInput.fill('Tes')

    // Wait for the fetch to fail
    await page.waitForTimeout(500)

    // Input should still be functional
    await descInput.fill('Description after network error')
    await expect(descInput).toHaveValue('Description after network error')

    // No error messages should be visible (network errors don't have a specific message to check)
    // The form works which is the main verification
  })

  test('typing continues to work after multiple autocomplete failures', async ({ page }) => {
    // Mock both autocomplete endpoints to return 500
    await page.route('**/api/autocomplete/name*', async route => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' })
    })
    await page.route('**/api/autocomplete/description*', async route => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' })
    })

    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD')

    // Open the new-feature card
    await page.locator('button[aria-label="Add feature to TODO"]').click()

    const titleInput = page.locator('input[placeholder*="Enter feature title"]')
    const descInput = page.locator('textarea[placeholder*="Describe"]')

    // Type and trigger multiple autocomplete requests
    await titleInput.fill('Fea')
    await page.waitForTimeout(300)
    await titleInput.fill('Feat')
    await page.waitForTimeout(300)
    await titleInput.fill('Feature')
    await page.waitForTimeout(300)

    await descInput.fill('Tes')
    await page.waitForTimeout(300)
    await descInput.fill('Test')
    await page.waitForTimeout(300)

    // Both fields should still be functional with correct values
    await expect(titleInput).toHaveValue('Feature')
    await expect(descInput).toHaveValue('Test')

    // Can continue typing
    await titleInput.fill('Feature with more text')
    await descInput.fill('Test with more text')

    await expect(titleInput).toHaveValue('Feature with more text')
    await expect(descInput).toHaveValue('Test with more text')
  })
})
