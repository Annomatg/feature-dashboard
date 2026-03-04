import { test, expect } from '@playwright/test';

/**
 * E2E tests for the Claude Log section in the Detail Panel.
 *
 * Test database seeds:
 *   Feature 1: TODO  (in_progress=false, passes=false)
 *   Feature 2: IN PROGRESS (in_progress=true,  passes=false)
 *   Feature 3: DONE (passes=true)
 *
 * The component calls GET /api/autopilot/session-log?limit=50.
 * Tests that need log data intercept that endpoint with mock payloads.
 */

const MOCK_SESSION_EMPTY = {
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({ entries: [], session_file: null }),
};

const MOCK_SESSION_WITH_ENTRIES = {
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({
    entries: [
      { timestamp: '2026-02-27T10:00:01.000000+00:00', entry_type: 'text', text: 'Starting feature work...' },
      { timestamp: '2026-02-27T10:00:02.000000+00:00', entry_type: 'tool_use', tool_name: 'Bash', text: 'Running command...' },
      { timestamp: '2026-02-27T10:00:03.000000+00:00', entry_type: 'thinking', text: 'Analyzing the codebase...' },
      { timestamp: '2026-02-27T10:00:04.000000+00:00', entry_type: 'text', text: 'Done.' },
    ],
    session_file: 'session.jsonl',
  }),
};

// 20 entries — enough to overflow the 200px max-height container
const MANY_ENTRIES = Array.from({ length: 20 }, (_, i) => ({
  timestamp: `2026-02-27T10:00:${String(i).padStart(2, '0')}.000000+00:00`,
  entry_type: 'text',
  text: `Log line ${i + 1} — some content here`,
}));

const MOCK_SESSION_MANY = {
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({ entries: MANY_ENTRIES, session_file: 'session.jsonl' }),
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
    await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_EMPTY));
    await openInProgressPanel(page);

    await expect(page.getByTestId('claude-log-section')).toBeVisible();
  });

  test('shows "No output yet" when session log is empty', async ({ page }) => {
    await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_EMPTY));
    await openInProgressPanel(page);

    await expect(page.getByText('No output yet...', { exact: true })).toBeVisible();
  });

  test('renders log entries with timestamp, stream badge and text', async ({ page }) => {
    await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_WITH_ENTRIES));
    await openInProgressPanel(page);

    const logLines = page.getByTestId('claude-log-lines');
    await expect(logLines).toBeVisible();

    // All four entries should be rendered
    await expect(logLines.getByText('Starting feature work...')).toBeVisible();
    await expect(logLines.getByText('Running command...')).toBeVisible();
    await expect(logLines.getByText('Analyzing the codebase...')).toBeVisible();
    await expect(logLines.getByText('Done.')).toBeVisible();

    // Stream badges present
    const badges = logLines.getByTestId('claude-log-stream-badge');
    await expect(badges).toHaveCount(4);
  });

  test('tool_use badge is blue, thinking badge is purple, text badge is green', async ({ page }) => {
    await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_WITH_ENTRIES));
    await openInProgressPanel(page);

    const badges = page.getByTestId('claude-log-stream-badge');
    const first = badges.nth(0);  // text entry
    const second = badges.nth(1); // tool_use entry
    const third = badges.nth(2);  // thinking entry

    await expect(first).toHaveText('text');
    await expect(first).toHaveClass(/text-green-400/);

    await expect(second).toHaveText('Bash');
    await expect(second).toHaveClass(/text-blue-400/);

    await expect(third).toHaveText('think');
    await expect(third).toHaveClass(/text-purple-400/);
  });

  test('header shows total entry count', async ({ page }) => {
    await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_WITH_ENTRIES));
    await openInProgressPanel(page);

    const toggle = page.getByTestId('claude-log-toggle');
    await expect(toggle).toContainText('4 entries');
  });

  test('collapse toggle hides log lines', async ({ page }) => {
    await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_WITH_ENTRIES));
    await openInProgressPanel(page);

    await expect(page.getByTestId('claude-log-lines')).toBeVisible();

    await page.getByTestId('claude-log-toggle').click();

    await expect(page.getByTestId('claude-log-lines')).not.toBeVisible();
  });

  test('collapse toggle re-expands log lines', async ({ page }) => {
    await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_WITH_ENTRIES));
    await openInProgressPanel(page);

    await page.getByTestId('claude-log-toggle').click();
    await expect(page.getByTestId('claude-log-lines')).not.toBeVisible();

    await page.getByTestId('claude-log-toggle').click();
    await expect(page.getByTestId('claude-log-lines')).toBeVisible();
  });

  test('refresh button re-fetches the log', async ({ page }) => {
    let callCount = 0;
    await page.route('**/api/autopilot/session-log**', route => {
      callCount++;
      route.fulfill(MOCK_SESSION_WITH_ENTRIES);
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
    await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_WITH_ENTRIES));

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
    await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_WITH_ENTRIES));
    await openInProgressPanel(page);

    const section = page.getByTestId('claude-log-section');
    await expect(section).toBeVisible();

    const box = await section.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x + box.width).toBeLessThanOrEqual(768 + 2);
  });

  test.describe('tail / scroll behaviour', () => {
    test('log is scrolled to bottom on initial open', async ({ page }) => {
      await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_MANY));
      await openInProgressPanel(page);

      const logEl = page.getByTestId('claude-log-lines');
      await expect(logEl).toBeVisible();
      // Last entry must be visible without any manual scrolling
      await expect(logEl.getByText('Log line 20 — some content here')).toBeVisible();

      // scrollTop should be at the bottom (within a small tolerance)
      const atBottom = await logEl.evaluate(el => el.scrollTop + el.clientHeight >= el.scrollHeight - 20);
      expect(atBottom).toBe(true);
    });

    test('log stays at bottom when new entries arrive and user is pinned', async ({ page }) => {
      // First response: 10 entries
      const firstEntries = MANY_ENTRIES.slice(0, 10);
      let callCount = 0;
      await page.route('**/api/autopilot/session-log**', route => {
        callCount++;
        if (callCount === 1) {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ entries: firstEntries, session_file: 'session.jsonl' }),
          });
        } else {
          route.fulfill(MOCK_SESSION_MANY); // 20 entries
        }
      });

      await openInProgressPanel(page);
      const logEl = page.getByTestId('claude-log-lines');
      await expect(logEl.getByText('Log line 10 — some content here')).toBeVisible();

      // Trigger the second fetch (click refresh to force it immediately)
      await page.getByTestId('claude-log-refresh').click();
      await expect(logEl.getByText('Log line 20 — some content here')).toBeVisible();

      // Should still be at the bottom
      const atBottom = await logEl.evaluate(el => el.scrollTop + el.clientHeight >= el.scrollHeight - 20);
      expect(atBottom).toBe(true);
    });

    test('log does NOT auto-scroll when user has scrolled up', async ({ page }) => {
      // First: 20 entries. Second: 20 entries (same, so no content change, but test scroll lock)
      let callCount = 0;
      await page.route('**/api/autopilot/session-log**', route => {
        callCount++;
        route.fulfill(MOCK_SESSION_MANY);
      });

      await openInProgressPanel(page);
      const logEl = page.getByTestId('claude-log-lines');
      await expect(logEl.getByText('Log line 20 — some content here')).toBeVisible();

      // User scrolls to the top
      await logEl.evaluate(el => { el.scrollTop = 0; });
      // Fire a scroll event so the component tracks the position
      await logEl.dispatchEvent('scroll');

      // Capture scrollTop before the next fetch
      const scrollTopBefore = await logEl.evaluate(el => el.scrollTop);

      // Trigger another fetch
      await page.getByTestId('claude-log-refresh').click();
      await page.waitForTimeout(300);

      // scrollTop should remain where user left it
      const scrollTopAfter = await logEl.evaluate(el => el.scrollTop);
      expect(scrollTopAfter).toBeLessThanOrEqual(scrollTopBefore + 5);
    });

    test('log scrolls to bottom when re-expanded after collapse', async ({ page }) => {
      await page.route('**/api/autopilot/session-log**', route => route.fulfill(MOCK_SESSION_MANY));
      await openInProgressPanel(page);

      const logEl = page.getByTestId('claude-log-lines');
      await expect(logEl.getByText('Log line 20 — some content here')).toBeVisible();

      // User scrolls up
      await logEl.evaluate(el => { el.scrollTop = 0; });
      await logEl.dispatchEvent('scroll');

      // Collapse then re-expand
      await page.getByTestId('claude-log-toggle').click();
      await expect(logEl).not.toBeVisible();
      await page.getByTestId('claude-log-toggle').click();
      await expect(logEl).toBeVisible();

      // After re-expanding, should be at the bottom again
      const atBottom = await logEl.evaluate(el => el.scrollTop + el.clientHeight >= el.scrollHeight - 20);
      expect(atBottom).toBe(true);
    });
  });
});
