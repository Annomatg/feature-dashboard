import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app
from api.database import create_database, Feature

@pytest.fixture
def test_db():
    """Create an isolated test database."""
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "features.db"

    # Create isolated database
    engine, session_maker = create_database(Path(temp_dir))

    # Seed with test data
    session = session_maker()
    try:
        features = [
            Feature(id=1, priority=100, category="Backend", name="Feature 1",
                   description="Test feature 1", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=2, priority=200, category="Backend", name="Feature 2",
                   description="Test feature 2", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=3, priority=300, category="Frontend", name="Feature 3",
                   description="Test feature 3", steps=["Step 1"], passes=True, in_progress=False),
            Feature(id=4, priority=400, category="Frontend", name="Feature 4",
                   description="Test feature 4", steps=["Step 1"], passes=False, in_progress=True),
        ]
        for feature in features:
            session.add(feature)
        session.commit()
    finally:
        session.close()

    yield session_maker

    # Cleanup - dispose engine to release file locks
    engine.dispose()

    # Remove temp directory
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        # Windows file locking issue - ignore
        pass


@pytest.fixture
def client(monkeypatch):
    """Create a test client with a fully isolated test database.

    Patches both _session_maker and _current_db_path so that all code paths
    — including asyncio monitor tasks that open their own DB connections —
    use the test database instead of the production one.
    """
    import backend.main as main_module
    import backend.deps as deps_module

    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "features.db"
    engine, session_maker = create_database(Path(temp_dir))

    session = session_maker()
    try:
        features = [
            Feature(id=1, priority=100, category="Backend", name="Feature 1",
                    description="Test feature 1", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=2, priority=200, category="Backend", name="Feature 2",
                    description="Test feature 2", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=3, priority=300, category="Frontend", name="Feature 3",
                    description="Test feature 3", steps=["Step 1"], passes=True, in_progress=False),
            Feature(id=4, priority=400, category="Frontend", name="Feature 4",
                    description="Test feature 4", steps=["Step 1"], passes=False, in_progress=True),
        ]
        for f in features:
            session.add(f)
        session.commit()
    finally:
        session.close()

    monkeypatch.setattr(deps_module, '_session_maker', session_maker)
    monkeypatch.setattr(deps_module, '_current_db_path', temp_db_path)
    # Suppress background monitor tasks for endpoint tests — they run against
    # the test DB but complete instantly (mock wait=0), altering state between
    # API calls.  Tests that specifically verify monitor-task behaviour inject
    # their own asyncio.create_task mock via a second monkeypatch.setattr call.
    monkeypatch.setattr(main_module.asyncio, 'create_task',
                        lambda coro: (coro.close(), None)[1])

    yield TestClient(app)

    engine.dispose()
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        pass


@pytest.fixture
def test_db_with_path():
    """Create an isolated test database; yield (session_maker, db_path)."""
    import tempfile
    import shutil
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "features.db"
    engine, session_maker = create_database(Path(temp_dir))

    session = session_maker()
    try:
        features = [
            Feature(id=1, priority=100, category="Backend", name="Feature 1",
                    description="Test feature 1", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=2, priority=200, category="Backend", name="Feature 2",
                    description="Test feature 2", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=3, priority=300, category="Frontend", name="Feature 3",
                    description="Test feature 3", steps=["Step 1"], passes=True, in_progress=False),
            Feature(id=4, priority=400, category="Frontend", name="Feature 4",
                    description="Test feature 4", steps=["Step 1"], passes=False, in_progress=True),
        ]
        for f in features:
            session.add(f)
        session.commit()
    finally:
        session.close()

    yield session_maker, temp_db_path

    engine.dispose()
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        pass
