import { test, expect } from '@playwright/test';

test.describe('Recent log in task card (Feature #148)', () => {
  test('card without comments shows no recent-log element', async ({ page }) => {
    // Create a feature with no comments
    const featureRes = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Card No Log Test',
        description: 'No comments here',
        steps: [],
      }
    });
    expect(featureRes.ok()).toBeTruthy();
    const feature = await featureRes.json();

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator(`[data-testid="kanban-card"][data-feature-id="${feature.id}"]`);
    await card.waitFor({ state: 'visible' });

    // No recent-log element should be present
    await expect(card.locator('[data-testid="recent-log"]')).not.toBeVisible();

    // Cleanup
    await page.request.delete(`http://localhost:8001/api/features/${feature.id}`);
  });

  test('card with a comment shows the most recent log entry', async ({ page }) => {
    // Create a feature
    const featureRes = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Card With Log Test',
        description: 'Has a comment',
        steps: [],
      }
    });
    expect(featureRes.ok()).toBeTruthy();
    const feature = await featureRes.json();

    // Add a comment
    const commentRes = await page.request.post(
      `http://localhost:8001/api/features/${feature.id}/comments`,
      { data: { content: 'Fixed the regression in module X' } }
    );
    expect(commentRes.ok()).toBeTruthy();

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator(`[data-testid="kanban-card"][data-feature-id="${feature.id}"]`);
    await card.waitFor({ state: 'visible' });

    const recentLog = card.locator('[data-testid="recent-log"]');
    await expect(recentLog).toBeVisible();
    await expect(recentLog).toContainText('Fixed the regression in module X');

    // Cleanup
    await page.request.delete(`http://localhost:8001/api/features/${feature.id}`);
  });

  test('card shows the latest comment when multiple exist', async ({ page }) => {
    const featureRes = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Card Multi Comment Log Test',
        description: 'Multiple comments',
        steps: [],
      }
    });
    expect(featureRes.ok()).toBeTruthy();
    const feature = await featureRes.json();

    // Add two comments — only the second should appear
    await page.request.post(
      `http://localhost:8001/api/features/${feature.id}/comments`,
      { data: { content: 'Older entry not visible' } }
    );
    await page.request.post(
      `http://localhost:8001/api/features/${feature.id}/comments`,
      { data: { content: 'Newest entry visible' } }
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator(`[data-testid="kanban-card"][data-feature-id="${feature.id}"]`);
    await card.waitFor({ state: 'visible' });

    const recentLog = card.locator('[data-testid="recent-log"]');
    await expect(recentLog).toBeVisible();
    await expect(recentLog).toContainText('Newest entry visible');
    // Older entry should NOT be shown in the card
    await expect(recentLog).not.toContainText('Older entry not visible');

    // Cleanup
    await page.request.delete(`http://localhost:8001/api/features/${feature.id}`);
  });

  test('recent log is positioned left of steps count', async ({ page }) => {
    const featureRes = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Card Log Position Test',
        description: 'Check layout',
        steps: ['Step 1', 'Step 2'],
      }
    });
    expect(featureRes.ok()).toBeTruthy();
    const feature = await featureRes.json();

    await page.request.post(
      `http://localhost:8001/api/features/${feature.id}/comments`,
      { data: { content: 'Some progress made' } }
    );

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const card = page.locator(`[data-testid="kanban-card"][data-feature-id="${feature.id}"]`);
    await card.waitFor({ state: 'visible' });

    const recentLog = card.locator('[data-testid="recent-log"]');
    const stepsText = card.locator('text=2 steps');

    await expect(recentLog).toBeVisible();
    await expect(stepsText).toBeVisible();

    // recent-log should be to the left (smaller x) of the steps count
    const logBox = await recentLog.boundingBox();
    const stepsBox = await stepsText.boundingBox();
    expect(logBox.x).toBeLessThan(stepsBox.x);

    // Cleanup
    await page.request.delete(`http://localhost:8001/api/features/${feature.id}`);
  });
});
