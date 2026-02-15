---
name: e2e-test-db
description: Use when writing or modifying E2E tests that interact with the database. Ensures tests use isolated test database (features.test.db) instead of production database.
---

# E2E Test Database Skill

## When to Use

**Use when:**
- Writing new E2E tests that create/modify/delete features
- Debugging E2E test failures related to database state
- Modifying existing E2E tests to add database interactions
- Understanding why tests don't affect production data

**Don't use when:**
- Writing unit tests (those don't touch the database)
- Writing backend API tests (use pytest with monkeypatch)
- Running DevServer for manual testing (uses production DB)

## Quick Reference

**Test Database:** `features.test.db` (gitignored, auto-created)
**Production Database:** `features.db` (never touched by tests)
**Run Tests:** `cd frontend && npm test`

**Test Infrastructure:**
- `frontend/tests/start-test-backend.js` - Setup script
- `frontend/playwright.config.js` - Dual server config
- `backend/main.py` - TEST_DB_PATH environment variable support

## How It Works

Playwright automatically:
1. Creates fresh `features.test.db` from scratch
2. Seeds with 3 test features
3. Starts backend with `TEST_DB_PATH=features.test.db`
4. Runs tests against isolated database
5. Production `features.db` remains untouched

## Seed Data

**Default test features:**
- ID 1: "Test Feature with Description" (TODO lane)
- ID 2: "Test Feature in Progress" (IN PROGRESS lane)
- ID 3: "Completed Test Feature" (DONE lane)

## Writing Tests with Database Mutations

**Safe to create/delete features:**

```javascript
test('feature without description', async ({ page }) => {
  // Create test feature
  const response = await page.request.post('http://localhost:8000/api/features', {
    data: {
      priority: 999,
      category: 'Test',
      name: 'Test Feature',
      description: '',
      steps: ['Step 1'],
      passes: false,
      in_progress: false
    }
  });
  const feature = await response.json();

  // Test behavior...

  // Clean up (safe - test DB only)
  await page.request.delete(`http://localhost:8000/api/features/${feature.id}`);
});
```

## Backend Environment Variable

**How backend detects test mode:**

```python
# In backend/main.py
TEST_DB_PATH = os.environ.get("TEST_DB_PATH")
if TEST_DB_PATH:
    # Use test database
    test_db_path = Path(TEST_DB_PATH)
    _engine, _session_maker = create_database(test_db_path.parent)
else:
    # Use production database
    _engine, _session_maker = create_database(PROJECT_DIR)
```

**Set by start-test-backend.js:**
```javascript
env: { ...process.env, TEST_DB_PATH: testDbPath }
```

## Critical Rules

1. **Never commit** `features.test.db` (already in .gitignore)
2. **Test database recreated** fresh before each `npm test`
3. **Production database untouched** during all E2E tests
4. **All database mutations safe** in E2E tests
5. **Manual testing uses production DB** (DevServer doesn't set TEST_DB_PATH)

## Common Patterns

**Check feature count in test:**
```javascript
const features = await page.locator('.feature-card').all();
expect(features.length).toBe(3); // Default seed data
```

**Verify production DB untouched:**
```bash
# After tests
venv/Scripts/python.exe -c "from api.database import create_database; \
  session = create_database(Path('.'))[1](); \
  print(f'{session.query(Feature).count()} features')"
```

## Troubleshooting

**Backend using wrong database:**
- Check Playwright output for `[OK] Test database created`
- Verify `TEST_DB_PATH` in backend startup logs
- Confirm `features.test.db` exists during test run

**Tests failing due to stale data:**
- Test DB recreated fresh each run - impossible
- Check seed data in `start-test-backend.js`

**Production database modified during tests:**
- Verify `.gitignore` excludes `features.test.db`
- Check Playwright config uses `start-test-backend.js`
- Ensure `TEST_DB_PATH` environment variable set
