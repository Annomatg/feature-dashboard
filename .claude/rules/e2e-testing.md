---
paths:
  - "frontend/tests/*.spec.js"
  - "frontend/playwright.config.js"
  - "frontend/tests/start-test-backend.js"
---

# E2E Testing Rules

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
// Safe to create/delete features in tests
const response = await page.request.post('http://localhost:8000/api/features', {
  data: { priority: 999, category: 'Test', name: 'Test', description: '', steps: ['Step 1'], passes: false, in_progress: false }
});
const feature = await response.json();

// Test behavior...

// Clean up
await page.request.delete(`http://localhost:8000/api/features/${feature.id}`);
```

## Running Tests

```bash
cd frontend && npm test
```

Playwright manages both frontend and backend automatically with test database.
