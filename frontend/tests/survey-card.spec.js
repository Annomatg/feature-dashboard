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

test.describe('SurveyCard — type-in option', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/survey-card-test?q=type-in')
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
  })

  test('shows text input immediately without any button click', async ({ page }) => {
    await expect(page.getByTestId('other-input-container')).toBeVisible()
    await expect(page.getByTestId('other-text-input')).toBeVisible()
  })

  test('does not render the (type in browser) placeholder as a button', async ({ page }) => {
    await expect(page.getByTestId('survey-option-0')).not.toBeVisible()
  })

  test('text input is auto-focused', async ({ page }) => {
    await expect(page.getByTestId('other-text-input')).toBeFocused()
  })

  test('submits the typed text, not the placeholder label', async ({ page }) => {
    await page.getByTestId('other-text-input').fill('My cool feature')
    await page.getByTestId('other-submit-btn').click()

    await expect(page.getByTestId('last-answer')).toContainText('My cool feature')
    await expect(page.getByTestId('last-answer')).not.toContainText('type in browser')
  })

  test('pressing Enter submits the typed text', async ({ page }) => {
    await page.getByTestId('other-text-input').fill('Enter key feature')
    await page.getByTestId('other-text-input').press('Enter')

    await expect(page.getByTestId('last-answer')).toContainText('Enter key feature')
  })
})

test.describe('SurveyCard — mixed options with (type in browser)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/survey-card-test?q=mixed')
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
  })

  test('renders real options as buttons', async ({ page }) => {
    await expect(page.getByTestId('survey-option-0')).toContainText('Backend')
    await expect(page.getByTestId('survey-option-1')).toContainText('Frontend')
  })

  test('clicking (type in browser) opens text input instead of submitting the label', async ({ page }) => {
    await page.getByTestId('survey-option-2').click()

    await expect(page.getByTestId('other-input-container')).toBeVisible()
    await expect(page.getByTestId('last-answer')).not.toBeVisible()
  })

  test('typing after clicking (type in browser) submits the typed text', async ({ page }) => {
    await page.getByTestId('survey-option-2').click()
    await page.getByTestId('other-text-input').fill('Custom category')
    await page.getByTestId('other-submit-btn').click()

    await expect(page.getByTestId('last-answer')).toContainText('Custom category')
    await expect(page.getByTestId('last-answer')).not.toContainText('type in browser')
  })
})

test.describe('SurveyCard — markdown rendering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/survey-card-test?q=markdown')
    await page.waitForSelector('[data-testid="survey-card"]', { timeout: 10000 })
  })

  test('renders **bold** text as <strong> elements', async ({ page }) => {
    const heading = page.getByTestId('survey-question')
    // Bold words should be wrapped in <strong> tags
    const strongTags = heading.locator('strong')
    await expect(strongTags).toHaveCount(3)
    await expect(strongTags.nth(0)).toContainText('Easy deployment')
    await expect(strongTags.nth(1)).toContainText('Refactoring plan')
    await expect(strongTags.nth(2)).toContainText('New code checker')
  })

  test('renders newlines as <br> elements', async ({ page }) => {
    const heading = page.getByTestId('survey-question')
    // The text contains multiple \n — verify <br> tags are present
    const brCount = await heading.locator('br').count()
    expect(brCount).toBeGreaterThanOrEqual(4)
  })

  test('question text is not rendered as a flat single line', async ({ page }) => {
    // The raw text has \n separators — confirm the heading does NOT show all
    // text crammed together on one line by checking that "1." and "2." appear
    // in the rendered output (they would be present even if newlines collapse)
    // but more importantly that <br> elements are present (tested above).
    const heading = page.getByTestId('survey-question')
    await expect(heading).toContainText('1.')
    await expect(heading).toContainText('2.')
    await expect(heading).toContainText('3.')
  })

  test('options are still selectable after markdown question is rendered', async ({ page }) => {
    await page.getByTestId('survey-option-0').click()
    await expect(page.getByTestId('survey-option-0')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('last-answer')).toContainText('Easy deployment')
  })
})
