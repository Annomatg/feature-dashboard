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
- **MCP Server** for feature management via Claude tools
- **Playwright** for E2E testing
- **ESLint** for code quality

## Project Structure

```
feature-dashboard/
├── frontend/               # React + Vite frontend
│   ├── src/
│   │   ├── components/    # Reusable UI components
│   │   ├── pages/         # Page components
│   │   ├── App.jsx        # Main app component
│   │   └── main.jsx       # Entry point
│   └── package.json
├── backend/               # FastAPI backend
│   ├── main.py           # API server
│   └── requirements.txt
├── api/                   # Database models and utilities
│   ├── database.py       # SQLAlchemy models
│   └── migration.py      # JSON to SQLite migration
├── mcp_server/           # MCP feature management server
│   └── feature_mcp.py
├── .mcp.json             # MCP server configuration
├── features.db           # SQLite database (created on first run)
└── .claude/              # Claude configuration
```

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
```bash
# Frontend development server (port 5173)
cd frontend && npm run dev

# Backend API server (port 8000)
venv\Scripts\uvicorn backend.main:app --reload

# Run E2E tests
cd frontend && npm test
```

### Database
```bash
# Start MCP server (for feature management)
venv\Scripts\python -m mcp_server.feature_mcp
```

## API Endpoints

- `GET /api/features` - List all features (with optional filters)
- `GET /api/features/stats` - Get statistics
- `GET /api/features/{id}` - Get single feature

Query parameters for `/api/features`:
- `passes=true/false` - Filter by passing status
- `in_progress=true/false` - Filter by in-progress status
- `category=<name>` - Filter by category

## Design Guidelines

- Use dark theme colors from Tailwind config
- Maintain consistent spacing and typography
- Use JetBrains Mono for code/numbers
- Follow existing component patterns from rl-dashboard

## Data Source

All feature data comes from `features.db`, a SQLite database with the following schema:

```sql
CREATE TABLE features (
  id INTEGER PRIMARY KEY,
  priority INTEGER NOT NULL,
  category VARCHAR(100) NOT NULL,
  name VARCHAR(255) NOT NULL,
  description TEXT NOT NULL,
  steps JSON NOT NULL,
  passes BOOLEAN NOT NULL DEFAULT 0,
  in_progress BOOLEAN NOT NULL DEFAULT 0
);
```

## Important Notes

- This project has its own independent `features.db` (separate from rl-training/rl-dashboard)
- Frontend proxies `/api` requests to backend at `localhost:8000`
- MCP server requires Python virtual environment at `venv/`
- Use existing agents and skills from `.claude/` directory for development
