"""
Git operations router.

Provides endpoints for running git commands on the feature-dashboard project
and an optional runner project.
"""

import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.deps import PROJECT_DIR, load_settings
from backend.schemas import GitOperationResult, GitUpdateResponse

router = APIRouter(prefix="/api", tags=["git"])


async def _run_git(args: list[str], cwd: Path) -> GitOperationResult:
    """Execute a git command and return the result."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        return GitOperationResult(
            success=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=stdout_bytes.decode("utf-8", errors="replace").strip(),
            stderr=stderr_bytes.decode("utf-8", errors="replace").strip(),
        )
    except FileNotFoundError:
        return GitOperationResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr="git executable not found",
        )
    except Exception as exc:
        return GitOperationResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr=str(exc),
        )


@router.post("/git/update", response_model=GitUpdateResponse)
async def git_update():
    """Run git push in feature-dashboard, then git pull in the runner folder.

    Reads runner_path from settings. If runner_path is not set or the
    directory doesn't exist, the pull step is skipped.
    """
    # Step 1: git push in the feature-dashboard project directory
    push = await _run_git(["push"], cwd=PROJECT_DIR)

    if not push.success:
        return GitUpdateResponse(push=push)

    # Step 2: git pull in the runner directory (if configured)
    settings = load_settings()
    runner_path_str = settings.get("runner_path", "").strip()

    if not runner_path_str:
        return GitUpdateResponse(push=push)

    runner_dir = Path(runner_path_str).resolve()
    if not runner_dir.is_dir():
        pull = GitOperationResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr=f"Runner directory not found: {runner_path_str}",
        )
        return GitUpdateResponse(push=push, pull=pull)

    pull = await _run_git(["pull"], cwd=runner_dir)
    return GitUpdateResponse(push=push, pull=pull)
