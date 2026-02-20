import { test, expect } from '@playwright/test';

test.describe('Settings Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
  });

  test('should show settings button in header', async ({ page }) => {
    await expect(page.getByTestId('settings-btn')).toBeVisible();
  });

  test('should open settings panel when clicking settings button', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible();
  });

  test('should close settings panel when clicking X button', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible();

    await page.getByTestId('settings-panel-close').click();
    await expect(page.getByTestId('settings-panel')).not.toBeVisible();
  });

  test('should close settings panel when pressing Escape', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(page.getByTestId('settings-panel')).not.toBeVisible();
  });

  test('should close settings panel when clicking backdrop', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible();

    await page.getByTestId('settings-panel-backdrop').click({ position: { x: 10, y: 300 } });
    await expect(page.getByTestId('settings-panel')).not.toBeVisible();
  });

  test('should show prompt template textarea in settings panel', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible();

    await expect(page.getByTestId('prompt-template-input')).toBeVisible();
  });

  test('should load current prompt template from API', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible();

    const textarea = page.getByTestId('prompt-template-input');
    await expect(textarea).toBeVisible();
    // Should have some non-empty content
    const value = await textarea.inputValue();
    expect(value.length).toBeGreaterThan(0);
  });

  test('should save prompt template and persist via API', async ({ page }) => {
    // Get the current template first so we can restore it
    const getResponse = await page.request.get('http://localhost:8001/api/settings');
    expect(getResponse.ok()).toBeTruthy();
    const originalSettings = await getResponse.json();

    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible();

    const textarea = page.getByTestId('prompt-template-input');
    await textarea.waitFor({ state: 'visible' });

    // Change the template
    const newTemplate = 'Test template: {name} - {description} - {steps}';
    await textarea.fill(newTemplate);

    // Save button should be enabled now
    const saveBtn = page.getByTestId('settings-save-btn');
    await expect(saveBtn).not.toBeDisabled();
    await saveBtn.click();

    // Should show success message
    await expect(page.getByTestId('settings-save-message')).toBeVisible();
    await expect(page.getByTestId('settings-save-message')).toHaveText('Settings saved!');

    // Verify it was saved via API
    const verifyResponse = await page.request.get('http://localhost:8001/api/settings');
    const saved = await verifyResponse.json();
    expect(saved.claude_prompt_template).toBe(newTemplate);

    // Restore original settings
    await page.request.put('http://localhost:8001/api/settings', {
      data: { claude_prompt_template: originalSettings.claude_prompt_template }
    });
  });

  test('should have save button disabled when no changes made', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible();

    // Wait for loading to complete
    await page.getByTestId('prompt-template-input').waitFor({ state: 'visible' });

    const saveBtn = page.getByTestId('settings-save-btn');
    await expect(saveBtn).toBeDisabled();
  });

  test('should reset to default template when clicking reset button', async ({ page }) => {
    await page.getByTestId('settings-btn').click();
    await expect(page.getByTestId('settings-panel')).toBeVisible();

    const textarea = page.getByTestId('prompt-template-input');
    await textarea.waitFor({ state: 'visible' });

    // Change the template to something custom
    await textarea.fill('Custom template that is not the default');

    // Click reset
    await page.getByTestId('settings-reset-btn').click();

    // Should be back to default (contains 'feature_id' placeholder)
    const value = await textarea.inputValue();
    expect(value).toContain('{feature_id}');
    expect(value).toContain('{name}');
    expect(value).toContain('{description}');
  });
});
