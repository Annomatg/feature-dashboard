"""
Settings and budget endpoints router.
"""

import asyncio
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.deps import PLAN_TASKS_PROMPT_TEMPLATE, PLANNING_MODEL, load_settings, save_settings
from backend.providers import REGISTRY, get_provider
from backend.schemas import BudgetPeriodData, BudgetResponse, SettingsResponse, UpdateSettingsRequest

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """Get application settings."""
    settings = load_settings()
    settings["available_providers"] = sorted(REGISTRY.keys())
    return SettingsResponse(**settings)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(request: UpdateSettingsRequest):
    """Update application settings."""
    try:
        # Validate the requested provider before saving
        get_provider(request.provider)
        current = load_settings()
        settings = {
            "claude_prompt_template": request.claude_prompt_template,
            "plan_tasks_prompt_template": (
                request.plan_tasks_prompt_template
                if request.plan_tasks_prompt_template is not None
                else current.get("plan_tasks_prompt_template", PLAN_TASKS_PROMPT_TEMPLATE)
            ),
            "autopilot_budget_limit": request.autopilot_budget_limit,
            "provider": request.provider,
            "planning_model": (
                request.planning_model
                if request.planning_model is not None
                else current.get("planning_model", PLANNING_MODEL)
            ),
            "runner_path": (
                request.runner_path
                if request.runner_path is not None
                else current.get("runner_path", "")
            ),
        }
        save_settings(settings)
        settings["available_providers"] = sorted(REGISTRY.keys())
        return SettingsResponse(**settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")


@router.get("/budget", response_model=BudgetResponse)
async def get_budget():
    """Get AI provider budget/usage information.

    Reads the Claude OAuth credentials from ~/.claude/.credentials.json and
    calls the Anthropic usage API to return 5-hour and 7-day utilization
    percentages with reset times.  Returns an error field instead of raising
    an HTTP exception so the UI can degrade gracefully when credentials are
    absent or the API is unreachable.
    """

    def _format_reset_time(reset_at: str) -> str:
        """Return a human-readable reset time: 'HH:MM' today, 'ddd HH:MM' otherwise."""
        if not reset_at:
            return "unknown"
        bare = reset_at[:19] if len(reset_at) >= 19 else reset_at
        try:
            utc_time = datetime.fromisoformat(bare).replace(tzinfo=timezone.utc)
            local_time = utc_time.astimezone()
            now = datetime.now(local_time.tzinfo)
            if local_time.date() == now.date():
                return local_time.strftime('%H:%M')
            return local_time.strftime('%a %H:%M')
        except Exception:
            return reset_at

    def _fetch_usage():
        cred_path = Path.home() / '.claude' / '.credentials.json'
        if not cred_path.exists():
            return None, "Credentials not found (~/.claude/.credentials.json)"
        try:
            creds = json.loads(cred_path.read_text(encoding='utf-8'))
            token = creds.get('claudeAiOauth', {}).get('accessToken')
            if not token:
                return None, "No OAuth access token found in credentials"
        except Exception as exc:
            return None, f"Failed to read credentials: {exc}"
        try:
            req = urllib.request.Request(
                'https://api.anthropic.com/api/oauth/usage',
                headers={
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {token}',
                    'anthropic-beta': 'oauth-2025-04-20',
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode('utf-8')), None
        except urllib.error.HTTPError as exc:
            return None, f"API error: {exc.code} {exc.reason}"
        except Exception as exc:
            return None, f"Request failed: {exc}"

    data, error = await asyncio.get_event_loop().run_in_executor(None, _fetch_usage)
    if error:
        return BudgetResponse(error=error)

    result = BudgetResponse()
    fh = data.get('five_hour')
    if fh is not None:
        result.five_hour = BudgetPeriodData(
            utilization=round(float(fh.get('utilization', 0)), 1),
            resets_at=fh.get('resets_at', ''),
            resets_formatted=_format_reset_time(fh.get('resets_at', '')),
        )
    sd = data.get('seven_day')
    if sd is not None:
        result.seven_day = BudgetPeriodData(
            utilization=round(float(sd.get('utilization', 0)), 1),
            resets_at=sd.get('resets_at', ''),
            resets_formatted=_format_reset_time(sd.get('resets_at', '')),
        )
    return result
