"""
Pydantic request/response models for the Feature Dashboard API.

All BaseModel classes are defined here to keep main.py free of data-class
noise.  Only pydantic and stdlib imports are used — no circular dependencies.
"""

from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Auto-pilot log
# ---------------------------------------------------------------------------

class LogEntry(BaseModel):
    """A single auto-pilot log entry with timestamp, severity level, and message."""
    timestamp: str          # ISO 8601 UTC timestamp
    level: str              # 'info' | 'success' | 'error'
    message: str


# ---------------------------------------------------------------------------
# Feature response models
# ---------------------------------------------------------------------------

class FeatureResponse(BaseModel):
    """Feature data response."""
    model_config = {"from_attributes": True}

    id: int
    priority: int
    category: str
    name: str
    description: str
    steps: list[str]
    passes: bool
    in_progress: bool
    model: Optional[str] = "sonnet"
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    completed_at: Optional[str] = None
    comment_count: int = 0
    recent_log: Optional[str] = None


class StatsResponse(BaseModel):
    """Statistics response."""
    passing: int
    in_progress: int
    total: int
    percentage: float


class PaginatedFeaturesResponse(BaseModel):
    """Paginated features response with metadata."""
    features: list[FeatureResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------

class DatabaseInfo(BaseModel):
    """Database information."""
    name: str
    path: str
    exists: bool
    is_active: bool


class SelectDatabaseRequest(BaseModel):
    """Request to select a database."""
    path: str


# ---------------------------------------------------------------------------
# Feature CRUD request models
# ---------------------------------------------------------------------------

class CreateFeatureRequest(BaseModel):
    """Request to create a new feature."""
    category: str
    name: str
    description: str
    steps: list[str]
    model: Optional[str] = "sonnet"


class UpdateFeatureRequest(BaseModel):
    """Request to update feature fields."""
    category: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list[str]] = None
    model: Optional[str] = None


class UpdateFeatureStateRequest(BaseModel):
    """Request to change feature state (passes/in_progress)."""
    passes: Optional[bool] = None
    in_progress: Optional[bool] = None


class UpdateFeaturePriorityRequest(BaseModel):
    """Request to set a specific priority value."""
    priority: int


class MoveFeatureRequest(BaseModel):
    """Request to move feature up or down within its lane."""
    direction: str  # "up" or "down"


class ReorderFeatureRequest(BaseModel):
    """Request to reorder a feature by placing it before or after a target feature."""
    target_id: int
    insert_before: bool


# ---------------------------------------------------------------------------
# Claude launch models
# ---------------------------------------------------------------------------

class LaunchClaudeRequest(BaseModel):
    """Request body for launching a Claude Code session."""
    hidden_execution: bool = True


class LaunchClaudeResponse(BaseModel):
    """Response for launching a Claude Code session."""
    launched: bool
    feature_id: int
    prompt: str
    working_directory: str
    model: str
    hidden_execution: bool


class PlanTasksRequest(BaseModel):
    """Request body for launching a plan-tasks Claude session."""
    description: str


class PlanTasksResponse(BaseModel):
    """Response for launching a plan-tasks Claude session."""
    launched: bool
    prompt: str
    working_directory: str


# ---------------------------------------------------------------------------
# Settings models
# ---------------------------------------------------------------------------

class SettingsResponse(BaseModel):
    """Application settings response."""
    claude_prompt_template: str
    plan_tasks_prompt_template: str
    autopilot_budget_limit: int = 0
    provider: str = "claude"
    available_providers: list[str] = []


class UpdateSettingsRequest(BaseModel):
    """Request to update application settings."""
    claude_prompt_template: str
    plan_tasks_prompt_template: Optional[str] = None
    autopilot_budget_limit: int = 0
    provider: str = "claude"


# ---------------------------------------------------------------------------
# Comment models
# ---------------------------------------------------------------------------

class CommentResponse(BaseModel):
    """Comment data response."""
    id: int
    feature_id: int
    content: str
    created_at: Optional[str] = None


class CreateCommentRequest(BaseModel):
    """Request to add a comment to a feature."""
    content: str


# ---------------------------------------------------------------------------
# Claude log models
# ---------------------------------------------------------------------------

class ClaudeLogLineResponse(BaseModel):
    """A single captured output line returned by the claude-log endpoint."""
    timestamp: str
    stream: str
    text: str


class ClaudeLogResponse(BaseModel):
    """Response for GET /api/features/{id}/claude-log."""
    feature_id: int
    active: bool
    lines: list[ClaudeLogLineResponse]
    total_lines: int


class SessionLogEntry(BaseModel):
    """A single entry from the Claude JSONL session log."""
    timestamp: str
    entry_type: str  # 'tool_use' | 'text'
    tool_name: Optional[str] = None
    text: str


class SessionLogResponse(BaseModel):
    """Response for GET /api/autopilot/session-log."""
    active: bool
    feature_id: Optional[int] = None  # ID of the feature being processed (autopilot or manual)
    session_file: Optional[str] = None
    entries: list[SessionLogEntry]
    total_entries: int


class AutoPilotStatusResponse(BaseModel):
    """Response for auto-pilot enable/status."""
    enabled: bool
    stopping: bool = False  # True when disabled but Claude process still running
    current_feature_id: Optional[int] = None
    current_feature_name: Optional[str] = None
    current_feature_model: Optional[str] = None
    last_error: Optional[str] = None
    log: list[LogEntry] = []
    # Manual launch fields (user clicked "Launch Claude" in detail panel)
    manual_active: bool = False
    manual_feature_id: Optional[int] = None
    manual_feature_name: Optional[str] = None
    manual_feature_model: Optional[str] = None
    # Budget fields
    budget_limit: int = 0
    features_completed: int = 0
    budget_exhausted: bool = False


# ---------------------------------------------------------------------------
# Budget models
# ---------------------------------------------------------------------------

class BudgetPeriodData(BaseModel):
    """Usage data for a single AI billing period."""
    utilization: float      # 0–100 percentage (may exceed 100 when exhausted)
    resets_at: str          # ISO 8601 UTC timestamp from the provider
    resets_formatted: str   # Human-readable: "14:30" (today) or "Mon 14:30"


class BudgetResponse(BaseModel):
    """AI provider budget/usage response."""
    provider: str = "anthropic"
    five_hour: Optional[BudgetPeriodData] = None
    seven_day: Optional[BudgetPeriodData] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Interview models
# ---------------------------------------------------------------------------

class InterviewQuestionRequest(BaseModel):
    text: str
    options: list[str]


class InterviewAnswerRequest(BaseModel):
    value: str


class InterviewStartRequest(BaseModel):
    description: str
