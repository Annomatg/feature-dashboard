import { test, expect } from '@playwright/test';

test.describe('Auto-Pilot Toggle', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept autopilot status so we control the state and avoid spawning Claude
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

  test('button appears in header', async ({ page }) => {
    const toggle = page.getByTestId('autopilot-toggle');
    await expect(toggle).toBeVisible();
  });

  test('disabled state shows Bot icon and "Auto-Pilot" label in muted style', async ({ page }) => {
    const toggle = page.getByTestId('autopilot-toggle');
    await expect(toggle).toBeVisible();

    // Text label
    await expect(toggle).toContainText('Auto-Pilot');

    // Pulsing dot should NOT be present in disabled state
    await expect(page.getByTestId('autopilot-pulse-dot')).not.toBeVisible();

    // Should not have the enabled (green border) class
    const classList = await toggle.getAttribute('class');
    expect(classList).not.toContain('border-success');
  });

  test('enabled state shows pulsing green dot and "Auto-Pilot ON" label', async ({ page }) => {
    // Override the status route to return enabled state
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: true, current_feature_id: 1, current_feature_name: 'Test Feature', last_error: null, log: [] }),
      });
    });

    // Reload so the component picks up enabled=true from the start
    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const toggle = page.getByTestId('autopilot-toggle');
    await expect(toggle).toBeVisible();

    // Should show "Auto-Pilot ON" text
    await expect(toggle).toContainText('Auto-Pilot ON');

    // Pulsing green dot should be present
    await expect(page.getByTestId('autopilot-pulse-dot')).toBeVisible();

    // Should have the enabled style (green border class)
    const classList = await toggle.getAttribute('class');
    expect(classList).toContain('border-success');
  });

  test('clicking disabled button calls enable endpoint and updates state', async ({ page }) => {
    let statusEnabled = false;

    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enabled: statusEnabled,
          current_feature_id: statusEnabled ? 1 : null,
          current_feature_name: statusEnabled ? 'Test Feature' : null,
          last_error: null,
          log: [],
        }),
      });
    });

    await page.route('**/api/autopilot/enable', route => {
      statusEnabled = true;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: true, current_feature_id: 1, current_feature_name: 'Test Feature', last_error: null, log: [] }),
      });
    });

    // Reload to pick up the new route
    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const toggle = page.getByTestId('autopilot-toggle');
    await expect(toggle).toBeVisible();
    await expect(toggle).toContainText('Auto-Pilot');

    // Click to enable
    await toggle.click();

    // After enable, status is polled — now it returns enabled=true
    await expect(toggle).toContainText('Auto-Pilot ON', { timeout: 5000 });
    await expect(page.getByTestId('autopilot-pulse-dot')).toBeVisible();
  });

  test('clicking enabled button calls disable endpoint and updates state', async ({ page }) => {
    let statusEnabled = true;

    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enabled: statusEnabled,
          current_feature_id: statusEnabled ? 1 : null,
          current_feature_name: statusEnabled ? 'Test Feature' : null,
          last_error: null,
          log: [],
        }),
      });
    });

    await page.route('**/api/autopilot/disable', route => {
      statusEnabled = false;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: false, current_feature_id: null, current_feature_name: null, last_error: null, log: [] }),
      });
    });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const toggle = page.getByTestId('autopilot-toggle');
    await expect(toggle).toContainText('Auto-Pilot ON', { timeout: 5000 });

    // Click to disable
    await toggle.click();

    // After disable, status returns enabled=false
    await expect(toggle).toContainText('Auto-Pilot', { timeout: 5000 });
    await expect(page.getByTestId('autopilot-pulse-dot')).not.toBeVisible();
  });

  test('shows error toast when enable fails', async ({ page }) => {
    await page.route('**/api/autopilot/enable', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Claude not found' }),
      });
    });

    const toggle = page.getByTestId('autopilot-toggle');
    await toggle.click();

    await expect(page.getByText('Claude not found', { exact: true })).toBeVisible({ timeout: 5000 });
  });
});

// ---------------------------------------------------------------------------
// Stopping state — process still alive after manual disable
// ---------------------------------------------------------------------------

const STOPPING_STATUS = {
  enabled: false,
  stopping: true,
  current_feature_id: 42,
  current_feature_name: 'Build the rocket',
  current_feature_model: 'sonnet',
  last_error: null,
  log: [],
};

test.describe('Auto-Pilot Toggle — stopping state', () => {
  test('shows amber "Stopping…" button when stopping=true', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(STOPPING_STATUS) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const toggle = page.getByTestId('autopilot-toggle');
    await expect(toggle).toBeVisible();
    // Must show the ellipsis character (…), not literal "\u2026"
    await expect(toggle).toContainText('Stopping\u2026');
    // Should not show enabled styles
    const cls = await toggle.getAttribute('class');
    expect(cls).not.toContain('border-success');
    // Should show amber styles
    expect(cls).toContain('border-amber-500');
  });

  test('stopping dot is visible when stopping=true', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(STOPPING_STATUS) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-stopping-dot')).toBeVisible();
    await expect(page.getByTestId('autopilot-pulse-dot')).not.toBeVisible();
  });

  test('clicking toggle while stopping calls enable endpoint', async ({ page }) => {
    let enableCalled = false;
    let currentStatus = { ...STOPPING_STATUS };

    await page.route('**/api/autopilot/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(currentStatus) });
    });

    await page.route('**/api/autopilot/enable', route => {
      enableCalled = true;
      currentStatus = {
        enabled: true, stopping: false,
        current_feature_id: 7, current_feature_name: 'Next Feature',
        current_feature_model: 'sonnet', last_error: null, log: [],
      };
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(currentStatus) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-toggle')).toContainText('Stopping\u2026');

    // Click to re-enable
    await page.getByTestId('autopilot-toggle').click();

    expect(enableCalled).toBe(true);
    // Toggle transitions to enabled (green) state
    await expect(page.getByTestId('autopilot-toggle')).toContainText('Auto-Pilot ON', { timeout: 5000 });
  });

  test('toggle transitions from stopping to normal disabled when process finishes', async ({ page }) => {
    let isStopping = true;

    await page.route('**/api/autopilot/status', route => {
      const body = isStopping
        ? STOPPING_STATUS
        : { enabled: false, stopping: false, current_feature_id: null,
            current_feature_name: null, current_feature_model: null, last_error: null, log: [] };
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-toggle')).toContainText('Stopping\u2026');

    // Simulate process finishing (poll will pick it up within 2 s)
    isStopping = false;

    await expect(page.getByTestId('autopilot-toggle')).toContainText('Auto-Pilot', { timeout: 8000 });
    // Should no longer show stopping dot
    await expect(page.getByTestId('autopilot-stopping-dot')).not.toBeVisible();
  });
});
