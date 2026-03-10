import subprocess
import sys
import tempfile
import shutil
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.main import app
from api.database import CategoryToken, create_database, DescriptionBigram, DescriptionToken, Feature, NameBigram, NameToken


class TestDatabaseEndpoints:
    """Tests for GET /, GET /api/databases, GET /api/databases/active, POST /api/databases/select."""

    def test_root_returns_api_info(self, client):
        """GET / returns API info with expected keys."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Feature Dashboard API"
        assert data["version"] == "1.0.0"
        assert "endpoints" in data
        assert "get_features" in data["endpoints"]
        assert "databases" in data["endpoints"]

    def test_get_databases_lists_configured_dbs(self, client, monkeypatch, tmp_path):
        """GET /api/databases returns list of configured databases."""
        import sqlite3
        import backend.deps as deps_module
        import backend.routers.databases as db_router

        # Create an actual db file at tmp_path
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE features (id INTEGER PRIMARY KEY)")
        conn.close()

        # Patch load_dashboards_config to return controlled data
        monkeypatch.setattr(db_router, 'load_dashboards_config',
                            lambda: [{"name": "Test DB", "path": str(db_path)}])
        monkeypatch.setattr(db_router, 'PROJECT_DIR', Path("/"))
        monkeypatch.setattr(deps_module, '_current_db_path', db_path)

        response = client.get("/api/databases")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_databases_empty_config(self, client, monkeypatch):
        """GET /api/databases returns empty list when config has no entries."""
        import backend.routers.databases as db_router
        monkeypatch.setattr(db_router, 'load_dashboards_config', lambda: [])

        response = client.get("/api/databases")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_active_database_found_in_config(self, client, monkeypatch, tmp_path):
        """GET /api/databases/active returns the active DB when found in config."""
        import backend.deps as deps_module
        import backend.routers.databases as db_router

        db_path = tmp_path / "features.db"
        db_path.touch()

        monkeypatch.setattr(deps_module, '_current_db_path', db_path)
        monkeypatch.setattr(db_router, 'PROJECT_DIR', tmp_path)
        monkeypatch.setattr(db_router, 'load_dashboards_config',
                            lambda: [{"name": "My DB", "path": "features.db"}])

        response = client.get("/api/databases/active")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My DB"
        assert data["is_active"] is True

    def test_get_active_database_not_in_config(self, client, monkeypatch, tmp_path):
        """GET /api/databases/active falls back when DB not in config."""
        import backend.deps as deps_module
        import backend.routers.databases as db_router

        db_path = tmp_path / "custom.db"
        db_path.touch()

        monkeypatch.setattr(deps_module, '_current_db_path', db_path)
        monkeypatch.setattr(db_router, 'PROJECT_DIR', tmp_path)
        monkeypatch.setattr(db_router, 'load_dashboards_config', lambda: [])

        response = client.get("/api/databases/active")
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True
        assert data["name"] == "Current Database"

    def test_select_database_not_found(self, client, monkeypatch, tmp_path):
        """POST /api/databases/select returns 404 when file does not exist."""
        import backend.routers.databases as db_router
        monkeypatch.setattr(db_router, 'PROJECT_DIR', tmp_path)

        response = client.post("/api/databases/select", json={"path": "nonexistent.db"})
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_select_database_invalid_sqlite(self, client, monkeypatch, tmp_path):
        """POST /api/databases/select returns 400 for invalid SQLite file."""
        import backend.routers.databases as db_router

        bad_db = tmp_path / "bad.db"
        bad_db.write_text("not a sqlite file")

        monkeypatch.setattr(db_router, 'PROJECT_DIR', tmp_path)

        response = client.post("/api/databases/select", json={"path": "bad.db"})
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_select_database_success(self, client, monkeypatch, tmp_path):
        """POST /api/databases/select switches to a valid database."""
        import sqlite3
        import backend.deps as deps_module
        import backend.routers.databases as db_router

        # Create a valid SQLite db with features table
        new_db = tmp_path / "new.db"
        conn = sqlite3.connect(str(new_db))
        conn.execute("""CREATE TABLE features (
            id INTEGER PRIMARY KEY,
            priority INTEGER NOT NULL,
            category VARCHAR(100) NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            steps JSON NOT NULL,
            passes BOOLEAN NOT NULL DEFAULT 0,
            in_progress BOOLEAN NOT NULL DEFAULT 0
        )""")
        conn.close()

        monkeypatch.setattr(db_router, 'PROJECT_DIR', tmp_path)
        # Prevent switch_database from actually modifying global state
        monkeypatch.setattr(db_router, 'switch_database', lambda path: None)

        response = client.post("/api/databases/select", json={"path": "new.db"})
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Database switched successfully"
        assert "new.db" in data["active_database"]


