# Backend Testing - Agent Guide

## Quick Reference

### Running Tests
```bash
# All tests
./venv/Scripts/python.exe -m pytest backend/test_crud_api.py -v

# Specific test
./venv/Scripts/python.exe -m pytest backend/test_crud_api.py::TestCreateFeature::test_create_feature_success -v
```

## Database Isolation (CRITICAL)

Tests use **monkeypatch** to inject isolated temp databases. **Never modify this pattern** - it prevents production data corruption.

```python
@pytest.fixture
def client(test_db, monkeypatch):
    import backend.main as main_module
    monkeypatch.setattr(main_module, '_session_maker', test_db)
    yield TestClient(app)
```

**Why monkeypatch?** Backend uses direct `session = get_session()` calls, not FastAPI `Depends()`, so `app.dependency_overrides` won't work.

## Test Data

Each test gets fresh seeded data:
- **4 features total**
- Features 1-2: TODO lane
- Feature 3: DONE lane
- Feature 4: IN-PROGRESS lane
- All names start with "Feature "

## Writing Tests

```python
class TestNewEndpoint:
    def test_success(self, client):
        response = client.post("/api/endpoint", json={...})
        assert response.status_code == 201
        assert response.json()["field"] == value

    def test_not_found(self, client):
        response = client.get("/api/endpoint/999")
        assert response.status_code == 404
```

## Coverage (24 tests)

- POST /api/features - create with validation
- PUT /api/features/{id} - update (full/partial)
- DELETE /api/features/{id} - delete
- PATCH /api/features/{id}/state - state transitions + completed_at
- PATCH /api/features/{id}/priority - reordering
- PATCH /api/features/{id}/move - up/down within lane
- Edge cases: boundaries, lane isolation, validation
- **test_isolation_from_production** - verifies no production data access

## Safety

✅ Safe to run while DevServer is running
✅ Zero risk to production database
✅ Automatic cleanup via engine.dispose()
✅ Each test isolated from others

## Debugging

```bash
# Verbose
./venv/Scripts/python.exe -m pytest backend/test_crud_api.py -vv

# With prints
./venv/Scripts/python.exe -m pytest backend/test_crud_api.py -s

# With debugger
./venv/Scripts/python.exe -m pytest backend/test_crud_api.py --pdb
```
