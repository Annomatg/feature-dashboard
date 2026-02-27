import { test, expect } from '@playwright/test';

const DISABLED_NO_ERROR = {
  enabled: false, current_feature_id: null, current_feature_name: null,
  current_feature_model: null, last_error: null, log: [], budget_exhausted: false,
  budget_limit: 0, features_completed: 0,
};

const DISABLED_WITH_ERROR = {
  enabled: false, current_feature_id: null, current_feature_name: null,
  current_feature_model: null, last_error: 'Claude process exited with code 1', log: [],
  budget_exhausted: false, budget_limit: 0, features_completed: 0,
};

const BUDGET_EXHAUSTED = {
  enabled: false, current_feature_id: null, current_feature_name: null,
  current_feature_model: null, last_error: null, log: [],
  budget_exhausted: true, budget_limit: 3, features_completed: 3,
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

  test('budget exhausted shows green info banner (not red error)', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(BUDGET_EXHAUSTED) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const banner = page.getByTestId('autopilot-error-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute('data-variant', 'budget');
  });

  test('budget exhausted banner shows correct message with feature count', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(BUDGET_EXHAUSTED) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const msg = page.getByTestId('autopilot-error-message');
    await expect(msg).toBeVisible();
    await expect(msg).toContainText('Session budget reached');
    await expect(msg).toContainText('3 features');
  });

  test('budget exhausted banner shows "Session Complete" label', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(BUDGET_EXHAUSTED) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-banner')).toContainText('Session Complete');
  });

  test('normal error still shows red error banner (data-variant=error)', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISABLED_WITH_ERROR) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const banner = page.getByTestId('autopilot-error-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute('data-variant', 'error');
    await expect(banner).toContainText('Auto-Pilot stopped');
  });

  test('budget exhausted banner has a dismiss button that clears it', async ({ page }) => {
    let cleared = false;

    await page.route('**/api/autopilot/status', route => {
      const body = cleared ? DISABLED_NO_ERROR : BUDGET_EXHAUSTED;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.route('**/api/autopilot/clear-error', route => {
      cleared = true;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ cleared: true }) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-banner')).toBeVisible();
    await page.getByTestId('autopilot-error-dismiss').click();
    await expect(page.getByTestId('autopilot-error-banner')).not.toBeVisible({ timeout: 5000 });
  });

  test('budget exhausted banner hidden when autopilot is enabled', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ ...BUDGET_EXHAUSTED, enabled: true }),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-error-banner')).not.toBeVisible();
  });
});
