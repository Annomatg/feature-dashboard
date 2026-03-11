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
from backend.schemas import GitCommitInfoResponse, GitOperationResult, GitUpdateResponse

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


@router.get("/git/commit/{commit_hash}", response_model=GitCommitInfoResponse)
async def get_commit_info(commit_hash: str):
    """Get details for a single git commit by its hash.

    Looks up the commit in the feature-dashboard repository and returns
    the full hash, abbreviated hash, commit message, author name, and date.
    Returns a 200 with an error field set if the commit hash is not found.
    """
    result = await _run_git(
        ["show", "--no-patch", "--format=%H%n%s%n%an%n%ai", commit_hash],
        cwd=PROJECT_DIR,
    )

    if not result.success or not result.stdout:
        return GitCommitInfoResponse(
            hash=commit_hash,
            short_hash=commit_hash[:7] if len(commit_hash) >= 7 else commit_hash,
            message="",
            author="",
            date="",
            error=result.stderr or f"Commit {commit_hash!r} not found",
        )

    lines = result.stdout.splitlines()
    full_hash = lines[0] if len(lines) > 0 else commit_hash
    message = lines[1] if len(lines) > 1 else ""
    author = lines[2] if len(lines) > 2 else ""
    date = lines[3] if len(lines) > 3 else ""

    return GitCommitInfoResponse(
        hash=full_hash,
        short_hash=full_hash[:7],
        message=message,
        author=author,
        date=date,
    )
