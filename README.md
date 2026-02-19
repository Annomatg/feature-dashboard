# Feature Dashboard

Web application for managing project feature backlogs across all Godot projects. Provides a Kanban board UI and a global MCP server that gives Claude Code access to any project's feature backlog.

## Architecture

- **Frontend**: React + Vite (port 5173)
- **Backend**: FastAPI (port 8000, managed by DevServer)
- **Database**: SQLite (`features.db`) — one per project
- **MCP Server**: Global, shared across all Godot projects
- **DevServer**: C# app that watches Python files and auto-restarts the backend

## Projects using this system

All three projects share the same DB schema and global MCP:

| Project | DB path |
|---|---|
| feature-dashboard | `F:/Work/Godot/feature-dashboard/features.db` |
| rl-training | `F:/Work/Godot/rl-training/features.db` |
| rl-dashboard | `F:/Work/Godot/rl-dashboard/features.db` |

---

## First-time Setup (or re-setup from scratch)

### 1. Python virtual environment

```bash
cd F:/Work/Godot/feature-dashboard
python -m venv venv
./venv/Scripts/pip install -r backend/requirements.txt
./venv/Scripts/pip install mcp fastmcp
```

### 2. Frontend dependencies

```bash
cd frontend
npm install
```

### 3. Global MCP server

Register the `features` MCP server at user scope so it's available in all projects:

```bash
claude mcp add --scope user features \
  "F:/Work/Godot/feature-dashboard/venv/Scripts/python.exe" \
  "F:/Work/Godot/feature-dashboard/mcp_server/feature_mcp.py" \
  --env "PYTHONPATH=F:/Work/Godot/feature-dashboard"
```

This writes to `C:\Users\Sprys\.claude.json` under `mcpServers.features`. The MCP server uses `.` as `PROJECT_DIR` by default, so it always operates on the current project's `features.db`.

### 4. Migrate all project databases

Run the startup migration to ensure all project DBs have the latest schema (`db_meta` + all columns):

```bash
cd F:/Work/Godot/feature-dashboard
./venv/Scripts/python.exe -c "from api.migration import migrate_all_dashboards; migrate_all_dashboards()"
```

Or just start the backend — it runs `migrate_all_dashboards()` automatically on startup.

---

## Running the app

```bash
# Terminal 1 — backend (auto-restarts on Python file changes)
dotnet run --project DevServer

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open http://localhost:5173

---

## Adding a new project to the system

1. Make sure the project has a `features.db` (the MCP creates one automatically on first use)
2. Add it to `dashboards.json`:
   ```json
   { "name": "My Project", "path": "F:/Work/Godot/my-project/features.db" }
   ```
3. Remove any project-local `features` MCP entry from the project's `.mcp.json` (the global one replaces it)
4. Delete legacy `api/` and `mcp_server/` directories from that project if they exist

---

## DB Schema versioning

Schema version is tracked in a `db_meta` table. Current version: **3**.

| Version | Migration |
|---|---|
| v1 | Add `in_progress` column |
| v2 | Fix NULL boolean values |
| v3 | Add `created_at`, `modified_at`, `completed_at` columns |

New migrations go in `api/database.py` — increment `LATEST_SCHEMA_VERSION` and add to `_MIGRATIONS`.

---

## Running tests

```bash
# Backend unit tests
./venv/Scripts/python.exe -m pytest backend/test_crud_api.py -v

# E2E tests (requires frontend + backend running)
cd frontend && npm test
```
