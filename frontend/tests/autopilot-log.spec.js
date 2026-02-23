import { test, expect } from '@playwright/test';

const DISABLED_STATUS = {
  enabled: false, current_feature_id: null, current_feature_name: null,
  current_feature_model: null, last_error: null, log: [],
};

const STATUS_WITH_LOG = {
  enabled: false, current_feature_id: null, current_feature_name: null,
  current_feature_model: null, last_error: null,
  log: [
    { timestamp: '2026-02-23T10:00:01.000000+00:00', level: 'info',    message: 'Auto-pilot enabled' },
    { timestamp: '2026-02-23T10:00:05.000000+00:00', level: 'success', message: 'Feature #42 complete' },
    { timestamp: '2026-02-23T10:00:09.000000+00:00', level: 'error',   message: 'Feature #43 failed: exit 1' },
  ],
};

async function gotoWithStatus(page, status) {
  await page.route('**/api/autopilot/status', route => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(status) });
  });
  await page.goto('/');
  await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
}

test.describe('AutoPilotLog panel', () => {
  test('log panel is always rendered (even when autopilot disabled)', async ({ page }) => {
    await gotoWithStatus(page, DISABLED_STATUS);
    await expect(page.getByTestId('autopilot-log-panel')).toBeVisible();
  });

  test('log panel is collapsed by default — entries not visible', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await expect(page.getByTestId('autopilot-log-entries')).not.toBeVisible();
  });

  test('clicking toggle opens the log panel', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await page.getByTestId('autopilot-log-toggle').click();
    await expect(page.getByTestId('autopilot-log-entries')).toBeVisible();
  });

  test('clicking toggle again closes the log panel', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);

    await page.getByTestId('autopilot-log-toggle').click();
    await expect(page.getByTestId('autopilot-log-entries')).toBeVisible();

    await page.getByTestId('autopilot-log-toggle').click();
    await expect(page.getByTestId('autopilot-log-entries')).not.toBeVisible();
  });

  test('shows "No log entries yet" placeholder when log is empty', async ({ page }) => {
    await gotoWithStatus(page, DISABLED_STATUS);
    await page.getByTestId('autopilot-log-toggle').click();
    await expect(page.getByTestId('autopilot-log-empty')).toBeVisible();
    await expect(page.getByTestId('autopilot-log-empty')).toContainText('No log entries yet');
  });

  test('entry count is shown in header when entries exist', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await expect(page.getByTestId('autopilot-log-count')).toBeVisible();
    await expect(page.getByTestId('autopilot-log-count')).toContainText('3');
  });

  test('entry count is hidden when log is empty', async ({ page }) => {
    await gotoWithStatus(page, DISABLED_STATUS);
    await expect(page.getByTestId('autopilot-log-count')).not.toBeVisible();
  });

  test('renders all log entries when opened', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await page.getByTestId('autopilot-log-toggle').click();

    const entries = page.getByTestId('autopilot-log-entry');
    await expect(entries).toHaveCount(3);
  });

  test('each entry shows formatted HH:mm:ss timestamp', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await page.getByTestId('autopilot-log-toggle').click();

    const entries = page.getByTestId('autopilot-log-entry');
    // All timestamps should be in HH:mm:ss format (exactly 8 chars)
    const firstTimestamp = entries.first().locator('.tabular-nums');
    const text = await firstTimestamp.textContent();
    expect(text).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });

  test('info badge uses gray/muted style', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await page.getByTestId('autopilot-log-toggle').click();

    const badge = page.getByTestId('autopilot-log-badge-info').first();
    await expect(badge).toBeVisible();
    const cls = await badge.getAttribute('class');
    expect(cls).toContain('text-text-secondary');
  });

  test('success badge uses green style', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await page.getByTestId('autopilot-log-toggle').click();

    const badge = page.getByTestId('autopilot-log-badge-success').first();
    await expect(badge).toBeVisible();
    const cls = await badge.getAttribute('class');
    expect(cls).toContain('text-success');
  });

  test('error badge uses red style', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await page.getByTestId('autopilot-log-toggle').click();

    const badge = page.getByTestId('autopilot-log-badge-error').first();
    await expect(badge).toBeVisible();
    const cls = await badge.getAttribute('class');
    expect(cls).toContain('text-red-400');
  });

  test('each entry shows message text', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await page.getByTestId('autopilot-log-toggle').click();

    await expect(page.getByTestId('autopilot-log-panel')).toContainText('Auto-pilot enabled');
    await expect(page.getByTestId('autopilot-log-panel')).toContainText('Feature #42 complete');
    await expect(page.getByTestId('autopilot-log-panel')).toContainText('Feature #43 failed: exit 1');
  });

  test('clear button is shown when log is open and non-empty', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await page.getByTestId('autopilot-log-toggle').click();

    await expect(page.getByTestId('autopilot-log-clear')).toBeVisible();
  });

  test('clear button is hidden when log is collapsed', async ({ page }) => {
    await gotoWithStatus(page, STATUS_WITH_LOG);
    await expect(page.getByTestId('autopilot-log-clear')).not.toBeVisible();
  });

  test('clear button is hidden when log is empty', async ({ page }) => {
    await gotoWithStatus(page, DISABLED_STATUS);
    await page.getByTestId('autopilot-log-toggle').click();

    await expect(page.getByTestId('autopilot-log-clear')).not.toBeVisible();
  });

  test('clicking clear calls /api/autopilot/log/clear and refreshes log', async ({ page }) => {
    let cleared = false;

    await page.route('**/api/autopilot/status', route => {
      const body = cleared ? { ...DISABLED_STATUS, log: [] } : STATUS_WITH_LOG;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.route('**/api/autopilot/log/clear', route => {
      cleared = true;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ cleared: true }) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await page.getByTestId('autopilot-log-toggle').click();
    await expect(page.getByTestId('autopilot-log-entry')).toHaveCount(3);

    await page.getByTestId('autopilot-log-clear').click();

    // After clear, the empty placeholder should appear
    await expect(page.getByTestId('autopilot-log-empty')).toBeVisible({ timeout: 5000 });
  });

  test('new entries added during polling are shown', async ({ page }) => {
    let showSecond = false;

    await page.route('**/api/autopilot/status', route => {
      const status = showSecond
        ? { ...DISABLED_STATUS, enabled: true, log: [...STATUS_WITH_LOG.log, { timestamp: '2026-02-23T10:00:15.000000+00:00', level: 'info', message: 'New entry arrived' }] }
        : { ...STATUS_WITH_LOG, enabled: true };
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(status) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await page.getByTestId('autopilot-log-toggle').click();
    await expect(page.getByTestId('autopilot-log-entry')).toHaveCount(3);

    showSecond = true;

    // Wait for the 2-second poll to fire (autopilot is enabled)
    await expect(page.getByTestId('autopilot-log-entry')).toHaveCount(4, { timeout: 8000 });
    await expect(page.getByTestId('autopilot-log-panel')).toContainText('New entry arrived');
  });
});
