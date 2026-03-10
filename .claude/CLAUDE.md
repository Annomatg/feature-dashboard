# Feature Dashboard - Project Context

## Project Overview

**Feature Dashboard** is a web application for visualizing and managing project features and backlog items stored in a SQLite database. You are the project assistant and backlog manager.

## Tech Stack

### Frontend
- **React 18** with Vite for fast development
- **React Router** for navigation
- **TanStack Query** for data fetching and caching
- **Tailwind CSS** for styling (dark theme)
- **Lucide React** for icons

### Backend
- **FastAPI** for REST API endpoints
- **SQLAlchemy** for database ORM
- **SQLite** for data persistence (features.db)
- **Uvicorn** as ASGI server

### Development Tools
- **DevServer** (C# .NET 8.0) - Auto-restart backend on file changes
- **MCP Server** for feature management via Claude tools
- **Playwright** for E2E testing (Chromium only - other browsers not supported)
- **ESLint** for code quality

## Development Process

- **Review** Always use the `code-review` after code generation is finished and before running tests
- **Testing** Always use the `test-reporter` agent to run backend tests and get results. Always use the `playwright-tester` for E2E tests
- **Commit** Always use the `git-workflow` agent to commit the message to git

## Project Structure

See `project.json` for full structure, key files, services, API endpoints, and database schema.

## Feature Management

Features are stored in `features.db` and managed via MCP tools:

- `feature_get_stats` - Get completion statistics
- `feature_get_next` - Get next pending feature
- `feature_mark_passing` - Mark feature as complete
- `feature_skip` - Move feature to end of queue
- `feature_create` - Add new feature to backlog
- `feature_create_bulk` - Add multiple features

## Key Commands

### Development

**CRITICAL: Always use DevServer for backend development**

```bash
# Start DevServer (REQUIRED for backend development/testing)
# Watches backend/, api/, mcp_server/ and auto-restarts on changes
dotnet run --project DevServer

# Frontend development server (port 5173)
cd frontend && npm run dev

# Run E2E tests (Chromium only)
cd frontend && npm test
```

**DO NOT manually start uvicorn** - DevServer manages the backend process automatically.

### Testing

**Browser Support**: Chromium only. We do not test on Firefox, Safari, or WebKit as the user exclusively uses Chromium-based browsers.

### Database
```bash
# Start MCP server (for feature management)
venv\Scripts\python -m mcp_server.feature_mcp
```

## API Endpoints

### Features
- `GET /api/features` - List all features (with optional filters)
- `GET /api/features/stats` - Get statistics
- `GET /api/features/{id}` - Get single feature

Query parameters for `/api/features`:
- `passes=true/false` - Filter by passing status
- `in_progress=true/false` - Filter by in-progress status
- `category=<name>` - Filter by category

### Databases (Multi-Database Support)
- `GET /api/databases` - List configured databases from dashboards.json
- `GET /api/databases/active` - Get currently active database
- `POST /api/databases/select` - Switch to a different database (body: `{"path": "features.db"}`)

## Design Guidelines

- Use dark theme colors from Tailwind config
- Maintain consistent spacing and typography
- Use JetBrains Mono for code/numbers
- Follow existing component patterns from rl-dashboard

## Mobile Layout Rules (MANDATORY)

**Every frontend change must consider portrait mobile (375–430px wide) layout:**

1. **Text labels in compact header controls must be hidden on mobile.** Use `hidden md:inline` for text inside icon-buttons (AutoPilotToggle, etc.) so the icon-only variant fits on narrow screens.
2. **Action buttons must never overflow the viewport.** Add `flex-shrink-0` to header action buttons so flex does not squeeze them into invisibility.
3. **After adding any new header control**, verify it is visible at 375px: check `boundingBox().x + width <= 375` in a Playwright test.
4. **When adding new navigation items or toolbar buttons**, run the responsive-header tests at 375px and 430px before merging.
5. **Prefer icon-only at `< md` (< 768px)** for controls that combine icon + text label. Show full label only at `md:` and above.

## Data Source

All feature data comes from `features.db` (SQLite). Schema is documented in `project.json` under `database_schema`.

## Important Notes

- This project has its own independent `features.db` (separate from rl-training/rl-dashboard)
- Frontend proxies `/api` requests to backend at `localhost:8000`
- MCP server requires Python virtual environment at `venv/`
- Use existing agents and skills from `.claude/` directory for development
