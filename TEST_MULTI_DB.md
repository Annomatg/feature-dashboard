# Testing Multi-Database Support

## Prerequisites

1. **Start DevServer** (Required for backend to run):
   ```bash
   dotnet run --project DevServer
   ```

2. **Wait for backend to start** - DevServer will show:
   ```
   Application startup complete.
   ```

## Running Tests

Once DevServer is running, in a new terminal:

```bash
venv\Scripts\python test_database_api.py
```

## What Gets Tested

1. ✓ Root endpoint lists new database endpoints
2. ✓ `GET /api/databases` returns list of configured databases
3. ✓ `GET /api/databases/active` returns current database
4. ✓ `POST /api/databases/select` switches databases
5. ✓ Invalid database paths are rejected
6. ✓ Existing features endpoints still work

## Manual Testing

### Test with curl:

```bash
# List databases
curl http://localhost:8000/api/databases | python -m json.tool

# Get active database
curl http://localhost:8000/api/databases/active | python -m json.tool

# Switch database
curl -X POST http://localhost:8000/api/databases/select \
  -H "Content-Type: application/json" \
  -d "{\"path\": \"features.db\"}"
```

## Configuration

Edit `dashboards.json` to add more databases:

```json
[
  {
    "name": "Feature Dashboard",
    "path": "features.db"
  },
  {
    "name": "Another Dashboard",
    "path": "path/to/another.db"
  }
]
```

**Note**: All paths in `dashboards.json` are relative to the project root.
