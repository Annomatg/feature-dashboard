import { test, expect } from '@playwright/test';

/**
 * Mobile Card Scaling Tests
 *
 * Verifies that feature cards render correctly at portrait mobile widths:
 * - No horizontal overflow/clipping
 * - Category badges truncate rather than breaking the layout
 * - Feature names are readable (visible)
 * - Cards are tappable (click opens detail panel)
 */

test.describe('Mobile Card Scaling', () => {
  test.beforeEach(async ({ page }) => {
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

  test.describe('Mobile portrait (375px — iPhone SE)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
    });

    test('kanban cards are visible at 375px', async ({ page }) => {
      const cards = page.getByTestId('kanban-card');
      const count = await cards.count();
      expect(count).toBeGreaterThan(0);
      // At least the first card is visible
      await expect(cards.first()).toBeVisible();
    });

    test('no horizontal scroll / overflow at 375px with cards visible', async ({ page }) => {
      // Wait for cards to render
      await page.getByTestId('kanban-card').first().waitFor({ state: 'visible' });

      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(375);
    });

    test('cards do not overflow their lane container at 375px', async ({ page }) => {
      await page.getByTestId('kanban-card').first().waitFor({ state: 'visible' });

      // Check that no card is wider than the viewport
      const cardWidths = await page.evaluate(() => {
        const cards = document.querySelectorAll('[data-testid="kanban-card"]');
        return Array.from(cards).map(card => card.getBoundingClientRect().width);
      });

      expect(cardWidths.length).toBeGreaterThan(0);
      for (const width of cardWidths) {
        expect(width).toBeLessThanOrEqual(375);
      }
    });

    test('feature names are visible on cards at 375px', async ({ page }) => {
      const firstCard = page.getByTestId('kanban-card').first();
      await firstCard.waitFor({ state: 'visible' });

      // h3 inside the card should be visible
      const name = firstCard.locator('h3');
      await expect(name).toBeVisible();
    });

    test('category badges are visible and do not overflow the card', async ({ page }) => {
      const firstCard = page.getByTestId('kanban-card').first();
      await firstCard.waitFor({ state: 'visible' });

      // The category span should be visible
      const badge = firstCard.locator('span.font-mono.truncate');
      await expect(badge).toBeVisible();

      // Badge right edge should not exceed card right edge
      const badgeBounds = await badge.boundingBox();
      const cardBounds = await firstCard.boundingBox();
      if (badgeBounds && cardBounds) {
        expect(badgeBounds.x + badgeBounds.width).toBeLessThanOrEqual(
          cardBounds.x + cardBounds.width + 1 // 1px tolerance
        );
      }
    });

    test('tapping a card opens the detail panel', async ({ page }) => {
      const firstCard = page.getByTestId('kanban-card').first();
      await firstCard.waitFor({ state: 'visible' });
      await firstCard.click();

      // Detail panel should open
      await expect(page.getByTestId('detail-panel')).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Mobile portrait (430px — iPhone Pro Max)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 430, height: 932 });
    });

    test('cards are visible at 430px', async ({ page }) => {
      const cards = page.getByTestId('kanban-card');
      await cards.first().waitFor({ state: 'visible' });
      await expect(cards.first()).toBeVisible();
    });

    test('no horizontal overflow at 430px', async ({ page }) => {
      await page.getByTestId('kanban-card').first().waitFor({ state: 'visible' });
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(430);
    });

    test('tapping a card opens the detail panel at 430px', async ({ page }) => {
      const firstCard = page.getByTestId('kanban-card').first();
      await firstCard.waitFor({ state: 'visible' });
      await firstCard.click();
      await expect(page.getByTestId('detail-panel')).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Desktop (1280px) — regression', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
    });

    test('cards are still visible on desktop', async ({ page }) => {
      const cards = page.getByTestId('kanban-card');
      await cards.first().waitFor({ state: 'visible' });
      await expect(cards.first()).toBeVisible();
    });

    test('clicking a card still opens the detail panel on desktop', async ({ page }) => {
      const firstCard = page.getByTestId('kanban-card').first();
      await firstCard.waitFor({ state: 'visible' });
      await firstCard.click();
      await expect(page.getByTestId('detail-panel')).toBeVisible({ timeout: 5000 });
    });

    test('no horizontal overflow on desktop', async ({ page }) => {
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(1280);
    });
  });
});
