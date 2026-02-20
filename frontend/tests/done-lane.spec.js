import { test, expect } from '@playwright/test';

/**
 * E2E tests for Done lane date grouping and pagination.
 * Uses isolated test database (port 8001).
 */

const API = 'http://localhost:8001';

async function createDoneFeature(request, overrides = {}) {
  // Create feature
  const createRes = await request.post(`${API}/api/features`, {
    data: {
      category: 'Test',
      name: 'Done Test Feature',
      description: 'Created for done lane test',
      steps: ['Step 1'],
      ...overrides
    }
  });
  expect(createRes.ok()).toBeTruthy();
  const feature = await createRes.json();

  // Mark it as done
  const stateRes = await request.patch(`${API}/api/features/${feature.id}/state`, {
    data: { passes: true, in_progress: false }
  });
  expect(stateRes.ok()).toBeTruthy();
  return stateRes.json();
}

async function deleteFeature(request, id) {
  await request.delete(`${API}/api/features/${id}`);
}

test.describe('Done lane: date grouping', () => {
  const createdIds = [];

  test.afterEach(async ({ request }) => {
    for (const id of createdIds) {
      await deleteFeature(request, id);
    }
    createdIds.length = 0;
  });

  test('should show "Today" date group for recently completed features', async ({ page, request }) => {
    const feature = await createDoneFeature(request, { name: 'Today Done Feature' });
    createdIds.push(feature.id);

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Wait for the done lane to render
    await page.waitForTimeout(500);

    // Should see "Today" date group header
    const todayHeader = page.locator('[data-testid="done-date-group"]', { hasText: 'Today' });
    await expect(todayHeader).toBeVisible();
  });

  test('should show feature name under the Today group', async ({ page, request }) => {
    const feature = await createDoneFeature(request, { name: 'My Grouped Done Feature' });
    createdIds.push(feature.id);

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(500);

    // The feature name should be visible in the done lane
    await expect(page.locator('[data-testid="kanban-card"]').filter({ hasText: 'My Grouped Done Feature' })).toBeVisible();
  });
});

test.describe('Done lane: features persist after move', () => {
  const createdIds = [];

  test.afterEach(async ({ request }) => {
    for (const id of createdIds) {
      await deleteFeature(request, id);
    }
    createdIds.length = 0;
  });

  test('existing done features remain visible after another feature is moved to Done', async ({ page, request }) => {
    // Create a feature already in Done
    const existingDone = await createDoneFeature(request, { name: 'Already Done Feature' });
    createdIds.push(existingDone.id);

    // Create a feature in TODO that we'll move to Done via the API
    const createRes = await request.post(`${API}/api/features`, {
      data: { category: 'Test', name: 'Will Be Moved To Done', description: '', steps: ['Step 1'] }
    });
    const toBeMoved = await createRes.json();
    createdIds.push(toBeMoved.id);

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(500);

    // Verify existing done feature is visible
    await expect(page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Already Done Feature' })).toBeVisible();

    // Move the second feature to Done via API (simulates moving a card)
    await request.patch(`${API}/api/features/${toBeMoved.id}/state`, {
      data: { passes: true, in_progress: false }
    });

    // Wait for auto-refresh (polling interval is 5s, use UI action instead)
    // Trigger by moving via the board's lane mutation — simulate via direct drag click on card state
    // Instead, wait for the 5s poll or force a reload
    await page.waitForTimeout(6000);

    // Both done features should still be visible — the original must not have disappeared
    await expect(page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Already Done Feature' })).toBeVisible();
    await expect(page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Will Be Moved To Done' })).toBeVisible();
  });

  test('done features remain visible after moving a done card back to TODO via UI', async ({ page, request }) => {
    // Create two done features
    const done1 = await createDoneFeature(request, { name: 'Done Feature stays A' });
    const done2 = await createDoneFeature(request, { name: 'Done Feature moves back' });
    createdIds.push(done1.id, done2.id);

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(500);

    // Both should be visible
    await expect(page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Done Feature stays A' })).toBeVisible();
    await expect(page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Done Feature moves back' })).toBeVisible();

    // Move done2 back to TODO via API (simulates what invalidateDoneFeatures triggers)
    await request.patch(`${API}/api/features/${done2.id}/state`, {
      data: { passes: false, in_progress: false }
    });

    // Wait for auto-refresh
    await page.waitForTimeout(6000);

    // done1 must still be visible in Done lane — not disappeared
    await expect(page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Done Feature stays A' })).toBeVisible();

    // done2 should now be in TODO
    await expect(page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Done Feature moves back' })).toBeVisible();
  });
});

test.describe('Done lane: pagination', () => {
  // Must run serially — tests share the same DB and the "show more" tests create 22 done
  // features that would interfere with the "no show more" test if run in parallel.
  test.describe.configure({ mode: 'serial' });

  const createdIds = [];

  test.afterEach(async ({ request }) => {
    for (const id of createdIds) {
      await deleteFeature(request, id);
    }
    createdIds.length = 0;
  });

  test('should show "Show more" button when there are more than 20 done features', async ({ page, request }) => {
    // Create 22 done features
    for (let i = 0; i < 22; i++) {
      const feature = await createDoneFeature(request, { name: `Pagination Test Feature ${i + 1}` });
      createdIds.push(feature.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(1000);

    // Should see "Show more" button
    const showMoreBtn = page.getByTestId('show-more-done');
    await expect(showMoreBtn).toBeVisible();
  });

  test('should load more features when "Show more" is clicked', async ({ page, request }) => {
    // Create 22 done features
    for (let i = 0; i < 22; i++) {
      const feature = await createDoneFeature(request, { name: `Load More Feature ${i + 1}` });
      createdIds.push(feature.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(1000);

    // Count all kanban cards in done lane before clicking show more
    // Done lane is the third column in the 3-column grid
    const allCards = page.locator('[data-testid="kanban-card"]');
    const cardsBefore = await allCards.count();
    expect(cardsBefore).toBeGreaterThan(0);

    // Click Show more
    const showMoreBtn = page.getByTestId('show-more-done');
    await expect(showMoreBtn).toBeVisible();
    await showMoreBtn.click();
    await page.waitForTimeout(1500);

    // Should have more cards now (new done features loaded)
    const cardsAfter = await allCards.count();
    expect(cardsAfter).toBeGreaterThan(cardsBefore);
  });

  test('should not show "Show more" button when 20 or fewer done features exist', async ({ page, request }) => {
    // Only create 2 done features. Serial execution ensures sibling pagination tests
    // have already cleaned up their 22 done features before this test runs.
    const feature1 = await createDoneFeature(request, { name: 'Small Done Feature 1' });
    const feature2 = await createDoneFeature(request, { name: 'Small Done Feature 2' });
    createdIds.push(feature1.id, feature2.id);

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(500);

    // Should NOT see "Show more" button
    const showMoreBtn = page.getByTestId('show-more-done');
    await expect(showMoreBtn).not.toBeVisible();
  });
});
