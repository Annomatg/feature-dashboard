---
paths:
  - "backend/**/*.py"
  - "api/**/*.py"
---

# Backend Development Rules

## Test-Driven Development (REQUIRED)

When writing or modifying backend functionality:

1. **Write tests FIRST** or immediately after implementation
2. **Run tests** to verify everything works
3. **Only commit** when all tests pass

### Testing Workflow

```bash
# After making backend changes, ALWAYS run:
./venv/Scripts/python.exe -m pytest backend/test_crud_api.py -v
```

**All tests must pass before committing.**

### Test Coverage Requirements

For new endpoints or features:
- ✅ Success cases (happy path)
- ✅ Error cases (404, 400, 422)
- ✅ Edge cases (boundaries, validation)
- ✅ Side effects (timestamps, state changes)

### Test Example

```python
class TestNewEndpoint:
    def test_success(self, client):
        """Test successful operation."""
        response = client.post("/api/endpoint", json={...})
        assert response.status_code == 201

    def test_validation_error(self, client):
        """Test invalid input."""
        response = client.post("/api/endpoint", json={...})
        assert response.status_code == 422
```

See `.claude/docs/backend-testing.md` for testing patterns and database isolation.
