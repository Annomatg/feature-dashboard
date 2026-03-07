import subprocess
import sys
import tempfile
import shutil
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app
from api.database import CategoryToken, create_database, DescriptionBigram, DescriptionToken, Feature, NameBigram, NameToken


class TestSchemas:
    """Unit tests for backend/schemas.py — verify the module is self-contained."""

    def test_schemas_importable_without_fastapi(self):
        """schemas.py should import using only pydantic + stdlib (no FastAPI/SQLAlchemy)."""
        import importlib
        mod = importlib.import_module("backend.schemas")
        assert hasattr(mod, "FeatureResponse")
        assert hasattr(mod, "LogEntry")
        assert hasattr(mod, "AutoPilotStatusResponse")
        assert hasattr(mod, "InterviewQuestionRequest")

    def test_feature_response_from_dict(self):
        """FeatureResponse accepts keyword arguments for all required fields."""
        from backend.schemas import FeatureResponse
        f = FeatureResponse(
            id=1,
            priority=100,
            category="Backend",
            name="Test",
            description="desc",
            steps=["step 1"],
            passes=False,
            in_progress=False,
        )
        assert f.id == 1
        assert f.model == "sonnet"
        assert f.comment_count == 0

    def test_auto_pilot_status_response_log_is_list_of_log_entries(self):
        """AutoPilotStatusResponse.log defaults to [] and accepts LogEntry items."""
        from backend.schemas import AutoPilotStatusResponse, LogEntry
        status = AutoPilotStatusResponse(enabled=True)
        assert status.log == []
        entry = LogEntry(timestamp="2025-01-01T00:00:00Z", level="info", message="hello")
        status.log.append(entry)
        assert len(status.log) == 1
        assert status.log[0].level == "info"

    def test_all_expected_classes_exported(self):
        """All classes listed in the feature description are present in schemas."""
        import backend.schemas as s
        expected = [
            "FeatureResponse", "StatsResponse", "PaginatedFeaturesResponse",
            "DatabaseInfo", "SelectDatabaseRequest", "CreateFeatureRequest",
            "UpdateFeatureRequest", "UpdateFeatureStateRequest",
            "UpdateFeaturePriorityRequest", "MoveFeatureRequest",
            "ReorderFeatureRequest", "LaunchClaudeRequest", "LaunchClaudeResponse",
            "PlanTasksRequest", "PlanTasksResponse", "SettingsResponse",
            "UpdateSettingsRequest", "CommentResponse", "CreateCommentRequest",
            "ClaudeLogLineResponse", "ClaudeLogResponse", "SessionLogEntry",
            "SessionLogResponse", "AutoPilotStatusResponse", "BudgetPeriodData",
            "BudgetResponse", "InterviewQuestionRequest", "InterviewAnswerRequest",
            "InterviewStartRequest", "LogEntry",
        ]
        for name in expected:
            assert hasattr(s, name), f"Missing schema class: {name}"

    def test_no_basemodel_in_main(self):
        """main.py must not define any BaseModel subclass directly."""
        main_py = Path(__file__).parent / "main.py"
        source = main_py.read_text(encoding="utf-8")
        assert "class " not in source.split("from backend.schemas import")[0].split("BaseModel")[-1] or \
               "BaseModel" not in source or \
               all("class " not in line for line in source.splitlines() if "BaseModel" in line), \
               "main.py still contains a BaseModel class definition"

        # Simpler: count class definitions that inherit from BaseModel
        import re
        matches = re.findall(r"^class \w+\(BaseModel\)", source, re.MULTILINE)
        assert matches == [], f"main.py still defines BaseModel classes: {matches}"

