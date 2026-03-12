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
  body: JSON.stringify({ active: true, feature_id: 2, entries: [], session_file: null }),
};

const MOCK_SESSION_WITH_ENTRIES = {
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({
    active: true,
    feature_id: 2, // Matches the in-progress feature (id=2)
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
  body: JSON.stringify({ active: true, feature_id: 2, entries: MANY_ENTRIES, session_file: 'session.jsonl' }),
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

  test.describe('feature_id filtering', () => {
    test('log section is hidden when feature_id does not match', async ({ page }) => {
      // Session log is for feature 99, but we're viewing feature 2
      const mockResponse = {
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: true,
          feature_id: 99, // Different from the in-progress feature (id=2)
          entries: [
            { timestamp: '2026-02-27T10:00:01.000000+00:00', entry_type: 'text', text: 'Working on feature 99...' },
          ],
          session_file: 'session.jsonl',
        }),
      };
      await page.route('**/api/autopilot/session-log**', route => route.fulfill(mockResponse));
      await openInProgressPanel(page);

      // Log section should be hidden because feature_id doesn't match
      await expect(page.getByTestId('claude-log-section')).not.toBeVisible();
    });

    test('log section is visible when feature_id matches', async ({ page }) => {
      // Session log is for feature 2 (the in-progress feature)
      const mockResponse = {
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: true,
          feature_id: 2, // Matches the in-progress feature
          entries: [
            { timestamp: '2026-02-27T10:00:01.000000+00:00', entry_type: 'text', text: 'Working on feature 2...' },
          ],
          session_file: 'session.jsonl',
        }),
      };
      await page.route('**/api/autopilot/session-log**', route => route.fulfill(mockResponse));
      await openInProgressPanel(page);

      // Log section should be visible because feature_id matches
      await expect(page.getByTestId('claude-log-section')).toBeVisible();
      // Check for the log entry in the log lines container
      await expect(page.getByTestId('claude-log-lines').getByText('Working on feature 2...')).toBeVisible();
    });

    test('log section is hidden when feature_id is null', async ({ page }) => {
      // Session log has no feature_id (e.g., no active session)
      const mockResponse = {
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: true,
          feature_id: null,
          entries: [
            { timestamp: '2026-02-27T10:00:01.000000+00:00', entry_type: 'text', text: 'Some log...' },
          ],
          session_file: 'session.jsonl',
        }),
      };
      await page.route('**/api/autopilot/session-log**', route => route.fulfill(mockResponse));
      await openInProgressPanel(page);

      // Log section should be hidden because feature_id is null
      await expect(page.getByTestId('claude-log-section')).not.toBeVisible();
    });

    test('shows historical log for in-progress feature when live session is for a different feature', async ({ page }) => {
      // Bug fix: if an in-progress feature has a claude_session_id (previous run), the log should
      // fall back to the historical endpoint even when the live session is for a different feature.
      const PREV_SESSION_ENTRIES = [
        { timestamp: '2026-02-27T09:00:01.000000+00:00', entry_type: 'text', text: 'Previous session output.' },
        { timestamp: '2026-02-27T09:00:02.000000+00:00', entry_type: 'tool_use', tool_name: 'Bash', text: '$ echo hello' },
      ];

      // Use a static mock response to inject claude_session_id into Feature 2 (in-progress).
      // The /api/features?passes=false endpoint returns a plain array (no pagination).
      await page.route(
        url => url.href.includes('/api/features') && url.href.includes('passes=false') && !url.href.includes('session-log'),
        route => route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 1, priority: 1, category: 'Test', name: 'Test Feature with Description', description: 'desc', steps: [], passes: false, in_progress: false, model: 'sonnet', claude_session_id: null, created_at: null, modified_at: null, completed_at: null },
            { id: 2, priority: 2, category: 'Test', name: 'Test Feature in Progress', description: 'desc', steps: [], passes: false, in_progress: true, model: 'sonnet', claude_session_id: 'prev-session.jsonl', created_at: null, modified_at: null, completed_at: null },
          ]),
        })
      );

      // Live session is for a different feature (99)
      await page.route('**/api/autopilot/session-log**', route => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ active: true, feature_id: 99, entries: [], session_file: 'other.jsonl' }),
      }));

      // Historical endpoint for Feature 2 returns previous session entries
      await page.route('**/api/features/2/session-log**', route => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: false,
          feature_id: 2,
          entries: PREV_SESSION_ENTRIES,
          session_file: 'prev-session.jsonl',
          total_entries: 2,
        }),
      }));

      await openInProgressPanel(page);

      // Log section should be visible with historical entries (not hidden)
      await expect(page.getByTestId('claude-log-section')).toBeVisible();
      await expect(page.getByTestId('claude-log-lines').getByText('Previous session output.')).toBeVisible();
      await expect(page.getByTestId('claude-log-lines').getByText('$ echo hello')).toBeVisible();
    });
  });

  test.describe('historical log (non-in-progress features with claude_session_id)', () => {
    const MOCK_HISTORICAL_LOG = {
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        active: false,
        feature_id: null,
        entries: [
          { timestamp: '2026-02-27T10:00:01.000000+00:00', entry_type: 'text', text: 'Fixed the bug.' },
          { timestamp: '2026-02-27T10:00:02.000000+00:00', entry_type: 'tool_use', tool_name: 'Edit', text: 'Edit: main.py' },
        ],
        session_file: 'old-session.jsonl',
        total_entries: 2,
      }),
    };

    test('section shows historical log for a TODO feature with session ID', async ({ page }) => {
      // Mock the features list to inject claude_session_id into Feature 1 (Test Feature with Description).
      // The /api/features?passes=false endpoint returns a plain array (no pagination), so we
      // map the array directly and fulfill with the modified array.
      await page.route(
        url => url.href.includes('/api/features') && url.href.includes('passes=false') && !url.href.includes('session-log'),
        async route => {
          const response = await route.fetch();
          const body = await response.json();
          const modified = body.map(f =>
            f.id === 1 ? { ...f, claude_session_id: 'old-session.jsonl' } : f
          );
          await route.fulfill({ json: modified });
        }
      );
      await page.route('**/api/features/1/session-log**', route => route.fulfill(MOCK_HISTORICAL_LOG));

      await page.goto('/');
      await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
      const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Test Feature with Description' });
      await card.waitFor({ state: 'visible' });
      await card.click();

      await expect(page.getByTestId('detail-panel')).toBeVisible();
      await expect(page.getByTestId('claude-log-section')).toBeVisible();
      await expect(page.getByTestId('claude-log-lines').getByText('Fixed the bug.')).toBeVisible();
      await expect(page.getByTestId('claude-log-lines').getByText('Edit: main.py')).toBeVisible();
    });

    test('section shows historical log for a DONE feature with session ID', async ({ page }) => {
      // Mock the features list to inject claude_session_id into Feature 3 (Completed Test Feature)
      await page.route(
        url => url.href.includes('/api/features') && url.href.includes('passes=true') && !url.href.includes('session-log'),
        async route => {
          const response = await route.fetch();
          const body = await response.json();
          const modified = (body.features || []).map(f =>
            f.id === 3 ? { ...f, claude_session_id: 'done-session.jsonl' } : f
          );
          await route.fulfill({ json: { ...body, features: modified } });
        }
      );
      await page.route('**/api/features/3/session-log**', route => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: false,
          feature_id: 3,
          entries: [{ timestamp: '2026-02-27T10:00:01.000000+00:00', entry_type: 'text', text: 'Feature completed.' }],
          session_file: 'done-session.jsonl',
          total_entries: 1,
        }),
      }));

      await page.goto('/');
      await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
      const doneTab = page.getByTestId('lane-tab-done');
      if (await doneTab.isVisible()) await doneTab.click();
      const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Completed Test Feature' });
      await card.waitFor({ state: 'visible' });
      await card.click();

      await expect(page.getByTestId('detail-panel')).toBeVisible();
      await expect(page.getByTestId('claude-log-section')).toBeVisible();
      await expect(page.getByTestId('claude-log-lines').getByText('Feature completed.')).toBeVisible();
    });

    test('historical log shows entry count in header', async ({ page }) => {
      // Mock the features list to inject claude_session_id into Feature 1
      await page.route(
        url => url.href.includes('/api/features') && url.href.includes('passes=false') && !url.href.includes('session-log'),
        async route => {
          const response = await route.fetch();
          const body = await response.json();
          const modified = body.map(f =>
            f.id === 1 ? { ...f, claude_session_id: 'count-session.jsonl' } : f
          );
          await route.fulfill({ json: modified });
        }
      );
      await page.route('**/api/features/1/session-log**', route => route.fulfill(MOCK_HISTORICAL_LOG));

      await page.goto('/');
      await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
      const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Test Feature with Description' });
      await card.waitFor({ state: 'visible' });
      await card.click();

      await expect(page.getByTestId('claude-log-section')).toBeVisible();
      await expect(page.getByTestId('claude-log-toggle')).toContainText('2 entries');
    });

    test('historical log does not poll (fetches only once)', async ({ page }) => {
      // Mock the features list to inject claude_session_id into Feature 1
      await page.route(
        url => url.href.includes('/api/features') && url.href.includes('passes=false') && !url.href.includes('session-log'),
        async route => {
          const response = await route.fetch();
          const body = await response.json();
          const modified = body.map(f =>
            f.id === 1 ? { ...f, claude_session_id: 'nopoll-session.jsonl' } : f
          );
          await route.fulfill({ json: modified });
        }
      );

      let callCount = 0;
      await page.route('**/api/features/1/session-log**', route => {
        callCount++;
        route.fulfill(MOCK_HISTORICAL_LOG);
      });

      await page.goto('/');
      await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
      const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Test Feature with Description' });
      await card.waitFor({ state: 'visible' });
      await card.click();

      await expect(page.getByTestId('claude-log-section')).toBeVisible();
      // Let initial fetches stabilize (React StrictMode may cause double-invoke in dev)
      await page.waitForTimeout(500);
      const countAfterMount = callCount;
      // Wait longer than one polling interval (3s) — no additional fetches should occur
      await page.waitForTimeout(3500);
      expect(callCount).toBe(countAfterMount);
    });
  });
});
