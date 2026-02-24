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

  test('autopilot toggle is visible', async ({ page }) => {
    await expect(page.getByTestId('autopilot-toggle')).toBeVisible();
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
