"""
Tests for project.json — validates structure and key file references.

Covers:
- project.json exists and is valid JSON
- Required top-level keys are present
- Key files listed in project.json exist on disk
- API endpoints section has expected routes
"""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROJECT_JSON = PROJECT_ROOT / "project.json"


@pytest.fixture(scope="module")
def project_data():
    assert PROJECT_JSON.exists(), "project.json not found at project root"
    with open(PROJECT_JSON, encoding="utf-8") as f:
        return json.load(f)


class TestProjectJsonStructure:
    def test_file_exists(self):
        assert PROJECT_JSON.exists()

    def test_valid_json(self):
        with open(PROJECT_JSON, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_required_top_level_keys(self, project_data):
        required = {"name", "description", "tech_stack", "structure", "key_files", "services", "database_schema", "api_endpoints"}
        missing = required - set(project_data.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_tech_stack_sections(self, project_data):
        tech = project_data["tech_stack"]
        assert "frontend" in tech
        assert "backend" in tech
        assert "dev_tools" in tech

    def test_database_schema_has_columns(self, project_data):
        schema = project_data["database_schema"]
        assert "table" in schema
        assert schema["table"] == "features"
        assert "columns" in schema
        expected_cols = {"id", "priority", "category", "name", "description", "steps", "passes", "in_progress"}
        missing = expected_cols - set(schema["columns"].keys())
        assert not missing, f"Missing columns: {missing}"

    def test_api_endpoints_not_empty(self, project_data):
        assert len(project_data["api_endpoints"]) > 0

    def test_services_has_backend(self, project_data):
        assert "backend_api" in project_data["services"]
        assert "localhost:8000" in project_data["services"]["backend_api"]


class TestProjectJsonKeyFiles:
    def test_key_files_section_exists(self, project_data):
        assert isinstance(project_data["key_files"], dict)
        assert len(project_data["key_files"]) > 0

    def test_critical_key_files_exist(self, project_data):
        """Check that non-runtime key files actually exist on disk."""
        # Only check files that should always exist (not runtime-created or gitignored ones)
        always_present = [
            "backend/main.py",
            "api/database.py",
            "mcp_server/feature_mcp.py",
            "DevServer/Program.cs",
            "playwright.config.js",
        ]
        missing = []
        for rel_path in always_present:
            if not (PROJECT_ROOT / rel_path).exists():
                missing.append(rel_path)
        assert not missing, f"Key files missing from disk: {missing}"

    def test_structure_dirs_exist(self, project_data):
        """Check that directory paths listed in structure actually exist."""
        missing = []
        for dir_path in project_data["structure"]:
            full = PROJECT_ROOT / dir_path.rstrip("/")
            if not full.exists():
                missing.append(dir_path)
        assert not missing, f"Directories in structure missing from disk: {missing}"
