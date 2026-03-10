# Feature Dashboard

See `project.json` for tech stack, structure, key files, API endpoints, and database schema.

## Development Workflow

- **Review**: Run `code-review` agent after code generation, before tests
- **Tests**: Use `test-reporter` agent for backend; `playwright-tester` for E2E
- **Commit**: Use `git-workflow` agent

## Commands

```bash
# Backend (REQUIRED — DO NOT run uvicorn manually)
dotnet run --project DevServer

# Frontend dev server
cd frontend && npm run dev

# E2E tests (Chromium only)
cd frontend && npm test

# MCP server
venv/Scripts/python -m mcp_server.feature_mcp
```

## Feature MCP Tools

- `feature_get_stats` — completion stats
- `feature_get_next` — next pending feature
- `feature_mark_passing` — mark complete
- `feature_skip` — move to end of queue
- `feature_create` / `feature_create_bulk` — add features

## Design

- Dark theme (Tailwind config)
- JetBrains Mono for code/numbers
- Follow existing component patterns

## Mobile Layout Rules (MANDATORY)

Every frontend change must consider portrait mobile (375–430px wide):

1. Hide text labels in compact header controls: use `hidden md:inline` inside icon-buttons
2. Add `flex-shrink-0` to header action buttons to prevent overflow
3. After adding any header control, verify visible at 375px in Playwright
4. Prefer icon-only at `< md` (< 768px); show label at `md:` and above

## Notes

- `features.db` is independent from rl-training/rl-dashboard
- MCP server requires `venv/`
- Use agents/skills from `.claude/` directory
