import { test, expect } from '@playwright/test';

/**
 * Portrait Mobile Regression Tests — iPhone 14 (390x844)
 *
 * Runs under the `mobile-portrait` Playwright project which sets the
 * viewport to 390x844 and emulates an iPhone 14.  Covers the three
 * areas most likely to regress on narrow screens:
 *
 *   1. Header — no horizontal overflow, all controls reachable
 *   2. Kanban lanes — tab switcher present and functional
 *   3. Feature cards — title and category readable, no overflow
 */

test.beforeEach(async ({ page }) => {
  // Ensure portrait viewport regardless of which Playwright project runs this file
  await page.setViewportSize({ width: 390, height: 844 });

  // Stub autopilot endpoint so tests don't depend on that backend feature
  await page.route('**/api/autopilot/status', route => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: false,
        current_feature_id: null,
        current_feature_name: null,
        last_error: null,
        log: [],
      }),
    });
  });

  await page.goto('/');
  await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
});

// ---------------------------------------------------------------------------
// 1. Header
// ---------------------------------------------------------------------------

test.describe('Header at 390px portrait', () => {
  test('title "FEATURE DASHBOARD" is visible', async ({ page }) => {
    await expect(page.getByText('FEATURE DASHBOARD')).toBeVisible();
  });

  test('no horizontal scroll / overflow', async ({ page }) => {
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
  });

  test('settings button is visible', async ({ page }) => {
    await expect(page.getByTestId('settings-btn')).toBeVisible();
  });

  test('plan tasks button is visible', async ({ page }) => {
    await expect(page.getByTestId('plan-tasks-btn')).toBeVisible();
  });

  test('plan tasks button is within viewport bounds (not clipped off-screen)', async ({ page }) => {
    const btn = page.getByTestId('plan-tasks-btn');
    const box = await btn.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.x).toBeGreaterThanOrEqual(0);
  });

  test('autopilot toggle is visible', async ({ page }) => {
    await expect(page.getByTestId('autopilot-toggle')).toBeVisible();
  });

  test('autopilot toggle shows icon-only on mobile (text label hidden)', async ({ page }) => {
    const toggle = page.getByTestId('autopilot-toggle');
    // On mobile, the text span is hidden via CSS (hidden md:inline).
    // Use the span locator + toBeHidden() since toContainText checks textContent (includes hidden text).
    const textSpan = toggle.locator('span').filter({ hasText: 'Auto-Pilot' });
    await expect(textSpan).toBeHidden();
  });

  test('mobile stats row is shown, desktop stats row is hidden', async ({ page }) => {
    await expect(page.getByTestId('header-stats-mobile')).toBeVisible();
    await expect(page.getByTestId('header-stats-desktop')).toBeHidden();
  });
});

// ---------------------------------------------------------------------------
// 2. Lane navigation — tab switcher
// ---------------------------------------------------------------------------

test.describe('Tab switcher at 390px portrait', () => {
  test('mobile lane tab bar is visible', async ({ page }) => {
    await expect(page.getByTestId('mobile-lane-tabs')).toBeVisible();
  });

  test('all three lane tabs are rendered', async ({ page }) => {
    await expect(page.getByTestId('lane-tab-todo')).toBeVisible();
    await expect(page.getByTestId('lane-tab-inProgress')).toBeVisible();
    await expect(page.getByTestId('lane-tab-done')).toBeVisible();
  });

  test('TODO lane is shown by default, others hidden', async ({ page }) => {
    const todo = page.locator('h2').filter({ hasText: 'TODO' });
    await expect(todo.first()).toBeVisible();

    await expect(page.locator('h2').filter({ hasText: 'IN PROGRESS' })).toBeHidden();
    await expect(page.locator('h2').filter({ hasText: 'DONE' })).toBeHidden();
  });

  test('tapping IN PROGRESS tab switches to that lane', async ({ page }) => {
    await page.getByTestId('lane-tab-inProgress').click();

    await expect(page.locator('h2').filter({ hasText: 'IN PROGRESS' })).toBeVisible();
    await expect(page.locator('h2').filter({ hasText: 'TODO' })).toBeHidden();
  });

  test('tapping DONE tab switches to that lane', async ({ page }) => {
    await page.getByTestId('lane-tab-done').click();

    await expect(page.locator('h2').filter({ hasText: 'DONE' })).toBeVisible();
    await expect(page.locator('h2').filter({ hasText: 'TODO' })).toBeHidden();
  });

  test('can switch back to TODO after navigating away', async ({ page }) => {
    await page.getByTestId('lane-tab-done').click();
    await page.getByTestId('lane-tab-todo').click();

    await expect(page.locator('h2').filter({ hasText: 'TODO' }).first()).toBeVisible();
    await expect(page.locator('h2').filter({ hasText: 'DONE' })).toBeHidden();
  });

  test('no horizontal overflow after tab switch', async ({ page }) => {
    await page.getByTestId('lane-tab-inProgress').click();
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
  });
});

// ---------------------------------------------------------------------------
// 3. Feature cards
// ---------------------------------------------------------------------------

test.describe('Feature cards at 390px portrait', () => {
  test('at least one card is visible in the TODO lane', async ({ page }) => {
    const cards = page.getByTestId('kanban-card');
    await cards.first().waitFor({ state: 'visible' });
    await expect(cards.first()).toBeVisible();
  });

  test('no horizontal overflow with cards rendered', async ({ page }) => {
    await page.getByTestId('kanban-card').first().waitFor({ state: 'visible' });
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
  });

  test('cards are not wider than the viewport', async ({ page }) => {
    await page.getByTestId('kanban-card').first().waitFor({ state: 'visible' });

    const cardWidths = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[data-testid="kanban-card"]'))
        .map(el => el.getBoundingClientRect().width)
    );

    expect(cardWidths.length).toBeGreaterThan(0);
    for (const w of cardWidths) {
      expect(w).toBeLessThanOrEqual(390);
    }
  });

  test('card title (h3) is visible', async ({ page }) => {
    const firstCard = page.getByTestId('kanban-card').first();
    await firstCard.waitFor({ state: 'visible' });
    await expect(firstCard.locator('h3')).toBeVisible();
  });

  test('category badge is visible and fits within the card', async ({ page }) => {
    const firstCard = page.getByTestId('kanban-card').first();
    await firstCard.waitFor({ state: 'visible' });

    const badge = firstCard.locator('span.font-mono.truncate');
    await expect(badge).toBeVisible();

    const badgeBox = await badge.boundingBox();
    const cardBox = await firstCard.boundingBox();
    if (badgeBox && cardBox) {
      expect(badgeBox.x + badgeBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
    }
  });

  test('tapping a card opens the detail panel', async ({ page }) => {
    const firstCard = page.getByTestId('kanban-card').first();
    await firstCard.waitFor({ state: 'visible' });
    await firstCard.click();
    await expect(page.getByTestId('detail-panel')).toBeVisible({ timeout: 5000 });
  });
});

// ---------------------------------------------------------------------------
// 4. Detail panel — fits within 390px portrait
// ---------------------------------------------------------------------------

test.describe('Detail panel at 390px portrait', () => {
  test('panel opens and fits within the viewport width', async ({ page }) => {
    const firstCard = page.getByTestId('kanban-card').first();
    await firstCard.waitFor({ state: 'visible' });
    await firstCard.click();

    const panel = page.getByTestId('detail-panel');
    await expect(panel).toBeVisible({ timeout: 5000 });

    const box = await panel.boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeLessThanOrEqual(390);
  });

  test('no horizontal overflow while detail panel is open', async ({ page }) => {
    const firstCard = page.getByTestId('kanban-card').first();
    await firstCard.waitFor({ state: 'visible' });
    await firstCard.click();
    await expect(page.getByTestId('detail-panel')).toBeVisible({ timeout: 5000 });

    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
  });

  test('close button is visible inside the panel', async ({ page }) => {
    const firstCard = page.getByTestId('kanban-card').first();
    await firstCard.waitFor({ state: 'visible' });
    await firstCard.click();
    await expect(page.getByTestId('detail-panel')).toBeVisible({ timeout: 5000 });

    await expect(page.getByTestId('detail-panel-close')).toBeVisible();
  });

  test('close button dismisses the panel', async ({ page }) => {
    const firstCard = page.getByTestId('kanban-card').first();
    await firstCard.waitFor({ state: 'visible' });
    await firstCard.click();
    await expect(page.getByTestId('detail-panel')).toBeVisible({ timeout: 5000 });

    await page.getByTestId('detail-panel-close').click();
    await expect(page.getByTestId('detail-panel')).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 5. Settings panel — fits within 390px portrait
// ---------------------------------------------------------------------------

test.describe('Settings panel at 390px portrait', () => {
  test('panel opens and fits within the viewport width', async ({ page }) => {
    await page.getByTestId('settings-btn').click();

    const panel = page.getByTestId('settings-panel');
    await expect(panel).toBeVisible({ timeout: 5000 });

    const box = await panel.boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeLessThanOrEqual(390);
  });

  test('no horizontal overflow while settings panel is open', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible({ timeout: 5000 });

    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
  });

  test('close button is visible inside the panel', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible({ timeout: 5000 });

    await expect(page.getByTestId('settings-panel-close')).toBeVisible();
  });

  test('close button dismisses the panel', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible({ timeout: 5000 });

    await page.getByTestId('settings-panel-close').click();
    await expect(page.getByTestId('settings-panel')).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 6. Settings panel content scrolling — plan prompt visible on mobile
// ---------------------------------------------------------------------------

test.describe('Settings panel scrolling at 390px portrait', () => {
  test('plan tasks prompt textarea is reachable by scrolling within the panel', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible({ timeout: 5000 });

    // Wait for content to load (first textarea becomes visible)
    await page.getByTestId('prompt-template-input').waitFor({ state: 'visible' });

    // The plan tasks textarea requires scrolling within the panel on mobile
    const planTextarea = page.getByTestId('plan-prompt-template-input');
    await planTextarea.scrollIntoViewIfNeeded();

    // After scrolling within the panel, the textarea must be in the viewport
    await expect(planTextarea).toBeInViewport();
  });

  test('plan tasks prompt textarea is interactable after scrolling on mobile', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible({ timeout: 5000 });

    await page.getByTestId('prompt-template-input').waitFor({ state: 'visible' });

    const planTextarea = page.getByTestId('plan-prompt-template-input');
    await planTextarea.scrollIntoViewIfNeeded();
    await expect(planTextarea).toBeInViewport();

    // Should be clickable and focusable
    await planTextarea.click();
    await expect(planTextarea).toBeFocused();
  });

  test('save button remains accessible after scrolling to plan template', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible({ timeout: 5000 });

    await page.getByTestId('prompt-template-input').waitFor({ state: 'visible' });

    // Scroll to the bottom of the settings panel to reach the plan template
    const planTextarea = page.getByTestId('plan-prompt-template-input');
    await planTextarea.scrollIntoViewIfNeeded();

    // The save button is in the footer (sticky), so it should remain visible
    const saveBtn = page.getByTestId('settings-save-btn');
    await expect(saveBtn).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 7. Mobile card move via long press (touch drag-and-drop alternative)
// ---------------------------------------------------------------------------

const API = 'http://localhost:8001';

async function createTestFeature(request, overrides = {}) {
  const response = await request.post(`${API}/api/features`, {
    data: {
      category: 'Test',
      name: 'Mobile Move Test Card',
      description: 'Created for mobile long-press move test',
      steps: [],
      ...overrides,
    },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function deleteTestFeature(request, id) {
  await request.delete(`${API}/api/features/${id}`);
}

async function getTestFeature(request, id) {
  const res = await request.get(`${API}/api/features/${id}`);
  return res.json();
}

/**
 * Simulate a long press on a kanban card by dispatching TouchEvent sequences.
 * Waits 600ms (past the 500ms LONG_PRESS_MS threshold) before lifting the finger.
 */
async function simulateLongPress(page, featureId) {
  await page.evaluate((id) => {
    const card = document.querySelector(`[data-feature-id="${id}"]`);
    if (!card) return;
    const rect = card.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const touch = new Touch({ identifier: 1, target: card, clientX: x, clientY: y, pageX: x, pageY: y });
    card.dispatchEvent(new TouchEvent('touchstart', {
      bubbles: true,
      cancelable: true,
      touches: [touch],
      changedTouches: [touch],
    }));
  }, featureId);

  // Hold for longer than LONG_PRESS_MS (500ms) to trigger the timer
  await page.waitForTimeout(650);

  await page.evaluate((id) => {
    const card = document.querySelector(`[data-feature-id="${id}"]`);
    if (!card) return;
    card.dispatchEvent(new TouchEvent('touchend', {
      bubbles: true,
      cancelable: true,
      touches: [],
      changedTouches: [],
    }));
  }, featureId);
}

test.describe('Mobile card move via long press', () => {
  test('long press on a card opens the move sheet', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Long Press Opens Sheet' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Long Press Opens Sheet' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPress(page, feature.id);

    await expect(page.getByTestId('mobile-move-sheet')).toBeVisible({ timeout: 3000 });

    await deleteTestFeature(request, feature.id);
  });

  test('move sheet shows the feature name', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Sheet Shows Feature Name' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Sheet Shows Feature Name' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPress(page, feature.id);

    const sheet = page.getByTestId('mobile-move-sheet');
    await expect(sheet).toBeVisible({ timeout: 3000 });
    await expect(sheet).toContainText('Sheet Shows Feature Name');

    await deleteTestFeature(request, feature.id);
  });

  test('move sheet has buttons for all three lanes', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Sheet Has Lane Buttons' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Sheet Has Lane Buttons' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPress(page, feature.id);

    await expect(page.getByTestId('mobile-move-sheet')).toBeVisible({ timeout: 3000 });
    await expect(page.getByTestId('move-to-todo')).toBeVisible();
    await expect(page.getByTestId('move-to-inProgress')).toBeVisible();
    await expect(page.getByTestId('move-to-done')).toBeVisible();

    await deleteTestFeature(request, feature.id);
  });

  test('TODO lane button is marked as current for a TODO card', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'TODO Current Lane Test' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'TODO Current Lane Test' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPress(page, feature.id);

    await expect(page.getByTestId('mobile-move-sheet')).toBeVisible({ timeout: 3000 });

    const todoBtn = page.getByTestId('move-to-todo');
    await expect(todoBtn).toContainText('current');
    await expect(todoBtn).toBeDisabled();

    await deleteTestFeature(request, feature.id);
  });

  test('tapping IN PROGRESS in sheet moves card and closes sheet', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Mobile Move To InProgress' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Mobile Move To InProgress' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPress(page, feature.id);

    await expect(page.getByTestId('mobile-move-sheet')).toBeVisible({ timeout: 3000 });
    await page.getByTestId('move-to-inProgress').click();

    // Sheet should close
    await expect(page.getByTestId('mobile-move-sheet')).not.toBeVisible({ timeout: 3000 });

    // Toast notification appears
    await expect(page.getByText('Moved to In Progress', { exact: true })).toBeVisible({ timeout: 8000 });

    // Verify API state updated
    await page.waitForTimeout(500);
    const updated = await getTestFeature(request, feature.id);
    expect(updated.in_progress).toBe(true);
    expect(updated.passes).toBe(false);

    await deleteTestFeature(request, feature.id);
  });

  test('tapping DONE in sheet moves card to done lane', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Mobile Move To Done' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Mobile Move To Done' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPress(page, feature.id);

    await expect(page.getByTestId('mobile-move-sheet')).toBeVisible({ timeout: 3000 });
    await page.getByTestId('move-to-done').click();

    await expect(page.getByTestId('mobile-move-sheet')).not.toBeVisible({ timeout: 3000 });
    await expect(page.getByText('Moved to Done', { exact: true })).toBeVisible({ timeout: 8000 });

    await page.waitForTimeout(500);
    const updated = await getTestFeature(request, feature.id);
    expect(updated.passes).toBe(true);
    expect(updated.in_progress).toBe(false);

    await deleteTestFeature(request, feature.id);
  });

  test('closing sheet via backdrop keeps card in original state', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Mobile Sheet Dismiss Test' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Mobile Sheet Dismiss Test' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPress(page, feature.id);

    await expect(page.getByTestId('mobile-move-sheet')).toBeVisible({ timeout: 3000 });
    await page.getByTestId('mobile-move-sheet-backdrop').click();

    await expect(page.getByTestId('mobile-move-sheet')).not.toBeVisible({ timeout: 2000 });

    // Feature should remain in TODO
    const current = await getTestFeature(request, feature.id);
    expect(current.in_progress).toBe(false);
    expect(current.passes).toBe(false);

    await deleteTestFeature(request, feature.id);
  });

  test('closing sheet via X button keeps card in original state', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Mobile Sheet Close Btn Test' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Mobile Sheet Close Btn Test' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPress(page, feature.id);

    await expect(page.getByTestId('mobile-move-sheet')).toBeVisible({ timeout: 3000 });
    await page.getByTestId('mobile-move-sheet-close').click();

    await expect(page.getByTestId('mobile-move-sheet')).not.toBeVisible({ timeout: 2000 });

    const current = await getTestFeature(request, feature.id);
    expect(current.in_progress).toBe(false);
    expect(current.passes).toBe(false);

    await deleteTestFeature(request, feature.id);
  });

  test('move sheet fits within 390px viewport (no overflow)', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Sheet Fits Viewport Test' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Sheet Fits Viewport Test' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPress(page, feature.id);

    await expect(page.getByTestId('mobile-move-sheet')).toBeVisible({ timeout: 3000 });

    const box = await page.getByTestId('mobile-move-sheet').boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeLessThanOrEqual(390);
    expect(box.x).toBeGreaterThanOrEqual(0);

    // Dismiss
    await page.getByTestId('mobile-move-sheet-close').click();
    await deleteTestFeature(request, feature.id);
  });
});
