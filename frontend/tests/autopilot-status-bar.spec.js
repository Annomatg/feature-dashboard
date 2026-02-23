import { test, expect } from '@playwright/test';

const DISABLED_STATUS = {
  enabled: false, current_feature_id: null, current_feature_name: null,
  current_feature_model: null, last_error: null, log: [],
};

const ENABLED_STATUS = {
  enabled: true, current_feature_id: 42, current_feature_name: 'Build the rocket',
  current_feature_model: 'sonnet', last_error: null, log: [],
};

test.describe('Auto-Pilot Status Bar', () => {
  test('status bar is hidden when auto-pilot is disabled', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_STATUS) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-status-bar')).not.toBeVisible();
  });

  test('status bar appears when auto-pilot is enabled', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ENABLED_STATUS) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-status-bar')).toBeVisible();
  });

  test('status bar shows feature ID and name', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ENABLED_STATUS) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const featureEl = page.getByTestId('autopilot-status-feature');
    await expect(featureEl).toBeVisible();
    await expect(featureEl).toContainText('#42');
    await expect(featureEl).toContainText('Build the rocket');
  });

  test('status bar shows model badge', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ENABLED_STATUS) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-status-model')).toBeVisible();
    await expect(page.getByTestId('autopilot-status-model')).toHaveText('sonnet');
  });

  test('status bar shows spinning loader', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ENABLED_STATUS) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-status-spinner')).toBeVisible();
  });

  test('status bar updates when feature changes', async ({ page }) => {
    // Use a mutable flag flipped AFTER we confirm the first feature is visible,
    // so React StrictMode's double-render burst doesn't prematurely advance state.
    const routeState = { showSecond: false };

    await page.route('**/api/autopilot/status', route => {
      const body = routeState.showSecond
        ? { ...ENABLED_STATUS, current_feature_id: 55, current_feature_name: 'Launch the rocket' }
        : { ...ENABLED_STATUS, current_feature_id: 42, current_feature_name: 'Build the rocket' };
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Confirm initial feature is showing
    await expect(page.getByTestId('autopilot-status-feature')).toContainText('#42');
    await expect(page.getByTestId('autopilot-status-feature')).toContainText('Build the rocket');

    // Now flip to the next feature — the 2s poll will pick it up
    routeState.showSecond = true;

    await expect(page.getByTestId('autopilot-status-feature')).toContainText('#55', { timeout: 8000 });
    await expect(page.getByTestId('autopilot-status-feature')).toContainText('Launch the rocket');
  });

  test('status bar disappears when auto-pilot is disabled', async ({ page }) => {
    let statusEnabled = true;

    await page.route('**/api/autopilot/status', route => {
      const body = statusEnabled ? ENABLED_STATUS : DISABLED_STATUS;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.route('**/api/autopilot/disable', route => {
      statusEnabled = false;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_STATUS) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Bar is visible initially
    await expect(page.getByTestId('autopilot-status-bar')).toBeVisible();

    // Click the toggle to disable
    await page.getByTestId('autopilot-toggle').click();

    // Bar should disappear
    await expect(page.getByTestId('autopilot-status-bar')).not.toBeVisible({ timeout: 5000 });
  });

  test('opus model badge shows correct colour class', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ ...ENABLED_STATUS, current_feature_model: 'claude-opus-4-6' }),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const badge = page.getByTestId('autopilot-status-model');
    await expect(badge).toHaveText('opus');
    const cls = await badge.getAttribute('class');
    expect(cls).toContain('text-purple-300');
  });

  test('haiku model badge shows correct colour class', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ ...ENABLED_STATUS, current_feature_model: 'claude-haiku-4-5' }),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const badge = page.getByTestId('autopilot-status-model');
    await expect(badge).toHaveText('haiku');
    const cls = await badge.getAttribute('class');
    expect(cls).toContain('text-success');
  });
});
