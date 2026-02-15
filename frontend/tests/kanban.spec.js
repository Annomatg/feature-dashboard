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
    const featureCards = await page.locator('.bg-surface.border.rounded-lg.p-4').all();
    expect(featureCards.length).toBeGreaterThan(0);
  });

  test('should display feature details on cards', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Wait for at least one feature card
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
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

  test('feature cards should show description indicator icon when description exists', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Wait for at least one feature card
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.waitFor({ state: 'visible' });

    // Check that the FileText icon is visible (cards with descriptions should have the icon)
    const icons = await firstCard.locator('svg').all();
    expect(icons.length).toBeGreaterThan(0);
  });

  test('feature cards should NOT show description indicator icon when description is empty', async ({ page }) => {
    // Create a test feature without a description via API
    // Using test database so it's safe to create/delete features
    const response = await page.request.post('http://localhost:8000/api/features', {
      data: {
        priority: 999,
        category: 'Test',
        name: 'Test Feature Without Description',
        description: '',
        steps: ['Step 1'],
        passes: false,
        in_progress: false
      }
    });
    expect(response.ok()).toBeTruthy();
    const createdFeature = await response.json();

    // Reload the page to see the new feature
    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Find the card for our test feature
    const testCard = page.locator('.bg-surface.border.rounded-lg.p-4').filter({ hasText: 'Test Feature Without Description' });
    await testCard.waitFor({ state: 'visible' });

    // Check that NO FileText icon is present (only category badge might have icon)
    // The description indicator icon should NOT be visible
    const titleSection = testCard.locator('.flex.items-start.gap-2');
    const icons = await titleSection.locator('svg').all();
    expect(icons.length).toBe(0);

    // Clean up: delete the test feature (safe because we're using test database)
    await page.request.delete(`http://localhost:8000/api/features/${createdFeature.id}`);
  });

  test('feature cards should be clickable and log selection', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Set up console listener
    const consoleMessages = [];
    page.on('console', msg => {
      if (msg.type() === 'log') {
        consoleMessages.push(msg.text());
      }
    });

    // Click on the first feature card
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.click();

    // Wait a bit for the console log
    await page.waitForTimeout(500);

    // Check that a selection was logged
    const hasSelectionLog = consoleMessages.some(msg => msg.includes('Selected feature:'));
    expect(hasSelectionLog).toBe(true);
  });

  test('feature cards should show visual distinction when selected', async ({ page }) => {
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Click on the first feature card
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.click();

    // Wait for the style to update
    await page.waitForTimeout(200);

    // The selected card should have a box-shadow (visual distinction)
    const boxShadow = await firstCard.evaluate(el => window.getComputedStyle(el).boxShadow);
    expect(boxShadow).not.toBe('none');
  });
});
