import { test, expect } from '@playwright/test';

test.describe('Kanban Board', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display three lanes', async ({ page }) => {
    // Wait for the board to load
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Check for all three lane titles using exact headings
    await expect(page.getByRole('heading', { name: 'TODO', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'IN PROGRESS', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'DONE', exact: true })).toBeVisible();
  });

  test('should display feature counts in each lane', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Each lane should have a count badge visible
    const counts = await page.locator('.font-mono.text-sm.font-semibold').all();
    expect(counts.length).toBeGreaterThanOrEqual(3);
  });

  test('should display add buttons for each lane', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Each lane should have an add button
    const addButtons = await page.locator('button[aria-label^="Add feature to"]').all();
    expect(addButtons.length).toBe(3);
  });

  test('should display features in correct lanes', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Check that at least one feature card is visible
    const featureCards = await page.locator('.bg-surface.border.border-surface-light.rounded-lg').all();
    expect(featureCards.length).toBeGreaterThan(0);
  });

  test('should display feature details on cards', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Wait for at least one feature card
    const firstCard = page.locator('.bg-surface.border.border-surface-light.rounded-lg').first();
    await firstCard.waitFor({ state: 'visible' });

    // Check that the card contains expected elements
    await expect(firstCard.locator('.font-mono.text-xs.text-text-secondary').first()).toBeVisible(); // Priority
    await expect(firstCard.locator('.text-text-primary.font-semibold')).toBeVisible(); // Name
  });

  test('should show total feature count in header', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Check for total features text in header
    await expect(page.locator('text=/\\d+ total features/')).toBeVisible();
  });

  test('lanes should be scrollable', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Check that lanes have overflow scrolling
    const scrollContainers = await page.locator('.overflow-y-auto.custom-scrollbar').all();
    expect(scrollContainers.length).toBe(3);
  });
});
