/**
 * E2E tests for Plan Tasks feature — covers all 6 acceptance steps:
 * 1. Plan button visible in TODO lane header
 * 2. Plan button NOT visible in IN PROGRESS or DONE lanes
 * 3. Clicking Plan button opens the PlanTasksModal
 * 4. Modal has a text area and submit button
 * 5. Modal closes on ESC key or backdrop click
 * 6. Submit with empty description is blocked (button disabled)
 */
import { test, expect } from '@playwright/test'

test.describe('Plan Tasks - E2E acceptance tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 })
  })

  // Step 1: Plan button visible in TODO lane header
  test('Plan button is visible in the TODO lane header', async ({ page }) => {
    await expect(page.getByTestId('todo-plan-btn')).toBeVisible()
  })

  // Step 2: Plan button NOT visible in IN PROGRESS or DONE lanes
  test('Plan button is NOT present in IN PROGRESS lane header', async ({ page }) => {
    // Only the TODO lane gets onPlanClick, so the data-testid should appear exactly once
    await expect(page.getByTestId('todo-plan-btn')).toHaveCount(1)

    // Confirm IN PROGRESS add button exists (lane is rendered) but no plan button alongside it
    const inProgressAddBtn = page.locator('button[aria-label="Add feature to IN PROGRESS"]')
    await expect(inProgressAddBtn).toBeVisible()

    // The plan button should not be adjacent to the IN PROGRESS add button.
    // We verify by checking the plan button's aria-label only appears once.
    const planButtons = page.locator('button[aria-label="Plan tasks with Claude"]')
    // Header button + TODO lane button = 2 total; none in IN PROGRESS or DONE
    await expect(planButtons).toHaveCount(2)
  })

  test('Plan button is NOT present in DONE lane header', async ({ page }) => {
    const doneAddBtn = page.locator('button[aria-label="Add feature to DONE"]')
    await expect(doneAddBtn).toBeVisible()

    // Still only 2 plan buttons (header + TODO lane)
    const planButtons = page.locator('button[aria-label="Plan tasks with Claude"]')
    await expect(planButtons).toHaveCount(2)
  })

  // Step 3: Clicking Plan button opens the PlanTasksModal
  test('Clicking Plan button in TODO lane opens the PlanTasksModal', async ({ page }) => {
    await page.getByTestId('todo-plan-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()
  })

  // Step 4: Modal has a text area and submit button
  test('Modal has a textarea and submit button', async ({ page }) => {
    await page.getByTestId('todo-plan-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()

    await expect(page.getByTestId('plan-tasks-description')).toBeVisible()
    await expect(page.getByTestId('plan-tasks-submit')).toBeVisible()
  })

  // Step 5: Modal closes on ESC key or backdrop click
  test('Modal closes when pressing ESC', async ({ page }) => {
    await page.getByTestId('todo-plan-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()
  })

  test('Modal closes when clicking backdrop', async ({ page }) => {
    await page.getByTestId('todo-plan-btn').click()
    await expect(page.getByTestId('plan-tasks-modal')).toBeVisible()

    await page.getByTestId('plan-tasks-backdrop').click({ position: { x: 10, y: 10 } })
    await expect(page.getByTestId('plan-tasks-modal')).not.toBeVisible()
  })

  // Step 6: Submit with empty description is blocked (disabled button = validation)
  test('Submit button is disabled when description is empty', async ({ page }) => {
    await page.getByTestId('todo-plan-btn').click()
    await expect(page.getByTestId('plan-tasks-submit')).toBeDisabled()
  })

  test('Submit button is disabled when description is only whitespace', async ({ page }) => {
    await page.getByTestId('todo-plan-btn').click()
    await page.getByTestId('plan-tasks-description').fill('   ')
    await expect(page.getByTestId('plan-tasks-submit')).toBeDisabled()
  })

  test('Submit button becomes enabled when description has content', async ({ page }) => {
    await page.getByTestId('todo-plan-btn').click()
    await page.getByTestId('plan-tasks-description').fill('Plan some features')
    await expect(page.getByTestId('plan-tasks-submit')).not.toBeDisabled()
  })
})
