import { test, expect } from '@playwright/test'

test.describe('Plan Tasks - TODO lane button', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 })
  })

  test('should show plan button in TODO lane header', async ({ page }) => {
    await expect(page.getByTestId('todo-plan-btn')).toBeVisible()
  })

  test('should NOT show plan button in IN PROGRESS lane header', async ({ page }) => {
    // The button has data-testid="todo-plan-btn" and only renders when onPlanClick is provided
    // Verify only one plan button exists (the TODO lane one)
    await expect(page.getByTestId('todo-plan-btn')).toHaveCount(1)
  })

  test('should open PlanTasksModal when clicking plan button in TODO lane', async ({ page }) => {
    await page.getByTestId('todo-plan-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()
  })

  test('plan button in TODO lane opens same modal as header button', async ({ page }) => {
    // Both the header button and the lane button open the same modal
    await page.getByTestId('todo-plan-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()

    // Close it
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()

    // Open via header button
    await page.getByTestId('plan-tasks-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()
  })

  test('plan button in TODO lane is left of the + button', async ({ page }) => {
    const planBtn = page.getByTestId('todo-plan-btn')
    const addBtn = page.locator('button[aria-label="Add feature to TODO"]')

    const planBox = await planBtn.boundingBox()
    const addBox = await addBtn.boundingBox()

    // Plan button x-center should be to the left of add button x-center
    expect(planBox.x + planBox.width / 2).toBeLessThan(addBox.x + addBox.width / 2)
  })

  test('modal from TODO lane button submits to /api/plan-tasks', async ({ page }) => {
    const requestBody = []
    await page.route('/api/plan-tasks', async (route) => {
      const body = route.request().postDataJSON()
      requestBody.push(body)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ launched: true, prompt: 'test', working_directory: '/test' })
      })
    })

    await page.getByTestId('todo-plan-btn').click()
    await page.getByTestId('plan-tasks-description').fill('Plan via lane button')
    await page.getByTestId('plan-tasks-submit').click()

    expect(requestBody.length).toBe(1)
    expect(requestBody[0]).toEqual({ description: 'Plan via lane button' })
    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()
  })
})
