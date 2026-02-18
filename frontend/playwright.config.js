import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E Test Configuration
 *
 * BROWSER SUPPORT: Chromium only
 * We only test on Chromium as it's the primary target browser.
 * No need for cross-browser testing (Firefox, Safari, WebKit).
 */
export default defineConfig({
  testDir: './tests',

  // Run tests in parallel
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Opt out of parallel tests on CI
  workers: process.env.CI ? 1 : undefined,

  // Reporter to use
  reporter: 'html',

  // Shared settings for all the projects below
  use: {
    // Base URL to use in actions like `await page.goto('/')`
    baseURL: 'http://localhost:5174',

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Disable CSS animations so drag-and-drop tests aren't affected by
    // elements animating into position during test execution
    reducedMotion: 'reduce',
  },

  // Configure projects for Chromium only
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Run dev server and backend before starting the tests
  webServer: [
    {
      // Start frontend on port 5174 with test-specific config (proxies to port 8001)
      command: 'npx vite --config vite.config.test.js',
      url: 'http://localhost:5174',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
    {
      // Run backend with test database on port 8001 (separate from DevServer on port 8000)
      // This allows tests to run even when DevServer is running for development
      command: 'node tests/start-test-backend.js',
      url: 'http://localhost:8001/api/features',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    }
  ],
});
