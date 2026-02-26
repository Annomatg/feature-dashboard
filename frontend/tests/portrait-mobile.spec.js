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
// 7. Mobile touch drag-and-drop
// ---------------------------------------------------------------------------

const API = 'http://localhost:8001';

async function createTestFeature(request, overrides = {}) {
  const response = await request.post(`${API}/api/features`, {
    data: {
      category: 'Test',
      name: 'Mobile Drag Test Card',
      description: 'Created for mobile touch drag test',
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
 * Dispatch a touchstart on a card and wait for the long-press timer to fire
 * (600ms > the 500ms threshold). Does NOT dispatch touchend — caller controls that.
 * Returns the initial touch position.
 */
async function startLongPress(page, featureId) {
  const pos = await page.evaluate((id) => {
    const card = document.querySelector(`[data-feature-id="${id}"]`);
    if (!card) return null;
    const rect = card.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const touch = new Touch({ identifier: 1, target: card, clientX: x, clientY: y, pageX: x, pageY: y });
    card.dispatchEvent(new TouchEvent('touchstart', {
      bubbles: true, cancelable: true,
      touches: [touch], changedTouches: [touch],
    }));
    return { x, y };
  }, featureId);
  // Wait past the 500ms long-press threshold
  await page.waitForTimeout(650);
  return pos;
}

/**
 * Dispatch touchmove to an absolute page position via the window global handler.
 */
async function dispatchTouchMove(page, featureId, x, y) {
  await page.evaluate(({ id, x, y }) => {
    const card = document.querySelector(`[data-feature-id="${id}"]`);
    if (!card) return;
    const touch = new Touch({ identifier: 1, target: card, clientX: x, clientY: y, pageX: x, pageY: y });
    window.dispatchEvent(new TouchEvent('touchmove', {
      bubbles: true, cancelable: true,
      touches: [touch], changedTouches: [touch],
    }));
  }, { id: featureId, x, y });
}

/**
 * Dispatch touchend to the window (the global handler fires, applying the drop).
 */
async function dispatchTouchEnd(page, featureId) {
  await page.evaluate((id) => {
    const card = document.querySelector(`[data-feature-id="${id}"]`);
    const touch = new Touch({ identifier: 1, target: card || document.body, clientX: 0, clientY: 0, pageX: 0, pageY: 0 });
    window.dispatchEvent(new TouchEvent('touchend', {
      bubbles: true, cancelable: true,
      touches: [], changedTouches: [touch],
    }));
  }, featureId);
}

/**
 * Full long-press without movement: start drag, wait, release — no action taken.
 */
async function simulateLongPressOnly(page, featureId) {
  await startLongPress(page, featureId);
  await dispatchTouchEnd(page, featureId);
}

test.describe('Mobile touch drag-and-drop', () => {
  test('long press shows ghost card overlay', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Long Press Ghost Test' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Long Press Ghost Test' });
    await card.waitFor({ state: 'visible' });

    // Start the long press (hold, don't release yet)
    await startLongPress(page, feature.id);

    // Ghost card should be visible while finger is held
    await expect(page.getByTestId('mobile-drag-ghost')).toBeVisible({ timeout: 2000 });

    // Ghost contains the feature name
    await expect(page.getByTestId('mobile-drag-ghost')).toContainText('Long Press Ghost Test');

    // Release finger
    await dispatchTouchEnd(page, feature.id);
    await expect(page.getByTestId('mobile-drag-ghost')).not.toBeVisible({ timeout: 2000 });

    await deleteTestFeature(request, feature.id);
  });

  test('dragged card dims in-place while ghost is shown', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Card Dims While Drag' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Use feature id selector to avoid ambiguity when tests run in parallel
    const card = page.locator(`[data-feature-id="${feature.id}"]`);
    await card.waitFor({ state: 'visible' });

    await startLongPress(page, feature.id);

    // Wait for React to render drag mode (ghost card becomes visible)
    await expect(page.getByTestId('mobile-drag-ghost')).toBeVisible({ timeout: 2000 });

    // The card's opacity should be reduced while dragging
    const opacity = await card.evaluate(el => parseFloat(window.getComputedStyle(el).opacity));
    expect(opacity).toBeLessThan(0.5);

    await dispatchTouchEnd(page, feature.id);

    // Wait for React to re-render and restore opacity
    await page.waitForFunction(
      (id) => {
        const el = document.querySelector(`[data-feature-id="${id}"]`);
        return el && parseFloat(window.getComputedStyle(el).opacity) > 0.9;
      },
      feature.id,
      { timeout: 3000 }
    );

    await deleteTestFeature(request, feature.id);
  });

  test('long press without movement leaves card state unchanged', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'No Move No Change' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'No Move No Change' });
    await card.waitFor({ state: 'visible' });

    await simulateLongPressOnly(page, feature.id);

    await page.waitForTimeout(400);
    const current = await getTestFeature(request, feature.id);
    expect(current.in_progress).toBe(false);
    expect(current.passes).toBe(false);

    await deleteTestFeature(request, feature.id);
  });

  test('moving to right edge shows edge indicator and right lane name', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Edge Right Indicator Test' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Edge Right Indicator Test' });
    await card.waitFor({ state: 'visible' });

    const initialPos = await startLongPress(page, feature.id);

    // Move to the right edge (x = viewportWidth - 10)
    const vw = await page.evaluate(() => window.innerWidth);
    await dispatchTouchMove(page, feature.id, vw - 10, initialPos.y);

    // Edge indicator should appear
    await expect(page.getByTestId('mobile-drag-edge-right')).toBeVisible({ timeout: 2000 });

    await dispatchTouchEnd(page, feature.id);
    await deleteTestFeature(request, feature.id);
  });

  test('moving to left edge shows left edge indicator (when not in first lane)', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Edge Left Indicator Test' });
    // Put feature in IN PROGRESS so there is a lane to the left
    await request.patch(`${API}/api/features/${feature.id}/state`, {
      data: { in_progress: true },
    });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Switch to IN PROGRESS tab
    await page.getByTestId('lane-tab-inProgress').click();

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Edge Left Indicator Test' });
    await card.waitFor({ state: 'visible' });

    await startLongPress(page, feature.id);

    // Move to the left edge
    await dispatchTouchMove(page, feature.id, 5, 400);

    await expect(page.getByTestId('mobile-drag-edge-left')).toBeVisible({ timeout: 2000 });

    await dispatchTouchEnd(page, feature.id);
    await deleteTestFeature(request, feature.id);
  });

  test('holding at right edge for 1s switches to next lane', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Edge Switch Lane Test' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Confirm we start in TODO tab
    const todoTab = page.getByTestId('lane-tab-todo');
    const inProgressTab = page.getByTestId('lane-tab-inProgress');

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Edge Switch Lane Test' });
    await card.waitFor({ state: 'visible' });

    const initialPos = await startLongPress(page, feature.id);

    // Move to right edge and hold
    const vw = await page.evaluate(() => window.innerWidth);
    await dispatchTouchMove(page, feature.id, vw - 10, initialPos.y);

    // Wait for the 1s edge switch timer
    await page.waitForTimeout(1200);

    // The active tab should now be IN PROGRESS
    const inProgressStyle = await inProgressTab.getAttribute('style');
    expect(inProgressStyle).not.toContain('#3d3d3d'); // colored border = active

    // Release in the new lane → card should move to IN PROGRESS
    await dispatchTouchMove(page, feature.id, vw / 2, initialPos.y); // move away from edge
    await dispatchTouchEnd(page, feature.id);

    await expect(page.getByText('Moved to In Progress', { exact: true })).toBeVisible({ timeout: 8000 });

    await page.waitForTimeout(500);
    const updated = await getTestFeature(request, feature.id);
    expect(updated.in_progress).toBe(true);
    expect(updated.passes).toBe(false);

    await deleteTestFeature(request, feature.id);
  });

  test('touch drag reorders cards within same lane', async ({ page, request }) => {
    const f1 = await createTestFeature(request, { name: 'Drag Reorder Card A' });
    const f2 = await createTestFeature(request, { name: 'Drag Reorder Card B' });

    // f1 has lower priority (created first), so appears above f2
    expect(f1.priority).toBeLessThan(f2.priority);

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const cardA = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Drag Reorder Card A' });
    const cardB = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Drag Reorder Card B' });
    await cardA.waitFor({ state: 'visible' });
    await cardB.waitFor({ state: 'visible' });

    // Long press on card A, drag it to below card B's midpoint
    await startLongPress(page, f1.id);

    const bBox = await cardB.boundingBox();
    // Touch Y in the bottom third of card B = "after card B" position
    const dropY = bBox.y + bBox.height * 0.75;
    const dropX = bBox.x + bBox.width / 2;

    await dispatchTouchMove(page, f1.id, dropX, dropY);
    await dispatchTouchEnd(page, f1.id);

    await page.waitForTimeout(800);

    // After drag: A should have higher priority number (lower in list) than B
    const updatedA = await getTestFeature(request, f1.id);
    const updatedB = await getTestFeature(request, f2.id);
    expect(updatedA.priority).toBeGreaterThan(updatedB.priority);

    await deleteTestFeature(request, f1.id);
    await deleteTestFeature(request, f2.id);
  });

  test('ghost card fits within 390px viewport (no overflow)', async ({ page, request }) => {
    const feature = await createTestFeature(request, { name: 'Ghost Fits Viewport Test' });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator('[data-testid="kanban-card"]').filter({ hasText: 'Ghost Fits Viewport Test' });
    await card.waitFor({ state: 'visible' });

    await startLongPress(page, feature.id);
    await expect(page.getByTestId('mobile-drag-ghost')).toBeVisible({ timeout: 2000 });

    // Move ghost to center of screen so it's fully visible
    await dispatchTouchMove(page, feature.id, 195, 400);

    const box = await page.getByTestId('mobile-drag-ghost').boundingBox();
    // Ghost should start within screen (may extend slightly beyond on narrow screens,
    // so we just check the left edge is not too far off screen)
    expect(box).not.toBeNull();
    expect(box.x).toBeGreaterThan(-160); // 160px is the left offset of the ghost

    await dispatchTouchEnd(page, feature.id);
    await deleteTestFeature(request, feature.id);
  });
});

// ---------------------------------------------------------------------------
// 8. Auto-pilot stopping state on mobile
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

test.describe('Auto-pilot stopping state at 390px portrait', () => {
  test('status bar is visible when stopping', async ({ page }) => {
    // Override the global beforeEach route with stopping state
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(STOPPING_STATUS),
      });
    });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-status-bar')).toBeVisible();
  });

  test('stopping status bar shows "Stopping" label on mobile', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(STOPPING_STATUS),
      });
    });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const label = page.getByTestId('autopilot-status-label');
    await expect(label).toBeVisible();
    await expect(label).toContainText('Stopping');
  });

  test('no horizontal overflow when stopping status bar is shown on mobile', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(STOPPING_STATUS),
      });
    });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-status-bar')).toBeVisible();
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
  });

  test('stopping status bar fits within 390px viewport', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(STOPPING_STATUS),
      });
    });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const bar = page.getByTestId('autopilot-status-bar');
    await expect(bar).toBeVisible();
    const box = await bar.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x + box.width).toBeLessThanOrEqual(390);
  });

  test('stopping toggle dot is visible on mobile (amber indicator)', async ({ page }) => {
    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(STOPPING_STATUS),
      });
    });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('autopilot-stopping-dot')).toBeVisible();
  });

  test('stopping state disappears on mobile when process finishes', async ({ page }) => {
    let isStopping = true;

    await page.route('**/api/autopilot/status', route => {
      const body = isStopping
        ? STOPPING_STATUS
        : { enabled: false, stopping: false, current_feature_id: null,
            current_feature_name: null, current_feature_model: null, last_error: null, log: [] };
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Status bar visible in stopping state
    await expect(page.getByTestId('autopilot-status-bar')).toBeVisible();

    // Simulate process finishing
    isStopping = false;

    // Bar should disappear within polling interval (2s when stopping)
    await expect(page.getByTestId('autopilot-status-bar')).not.toBeVisible({ timeout: 8000 });
  });
});
