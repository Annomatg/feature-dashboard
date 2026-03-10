import { test, expect } from '@playwright/test'

const API = 'http://localhost:8001'

test.describe('Graph View', () => {
  test('graph container is visible on /tasks/{id}/graph with mocked data', async ({ page }) => {
    // Mock the graph API to return test data (test DB has no real session files)
    await page.route('**/api/tasks/1/graph', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          nodes: [
            { id: 'main', label: 'Main Agent', type: 'main' },
            { id: 'agent_1', label: 'Explore codebase', type: 'Explore' },
            { id: 'agent_2', label: 'Run tests', type: 'test-reporter' },
          ],
          edges: [
            { source: 'main', target: 'agent_1' },
            { source: 'main', target: 'agent_2' },
          ],
        }),
      })
    })

    await page.goto('/tasks/1/graph')

    // Graph container must be visible
    const container = page.getByTestId('graph-container')
    await expect(container).toBeVisible({ timeout: 10000 })
  })

  test('renders graph header with task id', async ({ page }) => {
    await page.route('**/api/tasks/42/graph', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          nodes: [{ id: 'main', label: 'Main Agent', type: 'main' }],
          edges: [],
        }),
      })
    })

    await page.goto('/tasks/42/graph')

    await expect(page.getByText('Agent Graph — Task #42')).toBeVisible({ timeout: 10000 })
  })

  test('shows error state when API returns 404', async ({ page }) => {
    await page.route('**/api/tasks/999/graph', async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Task 999 not found' }),
      })
    })

    await page.goto('/tasks/999/graph')

    await expect(page.getByText('Failed to load graph')).toBeVisible({ timeout: 10000 })
    // Graph container still in DOM
    await expect(page.getByTestId('graph-container')).toBeAttached()
  })

  test('back button navigates to dashboard', async ({ page }) => {
    await page.route('**/api/tasks/1/graph', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          nodes: [{ id: 'main', label: 'Main Agent', type: 'main' }],
          edges: [],
        }),
      })
    })

    await page.goto('/tasks/1/graph')
    await expect(page.getByTestId('graph-container')).toBeVisible({ timeout: 10000 })

    await page.getByText('← Back').click()

    await expect(page).toHaveURL('/')
    await page.waitForSelector('text=FEATURE DASHBOARD', { timeout: 10000 })
  })

  test('clicking a node opens the log side panel with agent name', async ({ page }) => {
    await page.route('**/api/tasks/1/graph', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          nodes: [
            { id: 'main', label: 'Main Agent', type: 'main' },
            { id: 'agent_1', label: 'Explore codebase', type: 'Explore' },
          ],
          edges: [{ source: 'main', target: 'agent_1' }],
        }),
      })
    })

    await page.route('**/api/tasks/1/node-log/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: false,
          feature_id: 1,
          session_file: 'test.jsonl',
          entries: [
            {
              timestamp: '2024-01-01T00:00:00Z',
              entry_type: 'text',
              tool_name: null,
              text: 'Hello from main agent',
            },
          ],
          total_entries: 1,
        }),
      })
    })

    await page.goto('/tasks/1/graph')
    await expect(page.getByTestId('graph-container')).toBeVisible({ timeout: 10000 })

    // Wait for graph to finish rendering (status bar shows node count)
    await expect(page.getByText('2 nodes · 1 edges')).toBeVisible({ timeout: 10000 })

    // Trigger tap on node via cy instance stored on container element
    await page.evaluate(() => {
      const container = document.querySelector('[data-testid="graph-container"]')
      if (container && container._cy) {
        container._cy.$('#main').emit('tap')
      }
    })

    // Panel should appear with the agent name
    await expect(page.getByTestId('log-side-panel')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('log-panel-agent-name')).toBeVisible()
    await expect(page.getByTestId('log-panel-agent-name')).toContainText('Main Agent')
  })

  test('log side panel close button hides panel', async ({ page }) => {
    await page.route('**/api/tasks/1/graph', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          nodes: [{ id: 'main', label: 'Main Agent', type: 'main' }],
          edges: [],
        }),
      })
    })

    await page.route('**/api/tasks/1/node-log/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: false,
          feature_id: 1,
          session_file: 'test.jsonl',
          entries: [],
          total_entries: 0,
        }),
      })
    })

    await page.goto('/tasks/1/graph')
    await expect(page.getByTestId('graph-container')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('1 nodes · 0 edges')).toBeVisible({ timeout: 10000 })

    // Open panel via cy instance
    await page.evaluate(() => {
      const container = document.querySelector('[data-testid="graph-container"]')
      if (container && container._cy) {
        container._cy.$('#main').emit('tap')
      }
    })

    await expect(page.getByTestId('log-side-panel')).toBeVisible({ timeout: 5000 })

    // Close the panel
    await page.getByTestId('log-panel-close').click()
    await expect(page.getByTestId('log-side-panel')).not.toBeVisible({ timeout: 3000 })
  })

  test('log side panel shows log entries', async ({ page }) => {
    await page.route('**/api/tasks/1/graph', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          nodes: [{ id: 'main', label: 'Main Agent', type: 'main' }],
          edges: [],
        }),
      })
    })

    await page.route('**/api/tasks/1/node-log/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active: false,
          feature_id: 1,
          session_file: 'test.jsonl',
          entries: [
            { timestamp: '2024-01-01T00:00:00Z', entry_type: 'tool_use', tool_name: 'Bash', text: 'ls -la' },
            { timestamp: '2024-01-01T00:00:01Z', entry_type: 'text', tool_name: null, text: 'Done!' },
          ],
          total_entries: 2,
        }),
      })
    })

    await page.goto('/tasks/1/graph')
    await expect(page.getByText('1 nodes · 0 edges')).toBeVisible({ timeout: 10000 })

    await page.evaluate(() => {
      const container = document.querySelector('[data-testid="graph-container"]')
      if (container && container._cy) {
        container._cy.$('#main').emit('tap')
      }
    })

    await expect(page.getByTestId('log-side-panel')).toBeVisible({ timeout: 5000 })
    // Log entries should be rendered
    const entries = page.getByTestId('log-panel-entry')
    await expect(entries).toHaveCount(2, { timeout: 5000 })
  })

  test('shows node and edge count after successful render', async ({ page }) => {
    await page.route('**/api/tasks/1/graph', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          nodes: [
            { id: 'main', label: 'Main Agent', type: 'main' },
            { id: 'a1', label: 'Agent One', type: 'Explore' },
          ],
          edges: [{ source: 'main', target: 'a1' }],
        }),
      })
    })

    await page.goto('/tasks/1/graph')
    await expect(page.getByTestId('graph-container')).toBeVisible({ timeout: 10000 })

    // Node/edge count shown in header
    await expect(page.getByText('2 nodes · 1 edges')).toBeVisible()
  })
})
