import { test, expect } from '@playwright/test';

/**
 * E2E tests for lane scrolling behavior.
 * Verifies that when a lane has more features than fit on screen,
 * the lane scrolls internally rather than growing the page.
 */

const API = 'http://localhost:8001';

async function createFeature(request, overrides = {}) {
  const res = await request.post(`${API}/api/features`, {
    data: {
      category: 'Test',
      name: 'Scroll Test Feature',
      description: 'Created for scrolling test',
      steps: ['Step 1'],
      ...overrides
    }
  });
  expect(res.ok()).toBeTruthy();
  return res.json();
}

async function deleteFeature(request, id) {
  await request.delete(`${API}/api/features/${id}`);
}

test.describe('Lane scrolling', () => {
  const createdIds = [];

  test.afterEach(async ({ request }) => {
    for (const id of createdIds) {
      await deleteFeature(request, id);
    }
    createdIds.length = 0;
  });

  test('page does not scroll when features overflow a lane', async ({ page, request }) => {
    // Create enough features to overflow the TODO lane
    for (let i = 0; i < 15; i++) {
      const f = await createFeature(request, { name: `Scroll Test Feature ${i + 1}` });
      createdIds.push(f.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(300);

    const { documentHeight, viewportHeight } = await page.evaluate(() => ({
      documentHeight: document.documentElement.scrollHeight,
      viewportHeight: window.innerHeight,
    }));

    // The page itself must not be taller than the viewport
    expect(documentHeight).toBeLessThanOrEqual(viewportHeight);
  });

  test('todo lane content area is scrollable when overflowing', async ({ page, request }) => {
    // Create enough features to overflow the TODO lane
    for (let i = 0; i < 15; i++) {
      const f = await createFeature(request, { name: `Scroll Test Feature ${i + 1}` });
      createdIds.push(f.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(300);

    const scrollInfo = await page.evaluate(() => {
      // The first lane's scrollable content div
      const lanes = document.querySelectorAll('.grid > div');
      const todoLane = lanes[0];
      const scrollable = todoLane?.querySelector('.overflow-y-auto');
      if (!scrollable) return null;

      return {
        scrollHeight: scrollable.scrollHeight,
        clientHeight: scrollable.clientHeight,
        overflowY: window.getComputedStyle(scrollable).overflowY,
      };
    });

    expect(scrollInfo).not.toBeNull();
    // The scrollable area should have overflow content
    expect(scrollInfo.scrollHeight).toBeGreaterThan(scrollInfo.clientHeight);
    // And it must be set to auto (scrollable)
    expect(scrollInfo.overflowY).toBe('auto');
  });

  test('each lane is constrained to the viewport height', async ({ page, request }) => {
    // Create features to fill the TODO lane
    for (let i = 0; i < 10; i++) {
      const f = await createFeature(request, { name: `Lane Height Test ${i + 1}` });
      createdIds.push(f.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(300);

    const { laneHeight, viewportHeight } = await page.evaluate(() => {
      const lanes = document.querySelectorAll('.grid > div');
      const todoLane = lanes[0];
      return {
        laneHeight: todoLane?.getBoundingClientRect().height ?? 0,
        viewportHeight: window.innerHeight,
      };
    });

    // The lane must fit within the viewport
    expect(laneHeight).toBeLessThanOrEqual(viewportHeight);
  });

  test('user can scroll within the todo lane', async ({ page, request }) => {
    // Create enough features to require scrolling
    for (let i = 0; i < 15; i++) {
      const f = await createFeature(request, { name: `Scroll Nav Feature ${i + 1}` });
      createdIds.push(f.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(300);

    // Scroll down in the TODO lane
    await page.evaluate(() => {
      const lanes = document.querySelectorAll('.grid > div');
      const todoLane = lanes[0];
      const scrollable = todoLane?.querySelector('.overflow-y-auto');
      if (scrollable) scrollable.scrollTop = 500;
    });

    const scrollTop = await page.evaluate(() => {
      const lanes = document.querySelectorAll('.grid > div');
      const todoLane = lanes[0];
      const scrollable = todoLane?.querySelector('.overflow-y-auto');
      return scrollable?.scrollTop ?? 0;
    });

    // The lane should have scrolled
    expect(scrollTop).toBeGreaterThan(0);
  });
});
