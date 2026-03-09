---
paths:
  - "**/test_*.py"
---

# Backend Test File Rules

When running tests always use the `test-reporter` agent.

## Database Isolation (CRITICAL)

**NEVER use `TestClient(app)` directly** — always use the `client` fixture from `conftest.py`. Direct `TestClient(app)` writes to the production database.

The `client` fixture patches `backend.deps` (not `backend.main`):

```python
# conftest.py — actual pattern (DO NOT change)
@pytest.fixture
def client(monkeypatch):
    import backend.main as main_module
    import backend.deps as deps_module
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "features.db"
    engine, session_maker = create_database(Path(temp_dir))
    monkeypatch.setattr(deps_module, '_session_maker', session_maker)
    monkeypatch.setattr(deps_module, '_current_db_path', temp_db_path)
    monkeypatch.setattr(main_module.asyncio, 'create_task',
                        lambda coro: (coro.close(), None)[1])
    yield TestClient(app)
```

**Why `deps_module`?** `get_session()` lives in `backend.deps` and all routers import it from there. Patching `main_module._session_maker` has no effect.

## Test Data Structure

Each test fixture provides:
- **4 features total** (features 1-4)
- Features 1-2: TODO lane (passes=False, in_progress=False)
- Feature 3: DONE lane (passes=True, in_progress=False)
- Feature 4: IN-PROGRESS lane (passes=False, in_progress=True)
- All names start with "Feature "

## Writing Tests

```python
class TestNewEndpoint:
    def test_success(self, client):
        response = client.post("/api/endpoint", json={...})
        assert response.status_code == 201
        assert response.json()["field"] == expected_value

    def test_not_found(self, client):
        response = client.get("/api/endpoint/999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
```

## Running Tests

Always run after backend changes:
```bash
./venv/Scripts/python.exe -m pytest backend/test_crud_api.py -v
```

See `.claude/docs/backend-testing.md` for full guide.
