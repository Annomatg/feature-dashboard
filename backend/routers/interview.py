"""
Interview endpoints router.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.deps import PLAN_TASKS_PROMPT_TEMPLATE, load_settings
import backend.deps as _deps
from backend.interview_state import get_interview_session, _log_event as _log_interview_event, get_debug_log
from backend.schemas import InterviewAnswerRequest, InterviewQuestionRequest, InterviewStartRequest

router = APIRouter(prefix="/api/interview", tags=["interview"])


@router.post("/question", status_code=200)
async def post_interview_question(
    request: InterviewQuestionRequest,
    x_interview_token: Optional[str] = Header(None),
):
    """
    Push a new question into the interview session.

    Called by Claude Code to send the next question to the browser.
    Overwrites any previously active question and resets answer state.

    Session token guard (duplicate-instance prevention):
      - First call (no active session): generates a session token, stores it,
        and returns it as ``session_token`` in the response body.
      - Subsequent calls: must supply the token in the ``X-Interview-Token``
        request header.  Returns 409 Conflict if the token is missing or
        does not match the stored owner token.

    Also returns 409 if the browser has already submitted an answer that Claude
    has not yet consumed via GET /api/interview/answer.
    """
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="Question text must not be empty")
    if not request.options:
        raise HTTPException(status_code=422, detail="At least one option is required")

    session = get_interview_session()

    # --- Duplicate-session guard ---
    if session.owner_token is None:
        # No active session — this caller becomes the owner.
        new_token = session.claim_session()
    else:
        # A session is already in progress — validate the caller's token.
        if x_interview_token != session.owner_token:
            raise HTTPException(
                status_code=409,
                detail="An interview session is already active. "
                       "Only the session owner may post questions.",
            )
        new_token = None  # token already known by caller, no need to return it

    if session.has_unconsumed_answer():
        raise HTTPException(
            status_code=409,
            detail="An answer is pending and has not been consumed yet. "
                   "Call GET /api/interview/answer before posting a new question.",
        )

    await session.set_question(request.text, request.options)

    response: dict = {
        "text": session.active_question["text"],
        "options": session.active_question["options"],
    }
    if new_token is not None:
        response["session_token"] = new_token
    return response


# Heartbeat interval for the SSE stream (seconds).
# Override in tests to avoid 15-second waits.
_SSE_HEARTBEAT_SECONDS: float = 15.0


@router.get("/question/stream")
async def interview_question_stream():
    """
    SSE endpoint for receiving interview questions in real time.

    Browser subscribes to this endpoint for the duration of an interview.
    Events pushed:
      - question:   when Claude posts a new question via POST /api/interview/question
      - heartbeat:  every 15 s to keep the connection alive through proxies
      - end:        when the session is terminated via DELETE /api/interview/session
    """
    session = get_interview_session()
    queue = session.subscribe()
    _log_interview_event(session, "sse_connect", {})

    async def event_generator():
        try:
            # Send the currently active question immediately if one exists
            if session.active_question:
                q = session.active_question
                yield (
                    f"event: question\n"
                    f"data: {json.dumps({'text': q['text'], 'options': q['options']})}\n\n"
                )

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SSE_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue

                if event["type"] == "question":
                    yield (
                        f"event: question\n"
                        f"data: {json.dumps({'text': event['text'], 'options': event['options']})}\n\n"
                    )
                elif event["type"] == "answer_received":
                    yield "event: answer_received\ndata: {}\n\n"
                elif event["type"] == "session_paused":
                    yield "event: session-paused\ndata: {}\n\n"
                elif event["type"] == "session_timeout":
                    yield "event: session-timeout\ndata: {}\n\n"
                    break
                elif event["type"] == "session_ended":
                    features_created = event.get("features_created", 0)
                    yield f"event: end\ndata: {json.dumps({'features_created': features_created})}\n\n"
                    break
        finally:
            session.unsubscribe(queue)
            _log_interview_event(session, "sse_disconnect", {})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# Timeouts for GET /api/interview/answer long-poll (seconds).
# Override in tests to avoid multi-minute waits.
#   Soft timeout: no answer yet → broadcast session_paused to browser (session stays alive)
#   Hard timeout: still no answer → kill session, return 408 to Claude
_SOFT_TIMEOUT_SECONDS: float = 300.0   # 5 minutes
_HARD_TIMEOUT_SECONDS: float = 600.0   # 10 minutes
# Legacy single-value override used by tests: setting this caps both soft and hard timeouts.
_ANSWER_POLL_TIMEOUT_SECONDS: float = _HARD_TIMEOUT_SECONDS


@router.get("/answer")
async def get_interview_answer():
    """
    Long-polling endpoint that blocks until the user submits an answer.

    Called by Claude immediately after posting a question.  Two-phase timeout:

    • Soft timeout (_SOFT_TIMEOUT_SECONDS, default 5 min): no answer yet → the
      server broadcasts a ``session_paused`` SSE event so the browser shows a
      Revive button.  Session state is preserved; Claude continues blocking on
      this endpoint.

    • Hard timeout (_HARD_TIMEOUT_SECONDS, default 10 min total): still no
      answer → session is cleared, ``session_timeout`` is broadcast, and 408 is
      returned to Claude.

    Returns 408 Request Timeout if no answer arrives within the hard timeout.
    """
    session = get_interview_session()
    answer = await session.wait_for_answer(
        soft_timeout=min(_SOFT_TIMEOUT_SECONDS, _ANSWER_POLL_TIMEOUT_SECONDS),
        hard_timeout=min(_HARD_TIMEOUT_SECONDS, _ANSWER_POLL_TIMEOUT_SECONDS),
    )

    if answer is None:
        # Hard timeout: broadcast session-timeout and clear state
        await session.timeout()
        raise HTTPException(
            status_code=408,
            detail="No answer received within the timeout period.",
        )

    return {"value": answer}


@router.post("/answer", status_code=200)
async def post_interview_answer(request: InterviewAnswerRequest):
    """
    Submit the user's answer to the current interview question.

    Called by the browser when the user selects an answer option.
    Stores the answer in session state and broadcasts an answer_received event
    to all SSE subscribers so the browser can show a waiting state.

    Returns 400 if there is no active question pending an answer, or if an
    answer has already been submitted and not yet consumed by Claude.
    """
    if not request.value.strip():
        raise HTTPException(status_code=422, detail="Answer value must not be empty")

    session = get_interview_session()

    if session.active_question is None:
        raise HTTPException(
            status_code=400,
            detail="No active question is pending an answer.",
        )

    if session.has_unconsumed_answer():
        raise HTTPException(
            status_code=400,
            detail="An answer has already been submitted and not yet consumed.",
        )

    await session.submit_answer(request.value)

    return {"status": "received", "value": request.value}


@router.delete("/session", status_code=200)
async def delete_interview_session(features_created: int = 0):
    """
    End the current interview session and notify all connected browsers.

    Clears all session state (active question, pending answer) and broadcasts
    a session_ended event to every SSE subscriber so the browser can close
    the interview UI.

    Optional query parameter:
        features_created (int, default 0): number of features created during
        the session, forwarded to SSE subscribers in the end event payload.

    Idempotent: safe to call even when no session is active.
    """
    session = get_interview_session()
    await session.reset(features_created=features_created)
    return {"message": "Session ended"}


@router.post("/revive", status_code=200)
async def revive_interview_session():
    """
    Revive a paused interview session by re-broadcasting the current question.

    Called by the browser when the user clicks the Revive button after a soft
    timeout has fired.  Re-sends the active question to all SSE subscribers so
    the browser can transition back to the active state.

    Returns 404 if no question is currently active (e.g. the hard timeout has
    already fired and cleared session state).
    """
    session = get_interview_session()
    question = await session.revive()

    if question is None:
        raise HTTPException(
            status_code=404,
            detail="No active question to revive. The session may have timed out.",
        )

    return {"status": "revived", "question": question}


@router.get("/debug")
async def get_interview_debug():
    """
    Return the session event log for debugging.

    Returns the full structured log for the active session, or the last
    session's log if it ended within the past 60 seconds.

    Returns 404 if no session is active and no recent log is available.
    """
    result = get_debug_log()
    if result is None:
        raise HTTPException(status_code=404, detail="No active or recent interview session.")
    return result


# ---------------------------------------------------------------------------
# Interview process launcher — description-driven dynamic interview
# ---------------------------------------------------------------------------

# Appended to the plan-tasks template to redirect all interaction to the browser.
_INTERVIEW_API_SUFFIX = """
## IMPORTANT: Use the Browser Interview API for All Interaction

You MUST NOT ask questions or await input in the terminal. The user is waiting
in their browser at /interview. All conversation must happen through the
following API.

### API Quick Reference

| Action | Command |
|--------|---------|
| Post question (first) | See "Safe JSON Pattern" below — NEVER use inline `-d '{...}'` |
| Post question (subsequent) | Add `-H "X-Interview-Token: $SESSION_TOKEN"` to every POST |
| Poll for answer | `curl -s --max-time 610 http://localhost:8000/api/interview/answer` |
| End session | `curl -s -X DELETE "http://localhost:8000/api/interview/session?features_created=<N>"` |

Always use `--max-time 610` on the answer poll — the server long-polls up to 600 s total
(soft pause at 5 min, hard kill at 10 min).

### CRITICAL: Always Use Python to Build the JSON Body

**NEVER** construct the curl body with inline `-d '{"text":"..."}'. Question text
may contain backslashes, quotes, or other characters that break shell JSON strings.
Always generate the body with Python:

```bash
# First question — captures SESSION_TOKEN from response
BODY=$(python -c "import json; print(json.dumps({'text': 'Your question here', 'options': ['Option A', 'Option B']}))")
RESPONSE=$(curl -s -X POST http://localhost:8000/api/interview/question \\
  -H "Content-Type: application/json" \\
  -d "$BODY")
SESSION_TOKEN=$(echo "$RESPONSE" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_token',''))")

# Subsequent questions — include the session token header
BODY=$(python -c "import json; print(json.dumps({'text': 'Next question', 'options': ['A', 'B']}))")
RESPONSE=$(curl -s -X POST http://localhost:8000/api/interview/question \\
  -H "Content-Type: application/json" \\
  -H "X-Interview-Token: $SESSION_TOKEN" \\
  -d "$BODY")
```

**Key rules:**
- Always use `python -c "import json; print(json.dumps({...}))"` to build the body
- Use `d.get('session_token', '')` — never use direct key access, which raises KeyError if the key is absent
- `session_token` is only present in the **first** POST response; subsequent responses omit it

### Option Types

- **Multiple choice**: `"options": ["Option A", "Option B"]`
- **Free text**: `"options": ["(type in browser)"]` — renders a text input in the browser

### Conversation Flow

**Phase 1 — Clarify**: Post your first question greeting the user, summarising
your understanding of their request, and asking one focused clarifying question.
Continue asking follow-up questions until you have enough detail.

**Phase 2 — Present Breakdown**: Post a question listing planned features
grouped by category. Options: `["Approve and Create", "Revise"]`.
If "Revise", ask what to change.

**Phase 3 — Create Features**: Call `feature_create_bulk` with ALL features at once.
Then post a final confirmation with options `["Done"]`.

**Phase 4 — End**: Call `DELETE /api/interview/session?features_created=<N>`.
Always call this on completion OR on error.

### Error Handling

| Error | Action |
|-------|--------|
| POST → 409 (answer pending) | Wait 1 s, retry with `$SESSION_TOKEN` |
| GET answer → 408 | Re-post same question, poll again |
| Any unrecoverable error | Call DELETE /api/interview/session, stop |
"""


@router.post("/start")
async def start_interview(request: InterviewStartRequest):
    """Launch a dynamic interview session driven by a user-supplied description.

    Combines the plan-tasks prompt template (with the user's description) with
    browser interview API instructions, then launches Claude as a hidden background
    process (no terminal window, stdout/stderr captured via pipes). Claude uses the
    interview API to conduct a dynamic conversation in the browser and creates
    features via feature_create_bulk.
    """
    if not request.description.strip():
        raise HTTPException(status_code=400, detail="Description cannot be empty")

    settings = load_settings()
    plan_template = settings.get("plan_tasks_prompt_template", PLAN_TASKS_PROMPT_TEMPLATE)
    prompt = plan_template.format(description=request.description.strip())
    prompt += _INTERVIEW_API_SUFFIX

    working_dir = str(_deps._current_db_path.parent)

    try:
        if sys.platform == "win32":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            ps_cmd = (
                f'claude --dangerously-skip-permissions --print '
                f'(Get-Content -LiteralPath "{prompt_file}" -Raw)'
            )
            launched = False
            for ps_exe in ["pwsh", "powershell"]:
                try:
                    subprocess.Popen(
                        [ps_exe, "-Command", ps_cmd],
                        cwd=working_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            if not launched:
                raise HTTPException(
                    status_code=500,
                    detail="No PowerShell found. Install PowerShell 7 (pwsh) or ensure powershell.exe is available.",
                )
        else:
            try:
                subprocess.Popen(
                    ["claude", "--dangerously-skip-permissions", "--print", prompt],
                    cwd=working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except FileNotFoundError:
                raise HTTPException(
                    status_code=500,
                    detail="Claude CLI not found. Make sure 'claude' is in your PATH.",
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch Claude: {str(e)}")

    return {"launched": True}
