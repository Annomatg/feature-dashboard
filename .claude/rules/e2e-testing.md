---
paths:
  - "**/*.spec.js"
---

# E2E Testing Rules

For running tests always use the `playwright-tester` agent.

## Isolated Test Database (CRITICAL)

**Always use test database** - E2E tests run against `features.test.db`, not production `features.db`.

**How it works:**
- Playwright auto-creates fresh `features.test.db` before tests
- Backend detects `TEST_DB_PATH` environment variable
- Production database never touched during `npm test`

## Reference e2e-test-db Skill

When writing/modifying E2E tests with database interactions, reference the `e2e-test-db` skill for:
- Isolated test database setup details
- Safe create/delete patterns
- Test infrastructure understanding
- Troubleshooting test failures

## Default Seed Data

Test database contains 3 features:
- ID 1: "Test Feature with Description" (TODO)
- ID 2: "Test Feature in Progress" (IN PROGRESS)
- ID 3: "Completed Test Feature" (DONE)

## Safe Database Mutations

```javascript
// ALWAYS use port 8001 (test backend) — port 8000 is production and must never be touched
const API = 'http://localhost:8001';

const response = await page.request.post(`${API}/api/features`, {
  data: { category: 'Test', name: 'My Test Feature', description: '', steps: [] }
});
const feature = await response.json();

// Test behavior...

// Clean up after the test
await page.request.delete(`${API}/api/features/${feature.id}`);
```

## Running Tests

```bash
cd frontend && npm test
```

Playwright manages both frontend and backend automatically with test database.
