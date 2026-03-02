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

  // Helper: get scrollTop of the TODO lane's scrollable container
  async function getTodoScrollTop(page) {
    return page.evaluate(() => {
      const todoLane = document.querySelectorAll('.grid > div')[0];
      return todoLane?.querySelector('[data-scroll]')?.scrollTop ?? 0;
    });
  }

  // Helper: set scrollTop of the TODO lane's scrollable container
  async function setTodoScrollTop(page, value) {
    await page.evaluate((v) => {
      const todoLane = document.querySelectorAll('.grid > div')[0];
      const el = todoLane?.querySelector('[data-scroll]');
      if (el) el.scrollTop = v;
    }, value);
  }

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

test.describe('Drag auto-scroll', () => {
  /**
   * Tests for the drag-scroll feature: when a card is dragged near the top or
   * bottom of a lane's scroll container (or over the lane header), the container
   * auto-scrolls in the appropriate direction.
   */

  const createdIds = [];

  test.afterEach(async ({ request }) => {
    for (const id of createdIds) {
      await deleteFeature(request, id);
    }
    createdIds.length = 0;
  });

  async function getTodoScrollTop(page) {
    return page.evaluate(() => {
      const todoLane = document.querySelectorAll('.grid > div')[0];
      return todoLane?.querySelector('[data-scroll]')?.scrollTop ?? 0;
    });
  }

  async function setTodoScrollToBottom(page) {
    await page.evaluate(() => {
      const todoLane = document.querySelectorAll('.grid > div')[0];
      const el = todoLane?.querySelector('[data-scroll]');
      if (el) el.scrollTop = el.scrollHeight;
    });
    await page.waitForTimeout(50);
  }

  // Dispatch dragover on the TODO lane at a specific clientY value
  async function dispatchDragOver(page, clientY) {
    await page.evaluate((y) => {
      const todoLane = document.querySelectorAll('.animate-slide-in')[0];
      const scrollable = todoLane?.querySelector('[data-scroll]');
      if (!todoLane || !scrollable) return;
      const dt = new DataTransfer();
      todoLane.dispatchEvent(new DragEvent('dragover', {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientY: y,
      }));
    }, clientY);
  }

  test('dragging near bottom of scroll container scrolls down', async ({ page, request }) => {
    for (let i = 0; i < 20; i++) {
      const f = await createFeature(request, { name: `DragScroll Down ${i + 1}` });
      createdIds.push(f.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(300);

    // Confirm lane is scrollable and starts at top
    const isScrollable = await page.evaluate(() => {
      const el = document.querySelectorAll('.grid > div')[0]?.querySelector('[data-scroll]');
      return el ? el.scrollHeight > el.clientHeight : false;
    });
    expect(isScrollable).toBe(true);
    expect(await getTodoScrollTop(page)).toBe(0);

    // Get the bottom position of the scroll container and fire dragover 30px from edge
    const clientY = await page.evaluate(() => {
      const el = document.querySelectorAll('.grid > div')[0]?.querySelector('[data-scroll]');
      return el ? el.getBoundingClientRect().bottom - 30 : 0;
    });

    await dispatchDragOver(page, clientY);
    // Allow RAF loop to run for a few frames
    await page.waitForTimeout(200);

    expect(await getTodoScrollTop(page)).toBeGreaterThan(0);
  });

  test('dragging near top of scroll container scrolls up', async ({ page, request }) => {
    for (let i = 0; i < 20; i++) {
      const f = await createFeature(request, { name: `DragScroll Up ${i + 1}` });
      createdIds.push(f.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(300);

    await setTodoScrollToBottom(page);
    const initialTop = await getTodoScrollTop(page);
    expect(initialTop).toBeGreaterThan(0);

    // Fire dragover 30px below the top edge of the scroll container
    const clientY = await page.evaluate(() => {
      const el = document.querySelectorAll('.grid > div')[0]?.querySelector('[data-scroll]');
      return el ? el.getBoundingClientRect().top + 30 : 0;
    });

    await dispatchDragOver(page, clientY);
    await page.waitForTimeout(200);

    expect(await getTodoScrollTop(page)).toBeLessThan(initialTop);
  });

  test('dragging over lane header (above scroll container) scrolls up at max speed', async ({ page, request }) => {
    for (let i = 0; i < 20; i++) {
      const f = await createFeature(request, { name: `DragScroll Header ${i + 1}` });
      createdIds.push(f.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(300);

    await setTodoScrollToBottom(page);
    const initialTop = await getTodoScrollTop(page);
    expect(initialTop).toBeGreaterThan(0);

    // Fire dragover ABOVE the scroll container (in the header area)
    const clientY = await page.evaluate(() => {
      const el = document.querySelectorAll('.grid > div')[0]?.querySelector('[data-scroll]');
      return el ? el.getBoundingClientRect().top - 10 : 0;
    });

    await dispatchDragOver(page, clientY);
    await page.waitForTimeout(200);

    expect(await getTodoScrollTop(page)).toBeLessThan(initialTop);
  });

  test('scrolling stops when drop occurs', async ({ page, request }) => {
    for (let i = 0; i < 20; i++) {
      const f = await createFeature(request, { name: `DragScroll Stop ${i + 1}` });
      createdIds.push(f.id);
    }

    await page.goto('/');
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 });
    await page.waitForTimeout(300);

    // Start auto-scroll downward
    const clientY = await page.evaluate(() => {
      const el = document.querySelectorAll('.grid > div')[0]?.querySelector('[data-scroll]');
      return el ? el.getBoundingClientRect().bottom - 30 : 0;
    });

    await dispatchDragOver(page, clientY);
    await page.waitForTimeout(150);

    const scrollTopAfterDrag = await getTodoScrollTop(page);
    expect(scrollTopAfterDrag).toBeGreaterThan(0);

    // Fire drop on the lane to stop auto-scroll
    await page.evaluate(() => {
      const todoLane = document.querySelectorAll('.animate-slide-in')[0];
      if (!todoLane) return;
      const dt = new DataTransfer();
      todoLane.dispatchEvent(new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
      }));
    });

    // Record position right after drop
    const posAfterDrop = await getTodoScrollTop(page);
    // Wait and confirm it no longer changes
    await page.waitForTimeout(200);
    const posAfterWait = await getTodoScrollTop(page);

    expect(posAfterWait).toBe(posAfterDrop);
  });
});
