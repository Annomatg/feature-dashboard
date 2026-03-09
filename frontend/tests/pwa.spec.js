import { test, expect } from '@playwright/test';

async function fetchManifest(page) {
  const manifestLink = page.locator('link[rel="manifest"]');
  const href = await manifestLink.getAttribute('href');
  const response = await page.request.get(href);
  expect(response.ok()).toBe(true);
  return response.json();
}

test.describe('PWA Setup', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
  });

  test('manifest link is present in head', async ({ page }) => {
    const manifestLink = page.locator('link[rel="manifest"]');
    await expect(manifestLink).toHaveCount(1);
    const href = await manifestLink.getAttribute('href');
    expect(href).toBeTruthy();
  });

  test('manifest is accessible and has correct fields', async ({ page }) => {
    const manifest = await fetchManifest(page);
    expect(manifest.name).toBe('Feature Dashboard');
    expect(manifest.short_name).toBe('Dashboard');
    expect(manifest.display).toBe('standalone');
    expect(manifest.theme_color).toBe('#1e293b');
    expect(manifest.icons).toBeDefined();
    expect(manifest.icons.length).toBeGreaterThan(0);
  });

  test('manifest icons include 192x192 and 512x512 sizes', async ({ page }) => {
    const manifest = await fetchManifest(page);
    const sizes = manifest.icons.map(i => i.sizes);
    expect(sizes).toContain('192x192');
    expect(sizes).toContain('512x512');
  });

  test('manifest has maskable icon', async ({ page }) => {
    const manifest = await fetchManifest(page);
    const maskable = manifest.icons.find(i => i.purpose === 'maskable');
    expect(maskable).toBeDefined();
  });

  test('theme-color meta tag is present', async ({ page }) => {
    const themeColor = page.locator('meta[name="theme-color"]');
    await expect(themeColor).toHaveCount(1);
    const content = await themeColor.getAttribute('content');
    expect(content).toBe('#1e293b');
  });

  test('apple-touch-icon link is present', async ({ page }) => {
    const appleIcon = page.locator('link[rel="apple-touch-icon"]');
    await expect(appleIcon).toHaveCount(1);
    const href = await appleIcon.getAttribute('href');
    expect(href).toBeTruthy();
  });

  test('apple-mobile-web-app-capable meta tag is present', async ({ page }) => {
    const appCapable = page.locator('meta[name="apple-mobile-web-app-capable"]');
    await expect(appCapable).toHaveCount(1);
    const content = await appCapable.getAttribute('content');
    expect(content).toBe('yes');
  });

  test('PWA icon files are accessible', async ({ page }) => {
    const iconUrls = [
      '/pwa-192x192.png',
      '/pwa-512x512.png',
      '/apple-touch-icon-180x180.png',
      '/favicon.ico',
    ];

    for (const url of iconUrls) {
      const response = await page.request.get(url);
      expect(response.ok(), `Icon ${url} should be accessible`).toBe(true);
    }
  });
});
