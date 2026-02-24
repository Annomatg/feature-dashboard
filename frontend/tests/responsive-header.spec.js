import { test, expect } from '@playwright/test';

/**
 * Responsive Header Tests
 *
 * Verifies the header layout at portrait mobile widths (375-430px)
 * and desktop widths, ensuring no horizontal overflow and all controls
 * remain accessible.
 */

test.describe('Responsive Header', () => {
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

    test('title is visible', async ({ page }) => {
      await expect(page.getByText('FEATURE DASHBOARD')).toBeVisible();
    });

    test('settings button is visible and accessible', async ({ page }) => {
      await expect(page.getByTestId('settings-btn')).toBeVisible();
    });

    test('plan tasks button is visible and accessible', async ({ page }) => {
      await expect(page.getByTestId('plan-tasks-btn')).toBeVisible();
    });

    test('auto-pilot toggle is visible and accessible', async ({ page }) => {
      await expect(page.getByTestId('autopilot-toggle')).toBeVisible();
    });

    test('mobile stats row is visible', async ({ page }) => {
      await expect(page.getByTestId('header-stats-mobile')).toBeVisible();
    });

    test('desktop stats row is hidden', async ({ page }) => {
      await expect(page.getByTestId('header-stats-desktop')).toBeHidden();
    });

    test('mobile row is visible', async ({ page }) => {
      await expect(page.getByTestId('header-mobile-row')).toBeVisible();
    });

    test('no horizontal scroll / overflow at 375px', async ({ page }) => {
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = 375;
      expect(bodyScrollWidth).toBeLessThanOrEqual(viewportWidth);
    });
  });

  test.describe('Mobile portrait (430px — iPhone Pro Max)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 430, height: 932 });
    });

    test('title is visible', async ({ page }) => {
      await expect(page.getByText('FEATURE DASHBOARD')).toBeVisible();
    });

    test('all action buttons visible', async ({ page }) => {
      await expect(page.getByTestId('settings-btn')).toBeVisible();
      await expect(page.getByTestId('plan-tasks-btn')).toBeVisible();
      await expect(page.getByTestId('autopilot-toggle')).toBeVisible();
    });

    test('no horizontal scroll / overflow at 430px', async ({ page }) => {
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = 430;
      expect(bodyScrollWidth).toBeLessThanOrEqual(viewportWidth);
    });
  });

  test.describe('Desktop (1280px)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
    });

    test('title is visible', async ({ page }) => {
      await expect(page.getByText('FEATURE DASHBOARD')).toBeVisible();
    });

    test('desktop stats row is visible', async ({ page }) => {
      await expect(page.getByTestId('header-stats-desktop')).toBeVisible();
    });

    test('mobile row is hidden on desktop', async ({ page }) => {
      await expect(page.getByTestId('header-mobile-row')).toBeHidden();
    });

    test('all action buttons visible', async ({ page }) => {
      await expect(page.getByTestId('settings-btn')).toBeVisible();
      await expect(page.getByTestId('plan-tasks-btn')).toBeVisible();
      await expect(page.getByTestId('autopilot-toggle')).toBeVisible();
    });
  });

  test.describe('Settings and Plan Tasks work on mobile', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
    });

    test('settings panel opens on mobile', async ({ page }) => {
      await page.getByTestId('settings-btn').click();
      await expect(page.getByTestId('settings-panel')).toBeVisible();
    });
  });
});
