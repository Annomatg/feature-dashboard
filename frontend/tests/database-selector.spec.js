import { test, expect } from '@playwright/test';

/**
 * E2E tests for the DatabaseSelector component.
 *
 * Uses page.route() to mock /api/databases responses, since switching
 * databases requires a second configured database file which may not
 * exist in all test environments.
 */

const MOCK_DATABASES = [
  { name: 'Feature Dashboard', path: 'features.db', exists: true, is_active: true },
  { name: 'Godot Project', path: 'godot.db', exists: true, is_active: false },
];

test.describe('Database Selector', () => {
  test('selector is hidden when only one database is configured', async ({ page }) => {
    // Mock a single-database response
    await page.route('**/api/databases', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([MOCK_DATABASES[0]]),
      })
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Dropdown button should NOT be visible with only one DB
    const selector = page.locator('button', { hasText: 'Feature Dashboard' }).filter({
      has: page.locator('svg') // has icon
    });
    await expect(selector).toHaveCount(0);
  });

  test('selector is visible when multiple databases are configured', async ({ page }) => {
    await page.route('**/api/databases', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DATABASES),
      })
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Selector button should appear with the active DB name
    await expect(page.locator('button', { hasText: 'Feature Dashboard' }).first()).toBeVisible();
  });

  test('clicking selector opens dropdown with all databases', async ({ page }) => {
    await page.route('**/api/databases', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DATABASES),
      })
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Wait for selector to appear, then click
    const selectorBtn = page.locator('button', { hasText: 'Feature Dashboard' }).first();
    await selectorBtn.waitFor({ state: 'visible' });
    await selectorBtn.click();

    // Both databases should be listed in the dropdown
    await expect(page.locator('text=Feature Dashboard').first()).toBeVisible();
    await expect(page.locator('text=Godot Project')).toBeVisible();
  });

  test('active database is visually marked in the dropdown', async ({ page }) => {
    await page.route('**/api/databases', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DATABASES),
      })
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const selectorBtn = page.locator('button', { hasText: 'Feature Dashboard' }).first();
    await selectorBtn.waitFor({ state: 'visible' });
    await selectorBtn.click();

    // "active" label should be present next to the active database
    await expect(page.locator('text=active')).toBeVisible();
  });

  test('selecting a different database calls POST /api/databases/select and invalidates queries', async ({ page }) => {
    let selectCalled = false;
    let featuresRefetched = false;

    await page.route('**/api/databases', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DATABASES),
      })
    );

    await page.route('**/api/databases/select', async route => {
      selectCalled = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Database switched successfully', active_database: 'godot.db' }),
      });
    });

    // Track if features endpoint gets called again after switching
    await page.route('**/api/features**', async route => {
      featuresRefetched = true;
      await route.continue();
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const selectorBtn = page.locator('button', { hasText: 'Feature Dashboard' }).first();
    await selectorBtn.waitFor({ state: 'visible' });

    // Reset the tracking flag after initial load
    featuresRefetched = false;

    await selectorBtn.click();

    // Click on the non-active database
    await page.locator('text=Godot Project').click();

    // Wait a moment for async operations to complete
    await page.waitForTimeout(500);

    expect(selectCalled).toBe(true);
    expect(featuresRefetched).toBe(true);
  });

  test('loading spinner appears while switching databases', async ({ page }) => {
    await page.route('**/api/databases', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DATABASES),
      })
    );

    // Delay the select response so we can see the loading state
    await page.route('**/api/databases/select', async route => {
      await new Promise(resolve => setTimeout(resolve, 400));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Database switched successfully', active_database: 'godot.db' }),
      });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const selectorBtn = page.locator('button', { hasText: 'Feature Dashboard' }).first();
    await selectorBtn.waitFor({ state: 'visible' });
    await selectorBtn.click();
    await page.locator('text=Godot Project').click();

    // While switching, button should show "Switching..." text
    await expect(page.locator('button', { hasText: 'Switching...' })).toBeVisible();

    // After switch completes, "Switching..." text should disappear
    await expect(page.locator('button', { hasText: 'Switching...' })).not.toBeVisible({ timeout: 2000 });
  });

  test('clicking outside dropdown closes it', async ({ page }) => {
    await page.route('**/api/databases', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DATABASES),
      })
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const selectorBtn = page.locator('button', { hasText: 'Feature Dashboard' }).first();
    await selectorBtn.waitFor({ state: 'visible' });
    await selectorBtn.click();

    // Dropdown content visible
    await expect(page.locator('text=Godot Project')).toBeVisible();

    // Click somewhere outside
    await page.locator('h1').click();

    // Dropdown should be closed
    await expect(page.locator('text=Godot Project')).not.toBeVisible();
  });
});
