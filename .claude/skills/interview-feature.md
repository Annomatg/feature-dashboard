---
name: interview-feature
description: Run the feature planning interview. Sends questions to the browser UI via the backend interview API, collects answers, then creates the feature using the feature_create MCP tool.
---

# Feature Planning Interview Skill

## Purpose

Conduct an interactive feature-planning interview through the browser UI. Each question is sent to the browser via the backend interview API; the user answers in the browser and the answer is returned to Claude via long-poll.

## Prerequisites

- Backend running at `http://localhost:8000` (DevServer must be active)
- Browser has Feature Dashboard open at `http://localhost:5173`

## API Quick Reference

| Action | Command |
|--------|---------|
| Post question | `curl -s -X POST http://localhost:8000/api/interview/question -H "Content-Type: application/json" -d '{"text":"...","options":[...]}'` |
| Poll for answer | `curl -s --max-time 310 http://localhost:8000/api/interview/answer` |
| End session | `curl -s -X DELETE http://localhost:8000/api/interview/session` |

**Note:** Always use `--max-time 310` on the answer poll — the server long-polls up to 300 s.

## Interview Procedure

### Phase 1: Collect feature data (one question per curl pair)

Run each step in sequence. Store every returned answer value in a variable.

**Step 1 — Category**
```bash
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -d '{"text":"What category does this feature belong to?","options":["Backend","Frontend","Functional","Style","Navigation","Error Handling","Data","Infrastructure"]}'
curl -s --max-time 310 http://localhost:8000/api/interview/answer
```
Parse `{"value": "<category>"}`. Store as `CATEGORY`.

**Step 2 — Name**
```bash
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -d '{"text":"What is the name of this feature?","options":["(type in browser)"]}'
curl -s --max-time 310 http://localhost:8000/api/interview/answer
```
Store as `NAME`.

**Step 3 — Description**
```bash
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -d '{"text":"Describe this feature in detail:","options":["(type in browser)"]}'
curl -s --max-time 310 http://localhost:8000/api/interview/answer
```
Store as `DESCRIPTION`.

**Step 4 — Steps (loop)**

Repeat for N = 1, 2, 3 … until the answer is exactly `done`:
```bash
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -d '{"text":"Enter step N (or type \"done\" to finish):","options":["done"]}'
curl -s --max-time 310 http://localhost:8000/api/interview/answer
```
Collect non-`done` answers into `STEPS` list.

### Phase 2: Summarize

Print to the terminal before creating:
```
Feature to create:
  Category:    <CATEGORY>
  Name:        <NAME>
  Description: <DESCRIPTION>
  Steps:
    1. <step1>
    2. <step2>
    ...
```

### Phase 3: Create

Call the MCP tool:
```
feature_create(
  category=CATEGORY,
  name=NAME,
  description=DESCRIPTION,
  steps=STEPS
)
```

### Phase 4: Continue?

Ask via the browser:
```bash
curl -s -X POST http://localhost:8000/api/interview/question \
  -H "Content-Type: application/json" \
  -d '{"text":"Add another feature?","options":["Yes","No"]}'
curl -s --max-time 310 http://localhost:8000/api/interview/answer
```
- Answer `Yes` → loop back to Phase 1 (session stays open)
- Answer `No` → end session (see below)

### Phase 5: End session

Always call this when done or on error:
```bash
curl -s -X DELETE http://localhost:8000/api/interview/session
```

## Error Handling

| Error | Action |
|-------|--------|
| POST question → 409 | Wait 1 s, retry (unconsumed answer still in state) |
| GET answer → 408 | Re-post the same question and poll again |
| GET answer → empty/error | Inform user, call DELETE /session, stop |
| Backend unreachable | Tell user to start DevServer: `dotnet run --project DevServer` |

## Critical Rules

1. Never post the next question before the previous answer is consumed.
2. Never call `feature_create` until all steps are collected (`done` received).
3. Always DELETE `/api/interview/session` on completion **or** on error.
4. `STEPS` must contain at least one item.
