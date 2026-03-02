import { test, expect } from '@playwright/test';

/**
 * AI Budget Badge Tests
 *
 * Verifies that the AiBudgetBadge component renders correctly in the header,
 * responds to API data, degrades silently on errors, and fits within the
 * mobile viewport without causing horizontal overflow.
 *
 * Two instances are rendered:
 *   ai-budget-badge-desktop  — shown only at md+ (hidden on mobile, in title row)
 *   ai-budget-badge-mobile   — shown only in the mobile second row (hidden on desktop)
 *
 * Both instances render the same content: full period labels (5h + week),
 * not a simplified dot indicator.
 */

// Shared mock for budget API with healthy utilization
const HEALTHY_BUDGET = {
  provider: 'anthropic',
  five_hour: { utilization: 45.0, resets_at: '2026-03-02T15:00:00', resets_formatted: '15:00' },
  seven_day: { utilization: 30.0, resets_at: '2026-03-07T13:00:00', resets_formatted: 'Sat 13:00' },
  error: null,
};

const WARNING_BUDGET = {
  provider: 'anthropic',
  five_hour: { utilization: 97.0, resets_at: '2026-03-02T15:00:00', resets_formatted: '15:00' },
  seven_day: { utilization: 30.0, resets_at: '2026-03-07T13:00:00', resets_formatted: 'Sat 13:00' },
  error: null,
};

const EXHAUSTED_BUDGET = {
  provider: 'anthropic',
  five_hour: { utilization: 100.0, resets_at: '2026-03-02T15:00:00', resets_formatted: '15:00' },
  seven_day: { utilization: 85.0, resets_at: '2026-03-07T13:00:00', resets_formatted: 'Sat 13:00' },
  error: null,
};

const ERROR_BUDGET = {
  provider: 'anthropic',
  five_hour: null,
  seven_day: null,
  error: 'Credentials not found',
};

async function setupPage(page, budgetResponse) {
  await page.route('**/api/autopilot/status', route => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        enabled: false, current_feature_id: null, current_feature_name: null,
        last_error: null, log: [],
      }),
    });
  });

  await page.route('**/api/budget', route => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(budgetResponse),
    });
  });

  await page.goto('/');
  await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
}

// ── Desktop layout ────────────────────────────────────────────────────────────

test.describe('AiBudgetBadge — Desktop (1280px)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await setupPage(page, HEALTHY_BUDGET);
  });

  test('desktop badge is visible in the header', async ({ page }) => {
    await expect(page.getByTestId('ai-budget-badge-desktop')).toBeVisible();
  });

  test('shows 5h percentage label', async ({ page }) => {
    const badge = page.getByTestId('ai-budget-badge-desktop');
    await expect(badge).toContainText('5h');
    await expect(badge).toContainText('45%');
  });

  test('shows week percentage label', async ({ page }) => {
    const badge = page.getByTestId('ai-budget-badge-desktop');
    await expect(badge).toContainText('week');
    await expect(badge).toContainText('30%');
  });

  test('mobile badge row is hidden on desktop', async ({ page }) => {
    await expect(page.getByTestId('ai-budget-badge-mobile')).toBeHidden();
  });
});

// ── Mobile layout ─────────────────────────────────────────────────────────────

test.describe('AiBudgetBadge — Mobile (375px)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await setupPage(page, HEALTHY_BUDGET);
  });

  test('mobile badge is visible at 375px (in mobile row)', async ({ page }) => {
    await expect(page.getByTestId('ai-budget-badge-mobile')).toBeVisible();
  });

  test('mobile badge shows 5h percentage label (same as desktop)', async ({ page }) => {
    const badge = page.getByTestId('ai-budget-badge-mobile');
    await expect(badge).toContainText('5h');
    await expect(badge).toContainText('45%');
  });

  test('mobile badge shows week percentage label (same as desktop)', async ({ page }) => {
    const badge = page.getByTestId('ai-budget-badge-mobile');
    await expect(badge).toContainText('week');
    await expect(badge).toContainText('30%');
  });

  test('desktop badge is hidden on mobile', async ({ page }) => {
    await expect(page.getByTestId('ai-budget-badge-desktop')).toBeHidden();
  });

  test('no horizontal overflow at 375px caused by badge', async ({ page }) => {
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(375);
  });
});

// ── Color states ──────────────────────────────────────────────────────────────

test.describe('AiBudgetBadge — Color states', () => {
  test('shows green for healthy utilization', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await setupPage(page, HEALTHY_BUDGET);

    const badge = page.getByTestId('ai-budget-badge-desktop');
    await expect(badge).toBeVisible();
    const pctSpan = badge.locator('span.tabular-nums').first();
    const color = await pctSpan.evaluate(el => el.style.color);
    expect(color).toBe('rgb(34, 197, 94)');   // #22c55e
  });

  test('shows red for utilization >= 95', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await setupPage(page, WARNING_BUDGET);

    const badge = page.getByTestId('ai-budget-badge-desktop');
    await expect(badge).toBeVisible();
    const pctSpan = badge.locator('span.tabular-nums').first();
    const color = await pctSpan.evaluate(el => el.style.color);
    expect(color).toBe('rgb(239, 68, 68)');   // #ef4444
  });

  test('shows "resets HH:MM" when 5h is exhausted', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await setupPage(page, EXHAUSTED_BUDGET);

    const badge = page.getByTestId('ai-budget-badge-desktop');
    await expect(badge).toBeVisible();
    await expect(badge).toContainText('resets');
    await expect(badge).toContainText('15:00');
  });
});

// ── Error / no-data degradation ───────────────────────────────────────────────

test.describe('AiBudgetBadge — Error degradation', () => {
  test('desktop badge is absent when API returns error', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await setupPage(page, ERROR_BUDGET);

    await expect(page.getByTestId('ai-budget-badge-desktop')).not.toBeVisible();
  });

  test('mobile badge is absent when API returns error', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await setupPage(page, ERROR_BUDGET);

    await expect(page.getByTestId('ai-budget-badge-mobile')).not.toBeVisible();
  });

  test('badge is absent when API call fails entirely', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });

    await page.route('**/api/autopilot/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: false, current_feature_id: null, last_error: null, log: [] }),
      });
    });
    await page.route('**/api/budget', route => {
      route.fulfill({ status: 500, body: 'Internal Server Error' });
    });

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });

    await expect(page.getByTestId('ai-budget-badge-desktop')).not.toBeVisible();
  });

  test('no horizontal overflow at 375px even when badge absent', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await setupPage(page, ERROR_BUDGET);

    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(375);
  });
});

// ── Existing header controls still work ───────────────────────────────────────

test.describe('AiBudgetBadge — No regression on existing header controls', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await setupPage(page, HEALTHY_BUDGET);
  });

  test('settings button still visible and within viewport', async ({ page }) => {
    const btn = page.getByTestId('settings-btn');
    await expect(btn).toBeVisible();
    const box = await btn.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x + box.width).toBeLessThanOrEqual(375);
  });

  test('plan-tasks button still within viewport', async ({ page }) => {
    const btn = page.getByTestId('plan-tasks-btn');
    await expect(btn).toBeVisible();
    const box = await btn.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x + box.width).toBeLessThanOrEqual(375);
  });

  test('autopilot toggle still within viewport', async ({ page }) => {
    const toggle = page.getByTestId('autopilot-toggle');
    await expect(toggle).toBeVisible();
    const box = await toggle.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x + box.width).toBeLessThanOrEqual(375);
  });
});
