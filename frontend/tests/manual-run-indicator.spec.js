import { test, expect } from '@playwright/test';

const DISABLED_STATUS = {
  enabled: false,
  stopping: false,
  current_feature_id: null,
  current_feature_name: null,
  current_feature_model: null,
  last_error: null,
  log: [],
  manual_active: false,
  manual_feature_id: null,
  manual_feature_name: null,
  manual_feature_model: null,
};

const MANUAL_ACTIVE_STATUS = {
  enabled: false,
  stopping: false,
  current_feature_id: null,
  current_feature_name: null,
  current_feature_model: null,
  last_error: null,
  log: [
    {
      timestamp: new Date().toISOString(),
      level: 'info',
      message: 'Manual launch — feature #7: Add search filter (hidden, sonnet)',
    },
  ],
  manual_active: true,
  manual_feature_id: 7,
  manual_feature_name: 'Add search filter',
  manual_feature_model: 'sonnet',
};

test.describe('Manual Run Indicator', () => {
  test('indicator is hidden when no manual run is active', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DISABLED_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('manual-run-indicator')).not.toBeVisible();
  });

  test('indicator appears when manual_active=true', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MANUAL_ACTIVE_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('manual-run-indicator')).toBeVisible();
  });

  test('indicator shows pulsing dot when active', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MANUAL_ACTIVE_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('manual-run-pulse-dot')).toBeVisible();
  });

  test('indicator shows "Claude Running" label', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MANUAL_ACTIVE_STATUS),
      });
    });

    // Use desktop viewport so label is visible
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('manual-run-indicator')).toContainText('Claude Running');
  });

  test('indicator disappears when manual_active transitions to false', async ({ page }) => {
    let isManualActive = true;

    await page.route('**/api/autopilot/status', route => {
      const body = isManualActive ? MANUAL_ACTIVE_STATUS : DISABLED_STATUS;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Indicator is visible when manual run is active
    await expect(page.getByTestId('manual-run-indicator')).toBeVisible();

    // Simulate process finishing
    isManualActive = false;

    // Indicator should disappear within polling interval (2s when active)
    await expect(page.getByTestId('manual-run-indicator')).not.toBeVisible({ timeout: 8000 });
  });

  test('autopilot toggle is still accessible when manual run is active', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MANUAL_ACTIVE_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Both indicators should be visible side by side
    await expect(page.getByTestId('manual-run-indicator')).toBeVisible();
    await expect(page.getByTestId('autopilot-toggle')).toBeVisible();
  });
});

test.describe('Manual Run Status Bar', () => {
  test('status bar shows "Manual Run" label when manual_active=true and autopilot disabled', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MANUAL_ACTIVE_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const label = page.getByTestId('autopilot-status-label');
    await expect(label).toBeVisible();
    await expect(label).toContainText('Manual Run');
  });

  test('status bar shows feature ID and name during manual run', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MANUAL_ACTIVE_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const featureEl = page.getByTestId('autopilot-status-feature');
    await expect(featureEl).toBeVisible();
    await expect(featureEl).toContainText('#7');
    await expect(featureEl).toContainText('Add search filter');
  });

  test('status bar shows model badge during manual run', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MANUAL_ACTIVE_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-status-model')).toBeVisible();
    await expect(page.getByTestId('autopilot-status-model')).toHaveText('sonnet');
  });

  test('status bar is hidden when neither autopilot nor manual run is active', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DISABLED_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-status-bar')).not.toBeVisible();
  });

  test('status bar shows spinner during manual run', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MANUAL_ACTIVE_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-status-spinner')).toBeVisible();
  });
});

test.describe('Manual Run Event Log', () => {
  test('event log shows manual launch entry', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MANUAL_ACTIVE_STATUS),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Open the log
    await page.getByTestId('autopilot-log-toggle').click();

    // Entry should be visible
    await expect(page.getByTestId('autopilot-log-entries')).toBeVisible();
    const entries = page.getByTestId('autopilot-log-entry');
    await expect(entries).toHaveCount(1);
    await expect(entries.first()).toContainText('Manual launch');
  });
});
