import { test, expect } from '@playwright/test';

/**
 * E2E tests for Feature #150: Show Claude session log in in-progress cards.
 *
 * When a Claude process is active, the KanbanCard for in-progress features
 * should display the latest session log entry (data-testid="claude-log-snippet")
 * instead of the most recent comment (data-testid="recent-log").
 *
 * When no session is active, in-progress cards fall back to showing the
 * recent comment (same as TODO/DONE cards).
 */

const API = 'http://localhost:8001';

const MOCK_SESSION_ACTIVE = {
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({
    active: true,
    feature_id: null, // Will be set dynamically in tests
    session_file: 'session.jsonl',
    entries: [
      { timestamp: '2026-03-02T10:00:01.000000+00:00', entry_type: 'text', tool_name: null, text: 'Working on the implementation now' },
    ],
    total_entries: 1,
  }),
};

const MOCK_SESSION_INACTIVE = {
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({
    active: false,
    feature_id: null,
    session_file: null,
    entries: [],
    total_entries: 0,
  }),
};

async function createInProgressFeature(page, name) {
  const res = await page.request.post(`${API}/api/features`, {
    data: { category: 'Test', name, description: 'test desc', steps: [] },
  });
  expect(res.ok()).toBeTruthy();
  const feature = await res.json();

  const stateRes = await page.request.patch(`${API}/api/features/${feature.id}/state`, {
    data: { in_progress: true, passes: false },
  });
  expect(stateRes.ok()).toBeTruthy();
  return feature;
}

async function addComment(page, featureId, content) {
  const res = await page.request.post(`${API}/api/features/${featureId}/comments`, {
    data: { content },
  });
  expect(res.ok()).toBeTruthy();
}

test.describe('Claude log in in-progress card (Feature #150)', () => {
  test('in-progress card shows claude-log-snippet when session is active', async ({ page }) => {
    const feature = await createInProgressFeature(page, 'Log Snippet Active Test');
    await addComment(page, feature.id, 'Previous comment text');

    // Mock the session log to return an active session with one entry for this feature
    await page.route('**/api/autopilot/session-log?limit=1', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: true,
          feature_id: feature.id, // Match the feature being tested
          session_file: 'session.jsonl',
          entries: [
            { timestamp: '2026-03-02T10:00:01.000000+00:00', entry_type: 'text', tool_name: null, text: 'Working on the implementation now' },
          ],
          total_entries: 1,
        }),
      })
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator(`[data-testid="kanban-card"][data-feature-id="${feature.id}"]`);
    await card.waitFor({ state: 'visible' });

    // Claude log snippet should be shown
    const snippet = card.locator('[data-testid="claude-log-snippet"]');
    await expect(snippet).toBeVisible();
    await expect(snippet).toContainText('Working on the implementation now');

    // recent-log (comment) should NOT be shown
    await expect(card.locator('[data-testid="recent-log"]')).not.toBeVisible();

    // Cleanup
    await page.request.delete(`${API}/api/features/${feature.id}`);
  });

  test('in-progress card falls back to recent-log when session is inactive', async ({ page }) => {
    const feature = await createInProgressFeature(page, 'Log Snippet Inactive Test');
    await addComment(page, feature.id, 'Most recent comment here');

    // Mock the session log to return an inactive session
    await page.route('**/api/autopilot/session-log?limit=1', route =>
      route.fulfill(MOCK_SESSION_INACTIVE)
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator(`[data-testid="kanban-card"][data-feature-id="${feature.id}"]`);
    await card.waitFor({ state: 'visible' });

    // recent-log (comment) should be shown as fallback
    const recentLog = card.locator('[data-testid="recent-log"]');
    await expect(recentLog).toBeVisible();
    await expect(recentLog).toContainText('Most recent comment here');

    // claude-log-snippet should NOT be shown
    await expect(card.locator('[data-testid="claude-log-snippet"]')).not.toBeVisible();

    // Cleanup
    await page.request.delete(`${API}/api/features/${feature.id}`);
  });

  test('non-in-progress card always shows recent-log even when session is active', async ({ page }) => {
    // Create a TODO feature (not in-progress)
    const res = await page.request.post(`${API}/api/features`, {
      data: { category: 'Test', name: 'Todo Card Log Test', description: 'todo', steps: [] },
    });
    expect(res.ok()).toBeTruthy();
    const feature = await res.json();
    await addComment(page, feature.id, 'Todo comment text');

    // Mock an active session for a DIFFERENT feature (not this one)
    await page.route('**/api/autopilot/session-log?limit=1', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: true,
          feature_id: 99999, // Different feature - snippet should not show on this card
          session_file: 'session.jsonl',
          entries: [
            { timestamp: '2026-03-02T10:00:01.000000+00:00', entry_type: 'text', tool_name: null, text: 'Working on the implementation now' },
          ],
          total_entries: 1,
        }),
      })
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator(`[data-testid="kanban-card"][data-feature-id="${feature.id}"]`);
    await card.waitFor({ state: 'visible' });

    // TODO card should always show recent-log, not claude-log-snippet
    const recentLog = card.locator('[data-testid="recent-log"]');
    await expect(recentLog).toBeVisible();
    await expect(recentLog).toContainText('Todo comment text');
    await expect(card.locator('[data-testid="claude-log-snippet"]')).not.toBeVisible();

    // Cleanup
    await page.request.delete(`${API}/api/features/${feature.id}`);
  });

  test('claude-log-snippet is blue-tinted to distinguish from recent-log', async ({ page }) => {
    const feature = await createInProgressFeature(page, 'Log Snippet Color Test');

    await page.route('**/api/autopilot/session-log?limit=1', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: true,
          feature_id: feature.id, // Match the feature being tested
          session_file: 'session.jsonl',
          entries: [
            { timestamp: '2026-03-02T10:00:01.000000+00:00', entry_type: 'text', tool_name: null, text: 'Working on the implementation now' },
          ],
          total_entries: 1,
        }),
      })
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator(`[data-testid="kanban-card"][data-feature-id="${feature.id}"]`);
    await card.waitFor({ state: 'visible' });

    const snippet = card.locator('[data-testid="claude-log-snippet"]');
    await expect(snippet).toBeVisible();

    // Verify blue color class is applied (text-blue-400)
    await expect(snippet).toHaveClass(/text-blue-400/);

    // Cleanup
    await page.request.delete(`${API}/api/features/${feature.id}`);
  });

  test('snippet only shows on the card matching feature_id (Feature #176)', async ({ page }) => {
    // Create two in-progress features
    const featureA = await createInProgressFeature(page, 'Feature A - Active Session');
    const featureB = await createInProgressFeature(page, 'Feature B - Not Active');
    await addComment(page, featureA.id, 'Comment on A');
    await addComment(page, featureB.id, 'Comment on B');

    // Mock session log to show feature A is being processed
    await page.route('**/api/autopilot/session-log?limit=1', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: true,
          feature_id: featureA.id, // Only feature A should show the snippet
          session_file: 'session.jsonl',
          entries: [
            { timestamp: '2026-03-02T10:00:01.000000+00:00', entry_type: 'text', tool_name: null, text: 'Working on Feature A' },
          ],
          total_entries: 1,
        }),
      })
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Feature A card should show the snippet
    const cardA = page.locator(`[data-testid="kanban-card"][data-feature-id="${featureA.id}"]`);
    await cardA.waitFor({ state: 'visible' });
    const snippetA = cardA.locator('[data-testid="claude-log-snippet"]');
    await expect(snippetA).toBeVisible();
    await expect(snippetA).toContainText('Working on Feature A');

    // Feature B card should NOT show the snippet (should show recent-log instead)
    const cardB = page.locator(`[data-testid="kanban-card"][data-feature-id="${featureB.id}"]`);
    await cardB.waitFor({ state: 'visible' });
    const snippetB = cardB.locator('[data-testid="claude-log-snippet"]');
    await expect(snippetB).not.toBeVisible();
    const recentLogB = cardB.locator('[data-testid="recent-log"]');
    await expect(recentLogB).toBeVisible();
    await expect(recentLogB).toContainText('Comment on B');

    // Cleanup
    await page.request.delete(`${API}/api/features/${featureA.id}`);
    await page.request.delete(`${API}/api/features/${featureB.id}`);
  });
});
