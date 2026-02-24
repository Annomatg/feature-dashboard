import { test, expect } from '@playwright/test';

/**
 * Mobile Kanban Layout Tests
 *
 * Verifies the tab-based lane switcher at portrait mobile widths (375-430px)
 * and that the 3-column grid layout is preserved on desktop.
 */

test.describe('Mobile Kanban Layout', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept autopilot status to avoid backend dependency
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: false, current_feature_id: null, current_feature_name: null, last_error: null, log: [] }),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
  });

  test.describe('Mobile portrait (375px — iPhone SE)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
    });

    test('tab bar is visible', async ({ page }) => {
      await expect(page.getByTestId('mobile-lane-tabs')).toBeVisible();
    });

    test('all three lane tabs are rendered', async ({ page }) => {
      await expect(page.getByTestId('lane-tab-todo')).toBeVisible();
      await expect(page.getByTestId('lane-tab-inProgress')).toBeVisible();
      await expect(page.getByTestId('lane-tab-done')).toBeVisible();
    });

    test('TODO tab is active by default', async ({ page }) => {
      // Active tab has a colored border (not #3d3d3d)
      const todoTab = page.getByTestId('lane-tab-todo');
      const style = await todoTab.getAttribute('style');
      expect(style).not.toContain('#3d3d3d');
    });

    test('TODO lane content is visible by default, others hidden', async ({ page }) => {
      // The TODO lane content (title "TODO") should be visible
      const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
      await expect(todoTitle.first()).toBeVisible();

      // IN PROGRESS and DONE lane titles should NOT be visible
      const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
      const doneTitle = page.locator('h2').filter({ hasText: 'DONE' });
      await expect(inProgressTitle).toBeHidden();
      await expect(doneTitle).toBeHidden();
    });

    test('clicking IN PROGRESS tab shows that lane', async ({ page }) => {
      await page.getByTestId('lane-tab-inProgress').click();

      const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
      await expect(inProgressTitle).toBeVisible();

      // TODO should now be hidden
      const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
      await expect(todoTitle).toBeHidden();
    });

    test('clicking DONE tab shows that lane', async ({ page }) => {
      await page.getByTestId('lane-tab-done').click();

      const doneTitle = page.locator('h2').filter({ hasText: 'DONE' });
      await expect(doneTitle).toBeVisible();

      // TODO should now be hidden
      const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
      await expect(todoTitle).toBeHidden();
    });

    test('can switch back to TODO tab after switching away', async ({ page }) => {
      // Switch to DONE
      await page.getByTestId('lane-tab-done').click();
      const doneTitle = page.locator('h2').filter({ hasText: 'DONE' });
      await expect(doneTitle).toBeVisible();

      // Switch back to TODO
      await page.getByTestId('lane-tab-todo').click();
      const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
      await expect(todoTitle).toBeVisible();
      await expect(doneTitle).toBeHidden();
    });

    test('no horizontal scroll / overflow at 375px', async ({ page }) => {
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(375);
    });

    test('tab labels contain lane title text', async ({ page }) => {
      await expect(page.getByTestId('lane-tab-todo')).toContainText('TODO');
      await expect(page.getByTestId('lane-tab-inProgress')).toContainText('IN PROGRESS');
      await expect(page.getByTestId('lane-tab-done')).toContainText('DONE');
    });
  });

  test.describe('Mobile portrait (430px — iPhone Pro Max)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 430, height: 932 });
    });

    test('tab bar is visible', async ({ page }) => {
      await expect(page.getByTestId('mobile-lane-tabs')).toBeVisible();
    });

    test('no horizontal scroll / overflow at 430px', async ({ page }) => {
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(430);
    });

    test('switching tabs works at 430px', async ({ page }) => {
      await page.getByTestId('lane-tab-inProgress').click();
      const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
      await expect(inProgressTitle).toBeVisible();
    });
  });

  test.describe('Desktop (1280px)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
    });

    test('tab bar is hidden on desktop', async ({ page }) => {
      await expect(page.getByTestId('mobile-lane-tabs')).toBeHidden();
    });

    test('all three lane titles are visible simultaneously', async ({ page }) => {
      const todoTitle = page.locator('h2').filter({ hasText: 'TODO' });
      const inProgressTitle = page.locator('h2').filter({ hasText: 'IN PROGRESS' });
      const doneTitle = page.locator('h2').filter({ hasText: 'DONE' });

      await expect(todoTitle.first()).toBeVisible();
      await expect(inProgressTitle.first()).toBeVisible();
      await expect(doneTitle.first()).toBeVisible();
    });

    test('no horizontal scroll on desktop', async ({ page }) => {
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(1280);
    });
  });
});
