import { test, expect } from '@playwright/test';

test.describe('Detail Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
  });

  test('should open detail panel when clicking a card', async ({ page }) => {
    // Click on first feature card
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.waitFor({ state: 'visible' });
    await firstCard.click();

    // Panel should appear
    await expect(page.getByTestId('detail-panel')).toBeVisible();
  });

  test('should show feature title, category, and description in panel', async ({ page }) => {
    // Click on first card (Test Feature with Description - id=1, Backend)
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.click();

    const panel = page.getByTestId('detail-panel');
    await expect(panel).toBeVisible();

    // Should show title section label
    await expect(panel.getByText('Title', { exact: true })).toBeVisible();
    await expect(panel.getByText('Category', { exact: true })).toBeVisible();
    await expect(panel.getByText('Description', { exact: true })).toBeVisible();
    await expect(panel.getByText('Steps', { exact: false })).toBeVisible();
  });

  test('should close panel when clicking X button', async ({ page }) => {
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();

    // Click X close button
    await page.getByTestId('detail-panel-close').click();

    await expect(page.getByTestId('detail-panel')).not.toBeVisible();
  });

  test('should close panel when pressing Escape', async ({ page }) => {
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();

    await page.keyboard.press('Escape');

    await expect(page.getByTestId('detail-panel')).not.toBeVisible();
  });

  test('should close panel when clicking backdrop', async ({ page }) => {
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();

    // Click the backdrop (left side of screen, away from panel)
    await page.getByTestId('detail-panel-backdrop').click({ position: { x: 10, y: 300 } });

    await expect(page.getByTestId('detail-panel')).not.toBeVisible();
  });

  test('should edit title via inline editing and persist on save', async ({ page }) => {
    // Create a test feature to edit
    const createResponse = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Panel Edit Test Feature',
        description: 'Test description for panel editing',
        steps: ['Step A', 'Step B']
      }
    });
    expect(createResponse.ok()).toBeTruthy();
    const created = await createResponse.json();

    // Reload to see the new feature
    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Find and click the test feature card
    const testCard = page.locator('.bg-surface.border.rounded-lg.p-4').filter({ hasText: 'Panel Edit Test Feature' });
    await testCard.waitFor({ state: 'visible' });
    await testCard.click();

    const panel = page.getByTestId('detail-panel');
    await expect(panel).toBeVisible();

    // Click on the title field to start editing
    const titleField = panel.locator('[title="Click to edit"]').first();
    await titleField.click();

    // Input should now be visible
    const titleInput = panel.locator('input').first();
    await titleInput.waitFor({ state: 'visible' });

    // Clear and type new title
    await titleInput.fill('Updated Panel Title');

    // Click save button
    await panel.locator('button[title="Save (Enter)"]').first().click();

    // Wait for update and check persistence via API
    await page.waitForTimeout(500);
    const getResponse = await page.request.get(`http://localhost:8001/api/features/${created.id}`);
    const updated = await getResponse.json();
    expect(updated.name).toBe('Updated Panel Title');

    // Clean up
    await page.request.delete(`http://localhost:8001/api/features/${created.id}`);
  });

  test('should cancel edit when pressing Escape', async ({ page }) => {
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.click();

    const panel = page.getByTestId('detail-panel');
    await expect(panel).toBeVisible();

    // Get all clickable edit fields
    const editFields = panel.locator('[title="Click to edit"]');
    await expect(editFields.first()).toBeVisible();
    const originalTitle = await editFields.first().innerText();

    // Start editing title
    await editFields.first().click();
    const titleInput = panel.locator('input').first();
    await titleInput.waitFor({ state: 'visible' });

    // Type something then escape
    await titleInput.fill('This should be cancelled');
    await titleInput.press('Escape');

    // The editing input should be gone (title input was the first [title="Click to edit"] field)
    // Wait for the editable div to come back
    await expect(panel.locator('[title="Click to edit"]').first()).toBeVisible();
    await expect(panel.locator('[title="Click to edit"]').first()).toHaveText(originalTitle);
  });

  test('should show delete confirmation prompt', async ({ page }) => {
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();

    // Click Delete button
    await page.getByTestId('delete-feature-btn').click();

    // Confirmation button should appear
    await expect(page.getByTestId('confirm-delete-btn')).toBeVisible();
  });

  test('should cancel delete when clicking Cancel', async ({ page }) => {
    const firstCard = page.locator('.bg-surface.border.rounded-lg.p-4').first();
    await firstCard.click();

    await page.getByTestId('delete-feature-btn').click();
    await expect(page.getByTestId('confirm-delete-btn')).toBeVisible();

    // Click cancel in the confirmation UI
    await page.getByRole('button', { name: 'Cancel' }).last().click();

    // The confirm button should be gone, delete button back
    await expect(page.getByTestId('delete-feature-btn')).toBeVisible();
    await expect(page.getByTestId('confirm-delete-btn')).not.toBeVisible();
  });

  test('should show Launch Claude button for TODO feature', async ({ page }) => {
    // Create a TODO feature (not passes, not in_progress)
    const createResponse = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Launch Claude TODO Test',
        description: 'Test feature for launch claude button',
        steps: ['Step 1']
      }
    });
    expect(createResponse.ok()).toBeTruthy();
    const created = await createResponse.json();

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const testCard = page.locator('.bg-surface.border.rounded-lg.p-4').filter({ hasText: 'Launch Claude TODO Test' });
    await testCard.waitFor({ state: 'visible' });
    await testCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();
    await expect(page.getByTestId('launch-claude-btn')).toBeVisible();

    // Clean up
    await page.request.delete(`http://localhost:8001/api/features/${created.id}`);
  });

  test('should show Launch Claude button for IN PROGRESS feature', async ({ page }) => {
    // Create an IN PROGRESS feature
    const createResponse = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Launch Claude InProgress Test',
        description: 'Test feature in progress for launch claude button',
        steps: ['Step 1'],
        in_progress: true
      }
    });
    expect(createResponse.ok()).toBeTruthy();
    const created = await createResponse.json();

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const testCard = page.locator('.bg-surface.border.rounded-lg.p-4').filter({ hasText: 'Launch Claude InProgress Test' });
    await testCard.waitFor({ state: 'visible' });
    await testCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();
    await expect(page.getByTestId('launch-claude-btn')).toBeVisible();

    // Clean up
    await page.request.delete(`http://localhost:8001/api/features/${created.id}`);
  });

  test('should NOT show Launch Claude button for DONE feature', async ({ page }) => {
    // Create a feature then mark it as passing
    const createResponse = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Launch Claude Done Test',
        description: 'Test feature done for launch claude button',
        steps: ['Step 1']
      }
    });
    expect(createResponse.ok()).toBeTruthy();
    const created = await createResponse.json();

    // Mark as passing via state endpoint
    const updateResponse = await page.request.patch(`http://localhost:8001/api/features/${created.id}/state`, {
      data: { passes: true }
    });
    expect(updateResponse.ok()).toBeTruthy();

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    const testCard = page.locator('.bg-surface.border.rounded-lg.p-4').filter({ hasText: 'Launch Claude Done Test' });
    await testCard.waitFor({ state: 'visible' });
    await testCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();
    await expect(page.getByTestId('launch-claude-btn')).not.toBeVisible();

    // Clean up
    await page.request.delete(`http://localhost:8001/api/features/${created.id}`);
  });

  test('should call launch-claude API and show success message', async ({ page }) => {
    // Create a TODO feature
    const createResponse = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Launch Claude API Call Test',
        description: 'Test feature for launch claude API call',
        steps: ['Step 1']
      }
    });
    expect(createResponse.ok()).toBeTruthy();
    const created = await createResponse.json();

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Intercept the launch-claude API call to avoid actually launching Claude
    await page.route(`**/api/features/${created.id}/launch-claude`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          launched: true,
          feature_id: created.id,
          prompt: 'Test prompt',
          working_directory: '/test'
        })
      });
    });

    const testCard = page.locator('.bg-surface.border.rounded-lg.p-4').filter({ hasText: 'Launch Claude API Call Test' });
    await testCard.waitFor({ state: 'visible' });
    await testCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();
    await page.getByTestId('launch-claude-btn').click();

    // Should show success message
    await expect(page.getByTestId('launch-claude-message')).toBeVisible();
    await expect(page.getByTestId('launch-claude-message')).toHaveText('Claude launched!');

    // Clean up
    await page.request.delete(`http://localhost:8001/api/features/${created.id}`);
  });

  test('should show error message when launch-claude API fails', async ({ page }) => {
    // Create a TODO feature
    const createResponse = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Launch Claude Error Test',
        description: 'Test feature for launch claude error',
        steps: ['Step 1']
      }
    });
    expect(createResponse.ok()).toBeTruthy();
    const created = await createResponse.json();

    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Intercept to simulate failure
    await page.route(`**/api/features/${created.id}/launch-claude`, async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Claude CLI not found' })
      });
    });

    const testCard = page.locator('.bg-surface.border.rounded-lg.p-4').filter({ hasText: 'Launch Claude Error Test' });
    await testCard.waitFor({ state: 'visible' });
    await testCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();
    await page.getByTestId('launch-claude-btn').click();

    // Should show error message
    await expect(page.getByTestId('launch-claude-message')).toBeVisible();
    await expect(page.getByTestId('launch-claude-message')).toHaveText('Claude CLI not found');

    // Clean up
    await page.request.delete(`http://localhost:8001/api/features/${created.id}`);
  });

  test('should delete feature and close panel', async ({ page }) => {
    // Create a disposable test feature
    const createResponse = await page.request.post('http://localhost:8001/api/features', {
      data: {
        category: 'Test',
        name: 'Feature To Delete',
        description: 'Will be deleted in test',
        steps: []
      }
    });
    expect(createResponse.ok()).toBeTruthy();
    const created = await createResponse.json();

    // Reload to see it
    await page.reload();
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    // Open the panel for this feature
    const testCard = page.locator('.bg-surface.border.rounded-lg.p-4').filter({ hasText: 'Feature To Delete' });
    await testCard.waitFor({ state: 'visible' });
    await testCard.click();

    await expect(page.getByTestId('detail-panel')).toBeVisible();

    // Delete it
    await page.getByTestId('delete-feature-btn').click();
    await page.getByTestId('confirm-delete-btn').click();

    // Panel should close
    await expect(page.getByTestId('detail-panel')).not.toBeVisible();

    // Feature should be gone from the board
    await expect(page.locator('.bg-surface.border.rounded-lg.p-4').filter({ hasText: 'Feature To Delete' })).not.toBeVisible();

    // Verify via API that it's gone
    const getResponse = await page.request.get(`http://localhost:8001/api/features/${created.id}`);
    expect(getResponse.status()).toBe(404);
  });
});
