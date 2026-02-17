import { test, expect } from '@playwright/test';

/**
 * E2E tests for auto-refresh feature.
 * Verifies the board polls for changes every 5 seconds and:
 * - Picks up new data added externally
 * - Does NOT interrupt new feature creation form
 * - Does NOT interrupt drag-and-drop operations
 *
 * Uses isolated test database (port 8001).
 */

const API = 'http://localhost:8001';

async function createFeature(request, overrides = {}) {
  const response = await request.post(`${API}/api/features`, {
    data: {
      category: 'AutoRefresh',
      name: 'Auto Refresh Test Feature',
      description: 'Created for auto-refresh test',
      steps: ['Step 1'],
      ...overrides
    }
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function deleteFeature(request, id) {
  await request.delete(`${API}/api/features/${id}`);
}

test.describe('Auto-refresh: board updates with external changes', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
  });

  test('board picks up a new feature added via API without manual reload', async ({ page, request }) => {
    // Record the current feature count in the TODO lane header
    const todoCountBadge = page.locator('.animate-slide-in').nth(0)
      .locator('.font-mono.text-sm.font-semibold').first();
    const initialCount = parseInt(await todoCountBadge.textContent(), 10);

    // Add a new feature directly via API (simulating external change)
    const feature = await createFeature(request, { name: 'External Auto Refresh Feature' });

    // Wait for the board to auto-refresh (poll interval is 5s; wait up to 8s)
    await expect(
      page.locator('[data-testid="kanban-card"]').filter({ hasText: 'External Auto Refresh Feature' })
    ).toBeVisible({ timeout: 8000 });

    // Count should have increased
    const newCount = parseInt(await todoCountBadge.textContent(), 10);
    expect(newCount).toBeGreaterThan(initialCount);

    await deleteFeature(request, feature.id);
  });

  test('board removes a deleted feature after auto-refresh', async ({ page, request }) => {
    // Create a feature so we can verify its removal
    const feature = await createFeature(request, { name: 'Feature To Be Deleted Externally' });

    // Wait for the feature to appear on the board
    await expect(
      page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Feature To Be Deleted Externally' })
    ).toBeVisible({ timeout: 8000 });

    // Delete it via API (simulating external deletion)
    await deleteFeature(request, feature.id);

    // Board should stop showing the card after the next poll
    await expect(
      page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Feature To Be Deleted Externally' })
    ).not.toBeVisible({ timeout: 8000 });
  });
});

test.describe('Auto-refresh: does NOT interrupt new feature creation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
  });

  test('new feature form stays open and retains typed text during a refresh cycle', async ({ page, request }) => {
    // Open the new feature form
    await page.locator('button[aria-label="Add feature to TODO"]').click();

    // Verify form is open
    const titleInput = page.locator('input[placeholder*="Enter feature title"]');
    await expect(titleInput).toBeVisible();

    // Type a title
    await titleInput.fill('My Typed Title During Refresh');

    // Trigger an external change so a refresh would return different data
    const feature = await createFeature(request, { name: 'Background Change During Form' });

    // Wait well past the 5-second poll interval (7s)
    await page.waitForTimeout(7000);

    // The form must still be open (polling is paused while form is open)
    await expect(titleInput).toBeVisible();

    // The typed text must be preserved
    await expect(titleInput).toHaveValue('My Typed Title During Refresh');

    // The new card from the background change should NOT have appeared yet
    // (because the poll was paused)
    // After cancelling the form, the next poll should show it
    await page.click('button:has-text("Cancel")');

    // Now polling resumes; the background feature should appear within 6s
    await expect(
      page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Background Change During Form' })
    ).toBeVisible({ timeout: 8000 });

    await deleteFeature(request, feature.id);
  });

  test('description field retains value after a refresh cycle while form is open', async ({ page, request }) => {
    await page.locator('button[aria-label="Add feature to TODO"]').click();

    const titleInput = page.locator('input[placeholder*="Enter feature title"]');
    const descInput = page.locator('textarea[placeholder*="Describe"]');
    await expect(titleInput).toBeVisible();

    await titleInput.fill('Refresh Survival Title');
    await descInput.fill('This description should survive the refresh interval');

    // Wait for more than one full poll cycle (5s × 2 = 10s; wait 11s to be safe)
    await page.waitForTimeout(11000);

    // Form is still open, values intact
    await expect(titleInput).toHaveValue('Refresh Survival Title');
    await expect(descInput).toHaveValue('This description should survive the refresh interval');

    // Cancel without saving
    await page.click('button:has-text("Cancel")');
  });
});

test.describe('Auto-refresh: does NOT interrupt drag-and-drop', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
  });

  test('board does not refresh while a drag is in progress', async ({ page, request }) => {
    const feature = await createFeature(request, { name: 'Drag Refresh Safety Card' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Drag Refresh Safety Card' });
    await card.waitFor({ state: 'visible' });

    // Use JS to simulate drag start (sets isDragging=true via callback)
    const featureId = feature.id;
    await page.evaluate((fId) => {
      const cardEl = document.querySelector(`[data-feature-id="${fId}"]`);
      if (!cardEl) return;
      const dt = new DataTransfer();
      dt.setData('text/plain', String(fId));
      cardEl.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }));
    }, featureId);

    // Inject a new feature via API while the drag is in progress
    const bgFeature = await createFeature(request, { name: 'Background Card Injected During Drag' });

    // Wait for one full poll cycle; the new card should NOT appear (polling paused)
    await page.waitForTimeout(6000);

    // Card injected during drag should not be visible yet
    await expect(
      page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Background Card Injected During Drag' })
    ).not.toBeVisible();

    // Simulate drag end (resumes polling)
    await page.evaluate((fId) => {
      const cardEl = document.querySelector(`[data-feature-id="${fId}"]`);
      if (!cardEl) return;
      const dt = new DataTransfer();
      cardEl.dispatchEvent(new DragEvent('dragend', { bubbles: true, dataTransfer: dt }));
    }, featureId);

    // After drag ends, the next poll should show the background card
    await expect(
      page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Background Card Injected During Drag' })
    ).toBeVisible({ timeout: 8000 });

    await deleteFeature(request, feature.id);
    await deleteFeature(request, bgFeature.id);
  });
});
