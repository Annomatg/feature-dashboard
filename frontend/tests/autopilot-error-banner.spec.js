import { test, expect } from '@playwright/test';

const DISABLED_NO_ERROR = {
  enabled: false, current_feature_id: null, current_feature_name: null,
  current_feature_model: null, last_error: null, log: [],
};

const DISABLED_WITH_ERROR = {
  enabled: false, current_feature_id: null, current_feature_name: null,
  current_feature_model: null, last_error: 'Claude process exited with code 1', log: [],
};

const ENABLED_NO_ERROR = {
  enabled: true, current_feature_id: 42, current_feature_name: 'Build the rocket',
  current_feature_model: 'sonnet', last_error: null, log: [],
};

test.describe('Auto-Pilot Error Banner', () => {
  test('error banner is hidden when auto-pilot is disabled with no error', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_NO_ERROR) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-banner')).not.toBeVisible();
  });

  test('error banner is hidden when auto-pilot is enabled (even with last_error)', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ ...ENABLED_NO_ERROR, last_error: 'Some old error' }),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-banner')).not.toBeVisible();
  });

  test('error banner appears when auto-pilot is disabled with last_error set', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_WITH_ERROR) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-banner')).toBeVisible();
  });

  test('error banner shows warning icon', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_WITH_ERROR) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-icon')).toBeVisible();
  });

  test('error banner shows "Auto-Pilot stopped" label', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_WITH_ERROR) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-banner')).toContainText('Auto-Pilot stopped');
  });

  test('error banner shows the error message text', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_WITH_ERROR) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const messageEl = page.getByTestId('autopilot-error-message');
    await expect(messageEl).toBeVisible();
    await expect(messageEl).toHaveText('Claude process exited with code 1');
  });

  test('error banner has a dismiss (X) button', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_WITH_ERROR) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-dismiss')).toBeVisible();
  });

  test('dismiss button calls clear-error endpoint and hides the banner', async ({ page }) => {
    let errorCleared = false;

    await page.route('**/api/autopilot/status', route => {
      const body = errorCleared ? DISABLED_NO_ERROR : DISABLED_WITH_ERROR;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.route('**/api/autopilot/clear-error', route => {
      errorCleared = true;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ cleared: true }) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Banner is visible initially
    await expect(page.getByTestId('autopilot-error-banner')).toBeVisible();

    // Click dismiss
    await page.getByTestId('autopilot-error-dismiss').click();

    // Banner should disappear after clear-error + status re-fetch
    await expect(page.getByTestId('autopilot-error-banner')).not.toBeVisible({ timeout: 5000 });
  });

  test('error banner is not shown after clean completion (last_error=null)', async ({ page }) => {
    // Simulate: auto-pilot finished cleanly (disabled, no error)
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_NO_ERROR) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-banner')).not.toBeVisible();
  });

  test('status bar is hidden while error banner is visible', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_WITH_ERROR) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Status bar (for active feature) should be hidden because enabled=false
    await expect(page.getByTestId('autopilot-status-bar')).not.toBeVisible();

    // Error banner should be visible
    await expect(page.getByTestId('autopilot-error-banner')).toBeVisible();
  });
});
