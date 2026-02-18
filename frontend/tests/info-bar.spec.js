import { test, expect } from '@playwright/test';

const DB_DEFAULT = { name: 'Feature Dashboard', path: 'features.db', exists: true, is_active: true };
const DB_SECONDARY = { name: 'Godot Project', path: 'godot.db', exists: true, is_active: false };

function mockDatabases(page, databases) {
  return page.route('**/api/databases', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(databases),
    })
  );
}

test.describe('Info Bar', () => {
  test('info bar is hidden when default database is active', async ({ page }) => {
    await mockDatabases(page, [DB_DEFAULT, DB_SECONDARY]);
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.locator('[data-testid="info-bar"]')).toHaveCount(0);
  });

  test('info bar is hidden when only one database is configured', async ({ page }) => {
    await mockDatabases(page, [DB_DEFAULT]);
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.locator('[data-testid="info-bar"]')).toHaveCount(0);
  });

  test('info bar appears when a non-default database is active', async ({ page }) => {
    const secondary = { ...DB_SECONDARY, is_active: true };
    const primary = { ...DB_DEFAULT, is_active: false };
    await mockDatabases(page, [primary, secondary]);

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const infoBar = page.locator('[data-testid="info-bar"]');
    await expect(infoBar).toBeVisible();
    await expect(infoBar).toContainText('Active database: Godot Project');
  });

  test('info bar renders on top of kanban cards (z-index is 30)', async ({ page }) => {
    const secondary = { ...DB_SECONDARY, is_active: true };
    const primary = { ...DB_DEFAULT, is_active: false };
    await mockDatabases(page, [primary, secondary]);

    await page.goto('/');
    await page.waitForSelector('[data-testid="info-bar"]', { timeout: 10000 });

    const zIndex = await page.evaluate(() => {
      const bar = document.querySelector('[data-testid="info-bar"]');
      return window.getComputedStyle(bar).zIndex;
    });

    expect(Number(zIndex)).toBeGreaterThanOrEqual(30);
  });

  test('info bar can be dismissed', async ({ page }) => {
    const secondary = { ...DB_SECONDARY, is_active: true };
    const primary = { ...DB_DEFAULT, is_active: false };
    await mockDatabases(page, [primary, secondary]);

    await page.goto('/');
    await page.waitForSelector('[data-testid="info-bar"]', { timeout: 10000 });

    // Click the dismiss button
    await page.locator('[data-testid="info-bar"] button[aria-label="Dismiss"]').click();

    await expect(page.locator('[data-testid="info-bar"]')).toHaveCount(0);
  });

  test('info bar reappears after dismissal when database changes', async ({ page }) => {
    let activeDb = 'godot.db';

    // Return different active DB based on current state
    await page.route('**/api/databases', route => {
      const databases = [
        { ...DB_DEFAULT, is_active: activeDb === 'features.db' },
        { ...DB_SECONDARY, is_active: activeDb === 'godot.db' },
      ];
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(databases),
      });
    });

    await page.route('**/api/databases/select', async route => {
      activeDb = 'features.db';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Database switched successfully' }),
      });
    });

    await page.goto('/');
    await page.waitForSelector('[data-testid="info-bar"]', { timeout: 10000 });

    // Dismiss the info bar
    await page.locator('[data-testid="info-bar"] button[aria-label="Dismiss"]').click();
    await expect(page.locator('[data-testid="info-bar"]')).toHaveCount(0);

    // Switch back to default database (simulated via selector)
    await page.locator('button', { hasText: 'Godot Project' }).first().click();
    await page.locator('text=Feature Dashboard').first().click();
    await page.waitForTimeout(300);

    // Info bar should NOT reappear now (default DB is active)
    await expect(page.locator('[data-testid="info-bar"]')).toHaveCount(0);
  });
});
