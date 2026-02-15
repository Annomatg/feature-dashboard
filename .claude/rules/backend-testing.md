---
paths:
  - "backend/test_*.py"
  - "backend/**/test_*.py"
---

# Backend Test File Rules

## Database Isolation (CRITICAL)

**NEVER modify the monkeypatch pattern** - it prevents production data corruption.

```python
@pytest.fixture
def client(test_db, monkeypatch):
    import backend.main as main_module
    monkeypatch.setattr(main_module, '_session_maker', test_db)
    yield TestClient(app)
```

**Why?** Backend uses direct `session = get_session()` calls, not FastAPI `Depends()`, so `app.dependency_overrides` won't work.

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
