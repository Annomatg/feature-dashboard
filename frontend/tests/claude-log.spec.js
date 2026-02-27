import { test, expect } from '@playwright/test';

/**
 * E2E tests for the Claude Log section in the Detail Panel.
 *
 * Test database seeds:
 *   Feature 1: TODO  (in_progress=false, passes=false)
 *   Feature 2: IN PROGRESS (in_progress=true,  passes=false)
 *   Feature 3: DONE (passes=true)
 *
 * The claude-log endpoint always returns 404 in the test environment because
 * no real Claude process is running.  Tests that need log data use
 * page.route() to intercept the request and return mock payloads.
 */

const MOCK_LOG_404 = { status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'No Claude log found for feature 2' }) };

const MOCK_LOG_WITH_LINES = {
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({
    feature_id: 2,
    active: true,
    lines: [
      { timestamp: '2026-02-27T10:00:01.000000+00:00', stream: 'stdout', text: 'Starting feature work...' },
      { timestamp: '2026-02-27T10:00:02.000000+00:00', stream: 'stderr', text: 'Warning: slow API call' },
      { timestamp: '2026-02-27T10:00:03.000000+00:00', stream: 'stdout', text: 'Done.' },
    ],
    total_lines: 3,
  }),
};

const MOCK_LOG_EMPTY = {
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({
    feature_id: 2,
    active: true,
    lines: [],
    total_lines: 0,
  }),
};

/** Open the detail panel for the seeded IN PROGRESS feature (id=2). */
async function openInProgressPanel(page) {
  await page.goto('/');
  await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
  const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Test Feature in Progress' });
  await card.waitFor({ state: 'visible' });
  await card.click();
  await expect(page.getByTestId('detail-panel')).toBeVisible();
}

test.describe('Claude Log Section', () => {
  test('section is hidden for a TODO feature', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Feature 1 is TODO
    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Test Feature with Description' });
    await card.waitFor({ state: 'visible' });
    await card.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();
    await expect(page.getByTestId('claude-log-section')).not.toBeVisible();
  });

  test('section is hidden for a DONE feature', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Feature 3 is DONE
    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Completed Test Feature' });
    await card.waitFor({ state: 'visible' });
    await card.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();
    await expect(page.getByTestId('claude-log-section')).not.toBeVisible();
  });

  test('section is visible for an IN PROGRESS feature', async ({ page }) => {
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_404));
    await openInProgressPanel(page);

    await expect(page.getByTestId('claude-log-section')).toBeVisible();
  });

  test('shows "No output yet" when log returns 404', async ({ page }) => {
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_404));
    await openInProgressPanel(page);

    await expect(page.getByTestId('claude-log-section')).toBeVisible();
    await expect(page.getByText('No output yet...', { exact: true })).toBeVisible();
  });

  test('shows "No output yet" when log exists but is empty', async ({ page }) => {
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_EMPTY));
    await openInProgressPanel(page);

    await expect(page.getByText('No output yet...', { exact: true })).toBeVisible();
  });

  test('renders log lines with timestamp, stream badge and text', async ({ page }) => {
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_WITH_LINES));
    await openInProgressPanel(page);

    const logLines = page.getByTestId('claude-log-lines');
    await expect(logLines).toBeVisible();

    // All three lines should be rendered
    await expect(logLines.getByText('Starting feature work...')).toBeVisible();
    await expect(logLines.getByText('Warning: slow API call')).toBeVisible();
    await expect(logLines.getByText('Done.')).toBeVisible();

    // Stream badges present
    const badges = logLines.getByTestId('claude-log-stream-badge');
    await expect(badges).toHaveCount(3);
  });

  test('stdout badge is blue, stderr badge is red', async ({ page }) => {
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_WITH_LINES));
    await openInProgressPanel(page);

    const badges = page.getByTestId('claude-log-stream-badge');
    const first = badges.nth(0);  // stdout
    const second = badges.nth(1); // stderr

    await expect(first).toHaveText('stdout');
    await expect(first).toHaveClass(/text-blue-400/);

    await expect(second).toHaveText('stderr');
    await expect(second).toHaveClass(/text-red-400/);
  });

  test('header shows total line count', async ({ page }) => {
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_WITH_LINES));
    await openInProgressPanel(page);

    const toggle = page.getByTestId('claude-log-toggle');
    await expect(toggle).toContainText('3 lines');
  });

  test('collapse toggle hides log lines', async ({ page }) => {
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_WITH_LINES));
    await openInProgressPanel(page);

    await expect(page.getByTestId('claude-log-lines')).toBeVisible();

    await page.getByTestId('claude-log-toggle').click();

    await expect(page.getByTestId('claude-log-lines')).not.toBeVisible();
  });

  test('collapse toggle re-expands log lines', async ({ page }) => {
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_WITH_LINES));
    await openInProgressPanel(page);

    await page.getByTestId('claude-log-toggle').click();
    await expect(page.getByTestId('claude-log-lines')).not.toBeVisible();

    await page.getByTestId('claude-log-toggle').click();
    await expect(page.getByTestId('claude-log-lines')).toBeVisible();
  });

  test('refresh button re-fetches the log', async ({ page }) => {
    let callCount = 0;
    await page.route('**/api/features/2/claude-log**', route => {
      callCount++;
      route.fulfill(MOCK_LOG_WITH_LINES);
    });

    await openInProgressPanel(page);

    // Wait for initial fetch
    await expect(page.getByTestId('claude-log-lines')).toBeVisible();
    const countAfterLoad = callCount;

    // Click refresh
    await page.getByTestId('claude-log-refresh').click();
    await page.waitForTimeout(300);

    expect(callCount).toBeGreaterThan(countAfterLoad);
  });

  test('no horizontal overflow at 375px width', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_WITH_LINES));

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // On mobile, switch to IN PROGRESS lane tab so the card is visible
    const inProgressTab = page.getByTestId('lane-tab-inProgress');
    if (await inProgressTab.isVisible()) {
      await inProgressTab.click();
    }

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Test Feature in Progress' });
    await card.waitFor({ state: 'visible' });
    await card.click();
    await expect(page.getByTestId('detail-panel')).toBeVisible();

    const section = page.getByTestId('claude-log-section');
    await expect(section).toBeVisible();

    const box = await section.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x + box.width).toBeLessThanOrEqual(375 + 2); // allow 2px rounding
  });

  test('no horizontal overflow at 768px width', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.route('**/api/features/2/claude-log**', route => route.fulfill(MOCK_LOG_WITH_LINES));
    await openInProgressPanel(page);

    const section = page.getByTestId('claude-log-section');
    await expect(section).toBeVisible();

    const box = await section.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x + box.width).toBeLessThanOrEqual(768 + 2);
  });
});
