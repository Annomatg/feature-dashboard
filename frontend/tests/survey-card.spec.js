import { test, expect } from '@playwright/test'

test.describe('SurveyCard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/survey-card-test')
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
  })

  test('renders question text as a heading', async ({ page }) => {
    const heading = page.getByTestId('survey-question')
    await expect(heading).toBeVisible()
    await expect(heading).toContainText('Which frontend framework do you prefer?')
  })

  test('renders all option buttons with min height >= 56px', async ({ page }) => {
    // Verify 4 named options + Other button exist
    await expect(page.getByTestId('survey-option-0')).toBeVisible()
    await expect(page.getByTestId('survey-option-1')).toBeVisible()
    await expect(page.getByTestId('survey-option-2')).toBeVisible()
    await expect(page.getByTestId('survey-option-3')).toBeVisible()
    await expect(page.getByTestId('survey-option-other')).toBeVisible()

    // Check that each option meets the min-height requirement
    for (let i = 0; i < 4; i++) {
      const btn = page.getByTestId(`survey-option-${i}`)
      const box = await btn.boundingBox()
      expect(box.height).toBeGreaterThanOrEqual(56)
    }
  })

  test('option text matches the sample question options', async ({ page }) => {
    await expect(page.getByTestId('survey-option-0')).toContainText('React')
    await expect(page.getByTestId('survey-option-1')).toContainText('Vue')
    await expect(page.getByTestId('survey-option-2')).toContainText('Svelte')
    await expect(page.getByTestId('survey-option-3')).toContainText('Angular')
    await expect(page.getByTestId('survey-option-other')).toContainText('Other')
  })

  test('selecting an option highlights it with accent color', async ({ page }) => {
    const btn = page.getByTestId('survey-option-1') // Vue
    await btn.click()

    // aria-pressed should be true after selection
    await expect(btn).toHaveAttribute('aria-pressed', 'true')
  })

  test('selecting an option disables all other options', async ({ page }) => {
    await page.getByTestId('survey-option-0').click() // React

    // Other options should be disabled
    await expect(page.getByTestId('survey-option-1')).toBeDisabled()
    await expect(page.getByTestId('survey-option-2')).toBeDisabled()
    await expect(page.getByTestId('survey-option-3')).toBeDisabled()
    await expect(page.getByTestId('survey-option-other')).toBeDisabled()

    // Selected option itself stays enabled (aria-pressed=true, not disabled)
    await expect(page.getByTestId('survey-option-0')).not.toBeDisabled()
  })

  test('selecting an option calls onAnswer and displays the answer', async ({ page }) => {
    await page.getByTestId('survey-option-2').click() // Svelte

    const answerEl = page.getByTestId('last-answer')
    await expect(answerEl).toBeVisible()
    await expect(answerEl).toContainText('Svelte')
  })

  test('double-clicking an option does not submit twice', async ({ page }) => {
    const btn = page.getByTestId('survey-option-0')
    await btn.dblclick()

    // Answer should still show exactly once
    const answerEl = page.getByTestId('last-answer')
    await expect(answerEl).toBeVisible()
    await expect(answerEl).toContainText('React')

    // Selected button stays selected (not un-selected)
    await expect(btn).toHaveAttribute('aria-pressed', 'true')
  })

  test('Other option reveals a text input when selected', async ({ page }) => {
    // Text input should not be visible initially
    await expect(page.getByTestId('other-input-container')).not.toBeVisible()

    // Select Other
    await page.getByTestId('survey-option-other').click()

    // Free-text input and submit button should now appear
    await expect(page.getByTestId('other-input-container')).toBeVisible()
    await expect(page.getByTestId('other-text-input')).toBeVisible()
    await expect(page.getByTestId('other-submit-btn')).toBeVisible()
  })

  test('Other: submit button is disabled while input is empty', async ({ page }) => {
    await page.getByTestId('survey-option-other').click()

    const submitBtn = page.getByTestId('other-submit-btn')
    await expect(submitBtn).toBeDisabled()
  })

  test('Other: submit button enables after typing text', async ({ page }) => {
    await page.getByTestId('survey-option-other').click()
    await page.getByTestId('other-text-input').fill('My custom answer')

    const submitBtn = page.getByTestId('other-submit-btn')
    await expect(submitBtn).toBeEnabled()
  })

  test('Other: clicking Submit sends free-text answer', async ({ page }) => {
    await page.getByTestId('survey-option-other').click()
    await page.getByTestId('other-text-input').fill('Something else entirely')
    await page.getByTestId('other-submit-btn').click()

    const answerEl = page.getByTestId('last-answer')
    await expect(answerEl).toBeVisible()
    await expect(answerEl).toContainText('Something else entirely')
  })

  test('Other: pressing Enter in the text input submits the answer', async ({ page }) => {
    await page.getByTestId('survey-option-other').click()
    await page.getByTestId('other-text-input').fill('Entered via keyboard')
    await page.getByTestId('other-text-input').press('Enter')

    const answerEl = page.getByTestId('last-answer')
    await expect(answerEl).toBeVisible()
    await expect(answerEl).toContainText('Entered via keyboard')
  })

  test('Other: all options are disabled after free-text submit', async ({ page }) => {
    await page.getByTestId('survey-option-other').click()
    await page.getByTestId('other-text-input').fill('Custom answer')
    await page.getByTestId('other-submit-btn').click()

    // Regular options should be disabled
    for (let i = 0; i < 4; i++) {
      await expect(page.getByTestId(`survey-option-${i}`)).toBeDisabled()
    }
    // Other-submit button should be disabled too
    await expect(page.getByTestId('other-submit-btn')).toBeDisabled()
  })

  test('Other: text input auto-focuses when Other is selected', async ({ page }) => {
    await page.getByTestId('survey-option-other').click()
    await expect(page.getByTestId('other-text-input')).toBeFocused()
  })
})
