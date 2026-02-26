import { test, expect } from '@playwright/test';

/**
 * Mobile Swipe Lane Tests
 *
 * Verifies that swiping left/right on the kanban lanes container switches the
 * active mobile lane (todo ↔ inProgress ↔ done) at portrait mobile widths.
 *
 * We simulate the swipe by dispatching synthetic TouchEvent sequences via
 * page.evaluate(), since Playwright does not have a built-in swipe API for
 * touch events on arbitrary elements.
 */

/**
 * Simulate a horizontal swipe on the given element.
 * @param {import('@playwright/test').Page} page
 * @param {string} selector - CSS selector for the element to swipe
 * @param {number} deltaX   - Pixels to swipe: negative = left, positive = right
 */
async function swipe(page, selector, deltaX) {
  await page.evaluate(({ selector, deltaX }) => {
    const el = document.querySelector(selector);
    if (!el) throw new Error(`Element not found: ${selector}`);

    const rect = el.getBoundingClientRect();
    const startX = rect.left + rect.width / 2;
    const startY = rect.top + rect.height / 2;
    const endX = startX + deltaX;

    const mkTouch = (x, y) => new Touch({ identifier: 1, target: el, clientX: x, clientY: y });

    el.dispatchEvent(new TouchEvent('touchstart', {
      bubbles: true, cancelable: true,
      touches: [mkTouch(startX, startY)],
      changedTouches: [mkTouch(startX, startY)],
    }));
    el.dispatchEvent(new TouchEvent('touchend', {
      bubbles: true, cancelable: true,
      touches: [],
      changedTouches: [mkTouch(endX, startY)],
    }));
  }, { selector, deltaX });
}

test.describe('Mobile Swipe Lane Switching', () => {
  test.beforeEach(async ({ page }) => {
    // Stub autopilot status
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: false, current_feature_id: null, current_feature_name: null, last_error: null, log: [] }),
      });
    });

    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
  });

  test('swipe left on TODO advances to IN PROGRESS', async ({ page }) => {
    // Confirm we start on TODO
    await expect(page.getByTestId('lane-tab-todo')).toBeVisible();
    const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
    await expect(todoTitle.first()).toBeVisible();

    // Swipe left (negative dx)
    await swipe(page, '[data-testid="kanban-lanes"]', -100);

    // IN PROGRESS lane should now be visible
    const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
    await expect(inProgressTitle).toBeVisible();
    await expect(todoTitle).toBeHidden();
  });

  test('swipe left on IN PROGRESS advances to DONE', async ({ page }) => {
    // Navigate to IN PROGRESS first
    await page.getByTestId('lane-tab-inProgress').click();
    const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
    await expect(inProgressTitle).toBeVisible();

    // Swipe left
    await swipe(page, '[data-testid="kanban-lanes"]', -100);

    const doneTitle = page.locator('h2').filter({ hasText: 'DONE' });
    await expect(doneTitle).toBeVisible();
    await expect(inProgressTitle).toBeHidden();
  });

  test('swipe right on DONE goes back to IN PROGRESS', async ({ page }) => {
    // Navigate to DONE first
    await page.getByTestId('lane-tab-done').click();
    const doneTitle = page.locator('h2').filter({ hasText: 'DONE' });
    await expect(doneTitle).toBeVisible();

    // Swipe right (positive dx)
    await swipe(page, '[data-testid="kanban-lanes"]', 100);

    const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
    await expect(inProgressTitle).toBeVisible();
    await expect(doneTitle).toBeHidden();
  });

  test('swipe right on IN PROGRESS goes back to TODO', async ({ page }) => {
    // Navigate to IN PROGRESS
    await page.getByTestId('lane-tab-inProgress').click();
    const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
    await expect(inProgressTitle).toBeVisible();

    // Swipe right
    await swipe(page, '[data-testid="kanban-lanes"]', 100);

    const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
    await expect(todoTitle.first()).toBeVisible();
    await expect(inProgressTitle).toBeHidden();
  });

  test('swipe left on DONE does nothing (already at last lane)', async ({ page }) => {
    await page.getByTestId('lane-tab-done').click();
    const doneTitle = page.locator('h2').filter({ hasText: 'DONE' });
    await expect(doneTitle).toBeVisible();

    // Swipe left — no lane to advance to
    await swipe(page, '[data-testid="kanban-lanes"]', -100);

    // Should still show DONE
    await expect(doneTitle).toBeVisible();
  });

  test('swipe right on TODO does nothing (already at first lane)', async ({ page }) => {
    const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
    await expect(todoTitle.first()).toBeVisible();

    // Swipe right — no previous lane
    await swipe(page, '[data-testid="kanban-lanes"]', 100);

    // Should still show TODO
    await expect(todoTitle.first()).toBeVisible();
  });

  test('short swipe (below threshold) does not switch lane', async ({ page }) => {
    const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
    await expect(todoTitle.first()).toBeVisible();

    // Swipe only 30px — below the 60px threshold
    await swipe(page, '[data-testid="kanban-lanes"]', -30);

    // Should still be on TODO
    await expect(todoTitle.first()).toBeVisible();
  });

  test('mostly-vertical gesture does not switch lane', async ({ page }) => {
    const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
    await expect(todoTitle.first()).toBeVisible();

    // Simulate a diagonal swipe that is mostly vertical
    await page.evaluate(({ selector }) => {
      const el = document.querySelector(selector);
      const rect = el.getBoundingClientRect();
      const startX = rect.left + rect.width / 2;
      const startY = rect.top + rect.height / 2;
      // 80px horizontal but 100px vertical — ratio 100/80 = 1.25 > MAX_VERTICAL_RATIO (0.6)
      const endX = startX - 80;
      const endY = startY + 100;

      const mkTouch = (x, y) => new Touch({ identifier: 1, target: el, clientX: x, clientY: y });

      el.dispatchEvent(new TouchEvent('touchstart', {
        bubbles: true, cancelable: true,
        touches: [mkTouch(startX, startY)],
        changedTouches: [mkTouch(startX, startY)],
      }));
      el.dispatchEvent(new TouchEvent('touchend', {
        bubbles: true, cancelable: true,
        touches: [],
        changedTouches: [mkTouch(endX, endY)],
      }));
    }, { selector: '[data-testid="kanban-lanes"]' });

    // Should still be on TODO
    await expect(todoTitle.first()).toBeVisible();
    const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
    await expect(inProgressTitle).toBeHidden();
  });

  test('swipe works at 430px width too', async ({ page }) => {
    await page.setViewportSize({ width: 430, height: 932 });

    const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
    await expect(todoTitle.first()).toBeVisible();

    await swipe(page, '[data-testid="kanban-lanes"]', -100);

    const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
    await expect(inProgressTitle).toBeVisible();
  });
});
