import { test, expect } from '@playwright/test'

test.describe('Plan Tasks Modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 })
  })

  test('should show plan tasks button in header', async ({ page }) => {
    await expect(page.getByTestId('plan-tasks-btn')).toBeVisible()
  })

  test('should open modal when clicking plan tasks button', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()
  })

  test('should close modal when clicking X button', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()

    await page.getByTestId('plan-tasks-close').click()
    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()
  })

  test('should close modal when pressing Escape', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()
  })

  test('should close modal when clicking backdrop', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()

    // Click the backdrop area (outside the modal panel)
    await page.getByTestId('plan-tasks-backdrop').click({ position: { x: 10, y: 10 } })
    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()
  })

  test('should close modal when clicking Cancel button', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()

    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()
  })

  test('should show description textarea', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()
    await expect(page.getByTestId('plan-tasks-description')).toBeVisible()
  })

  test('should auto-focus textarea when modal opens', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()
    await expect(page.getByTestId('plan-tasks-description')).toBeFocused()
  })

  test('should have submit button disabled when description is empty', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()
    await expect(page.getByTestId('plan-tasks-submit')).toBeDisabled()
  })

  test('should enable submit button when description has content', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()

    await page.getByTestId('plan-tasks-description').fill('Plan some new features')
    await expect(page.getByTestId('plan-tasks-submit')).not.toBeDisabled()
  })

  test('should disable submit button when description is only whitespace', async ({ page }) => {
    await page.getByTestId('plan-tasks-btn').click()

    await page.getByTestId('plan-tasks-description').fill('   ')
    await expect(page.getByTestId('plan-tasks-submit')).toBeDisabled()
  })

  test('should call POST /api/plan-tasks with description on submit', async ({ page }) => {
    // Intercept the API call
    const requestBody = []
    await page.route('/api/plan-tasks', async (route) => {
      const body = route.request().postDataJSON()
      requestBody.push(body)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ launched: true, prompt: 'test prompt', working_directory: '/test' })
      })
    })

    await page.getByTestId('plan-tasks-btn').click()
    await page.getByTestId('plan-tasks-description').fill('Add user authentication')
    await page.getByTestId('plan-tasks-submit').click()

    expect(requestBody.length).toBe(1)
    expect(requestBody[0]).toEqual({ description: 'Add user authentication' })
  })

  test('should close modal after successful submission', async ({ page }) => {
    await page.route('/api/plan-tasks', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ launched: true, prompt: 'test prompt', working_directory: '/test' })
      })
    })

    await page.getByTestId('plan-tasks-btn').click()
    await page.getByTestId('plan-tasks-description').fill('Plan new features')
    await page.getByTestId('plan-tasks-submit').click()

    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()
  })

  test('should show success toast after successful submission', async ({ page }) => {
    await page.route('/api/plan-tasks', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ launched: true, prompt: 'test prompt', working_directory: '/test' })
      })
    })

    await page.getByTestId('plan-tasks-btn').click()
    await page.getByTestId('plan-tasks-description').fill('Plan new features')
    await page.getByTestId('plan-tasks-submit').click()

    await expect(page.getByText('Planning session launched', { exact: true })).toBeVisible()
  })

  test('should show error toast on API failure', async ({ page }) => {
    await page.route('/api/plan-tasks', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Claude CLI not found' })
      })
    })

    await page.getByTestId('plan-tasks-btn').click()
    await page.getByTestId('plan-tasks-description').fill('Plan new features')
    await page.getByTestId('plan-tasks-submit').click()

    await expect(page.getByText('Claude CLI not found', { exact: true })).toBeVisible()
  })

  test('should keep modal open on API failure', async ({ page }) => {
    await page.route('/api/plan-tasks', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Claude CLI not found' })
      })
    })

    await page.getByTestId('plan-tasks-btn').click()
    await page.getByTestId('plan-tasks-description').fill('Plan new features')
    await page.getByTestId('plan-tasks-submit').click()

    // Modal should still be visible after error
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()
  })

  test('should submit with Ctrl+Enter shortcut', async ({ page }) => {
    const requestBody = []
    await page.route('/api/plan-tasks', async (route) => {
      const body = route.request().postDataJSON()
      requestBody.push(body)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ launched: true, prompt: 'test prompt', working_directory: '/test' })
      })
    })

    await page.getByTestId('plan-tasks-btn').click()
    const textarea = page.getByTestId('plan-tasks-description')
    await textarea.fill('Plan via keyboard shortcut')
    await textarea.press('Control+Enter')

    expect(requestBody.length).toBe(1)
    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()
  })
})
