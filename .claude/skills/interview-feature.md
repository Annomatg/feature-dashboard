---
name: interview-feature
description: Run the feature planning interview. Sends questions to the browser UI via the backend interview API, collects answers, then creates the feature using the feature_create MCP tool.
---

# Feature Planning Interview Skill

## Prerequisites

- Backend running at `http://localhost:8000` (DevServer must be active)
- Browser has Feature Dashboard open at `http://localhost:5173`

## API Quick Reference

| Action | Command |
|--------|---------|
| Post question (first) | `curl -s -X POST http://localhost:8000/api/interview/question -H "Content-Type: application/json" -d '{"text":"...","options":[...]}'` |
| Post question (subsequent) | Add `-H "X-Interview-Token: $SESSION_TOKEN"` to every POST |
| Poll for answer | `curl -s --max-time 310 http://localhost:8000/api/interview/answer` |
| Notify board | `curl -s -X POST "http://localhost:8000/api/features/notify?feature_id=<ID>&name=<NAME>"` |
| End session | `curl -s -X DELETE http://localhost:8000/api/interview/session` |

**Note:** Always use `--max-time 310` on the answer poll — the server long-polls up to 300 s.

## Session Token (Duplicate-Instance Guard)

The first POST to `/api/interview/question` returns a `session_token` in the response body.
Store it immediately and include it as `X-Interview-Token` in **every subsequent POST** to
`/api/interview/question`. Without it, subsequent POSTs return 409 Conflict.

```bash
# First question — capture the token
RESPONSE=$(curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -d '{"text":"...","options":[...]}')
SESSION_TOKEN=$(echo "$RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin)['session_token'])")

# All subsequent questions — include the token
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -H "X-Interview-Token: $SESSION_TOKEN" \
  -d '{"text":"...","options":[...]}'
```

## Interview Procedure

### Phase 1: Collect feature data (one question per curl pair)

**Step 1 — Category (first POST, capture token)**
```bash
RESPONSE=$(curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -d '{"text":"What category does this feature belong to?","options":["Backend","Frontend","Functional","Style","Navigation","Error Handling","Data","Infrastructure"]}')
SESSION_TOKEN=$(echo "$RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin)['session_token'])")
CATEGORY=$(curl -s --max-time 310 http://localhost:8000/api/interview/answer | python -c "import sys,json; print(json.load(sys.stdin)['value'])")
```

**Step 2 — Name**
```bash
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -H "X-Interview-Token: $SESSION_TOKEN" \
  -d '{"text":"What is the name of this feature?","options":["(type in browser)"]}'
NAME=$(curl -s --max-time 310 http://localhost:8000/api/interview/answer | python -c "import sys,json; print(json.load(sys.stdin)['value'])")
```

**Step 3 — Description**
```bash
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -H "X-Interview-Token: $SESSION_TOKEN" \
  -d '{"text":"Describe this feature in detail:","options":["(type in browser)"]}'
DESCRIPTION=$(curl -s --max-time 310 http://localhost:8000/api/interview/answer | python -c "import sys,json; print(json.load(sys.stdin)['value'])")
```

**Step 4 — Steps (multi-line)**
```bash
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -H "X-Interview-Token: $SESSION_TOKEN" \
  -d '{"text":"Enter the implementation steps (one per line):","options":["(type steps, one per line)"]}'
STEPS_RAW=$(curl -s --max-time 310 http://localhost:8000/api/interview/answer | python -c "import sys,json; print(json.load(sys.stdin)['value'])")
```
Split `STEPS_RAW` on newlines. Trim whitespace. Filter blank lines. Store as `STEPS` list (at least one item).

### Phase 2: Summarize

Print before creating:
```
Feature to create:
  Category:    <CATEGORY>
  Name:        <NAME>
  Description: <DESCRIPTION>
  Steps:       1. <step1>  2. <step2>  ...
```

### Phase 3: Create

Call immediately — no confirmation prompt:
```
feature_create(category=CATEGORY, name=NAME, description=DESCRIPTION, steps=STEPS)
```
Print: `Created feature #<id>: <name>`

Notify board (URL-encode the name):
```bash
curl -s -X POST "http://localhost:8000/api/features/notify?feature_id=<id>&name=<URL-encoded-name>"
```

### Phase 4: Continue?

```bash
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -H "X-Interview-Token: $SESSION_TOKEN" \
  -d '{"text":"Add another feature?","options":["Yes","No"]}'
curl -s --max-time 310 http://localhost:8000/api/interview/answer
```
- `Yes` → loop back to Phase 1 (keep `$SESSION_TOKEN`, session stays open)
- `No` → end session

### Phase 5: End session

Always call on completion **or** on error:
```bash
curl -s -X DELETE http://localhost:8000/api/interview/session
```

## Error Handling

| Error | Action |
|-------|--------|
| POST question → 409 (answer pending) | Wait 1 s, retry with same `$SESSION_TOKEN` |
| POST question → 409 (session active, no token) | Another instance is running — abort, tell user |
| GET answer → 408 | Re-post the same question with `$SESSION_TOKEN`, poll again |
| GET answer → empty/error | Inform user, call DELETE /session, stop |
| Backend unreachable | Tell user to start DevServer: `dotnet run --project DevServer` |

## Critical Rules

1. Capture `session_token` from the first POST response — include it in every subsequent POST.
2. Never post the next question before the previous answer is consumed.
3. Never call `feature_create` until all 4 fields are collected.
4. Always DELETE `/api/interview/session` on completion **or** on error.
5. `STEPS` must contain at least one item after filtering blank lines.
6. Call `POST /api/features/notify` after every successful `feature_create`.
