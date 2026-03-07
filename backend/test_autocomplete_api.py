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


class TestAutocompleteNameEndpoint:
    """Tests for GET /api/autocomplete/name"""

    def test_prefix_too_short_returns_empty(self, client):
        """Returns empty suggestions when prefix is shorter than 3 characters."""
        for prefix in ["", "a", "fe"]:
            response = client.get(f"/api/autocomplete/name?prefix={prefix}")
            assert response.status_code == 200
            assert response.json() == {"suggestions": []}

    def test_prefix_exact_three_chars_returns_results(self, client):
        """Returns suggestions when prefix is exactly 3 characters."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Seed name_tokens directly
        session = main_module.get_session()
        try:
            session.add(NameToken(token="feature", usage_count=5))
            session.add(NameToken(token="feat", usage_count=3))
            session.add(NameToken(token="fetch", usage_count=1))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/name?prefix=fea")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert "feature" in data["suggestions"]
        assert "feat" in data["suggestions"]
        # "fetch" does not start with "fea"
        assert "fetch" not in data["suggestions"]

    def test_no_match_returns_empty_array(self, client):
        """Returns empty suggestions when no token matches the prefix."""
        response = client.get("/api/autocomplete/name?prefix=xyz")
        assert response.status_code == 200
        assert response.json() == {"suggestions": []}

    def test_results_ordered_by_usage_count_desc(self, client):
        """Suggestions are ordered by usage_count descending."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(NameToken(token="backend", usage_count=10))
            session.add(NameToken(token="backlog", usage_count=20))
            session.add(NameToken(token="backfill", usage_count=5))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/name?prefix=bac")
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        # backlog(20) > backend(10) > backfill(5)
        assert suggestions.index("backlog") < suggestions.index("backend")
        assert suggestions.index("backend") < suggestions.index("backfill")

    def test_returns_at_most_five_suggestions(self, client):
        """Returns no more than 5 suggestions."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            for i in range(8):
                session.add(NameToken(token=f"token{i:02d}", usage_count=i))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/name?prefix=tok")
        assert response.status_code == 200
        assert len(response.json()["suggestions"]) <= 5

    def test_missing_prefix_returns_empty(self, client):
        """Returns empty suggestions when prefix parameter is omitted."""
        response = client.get("/api/autocomplete/name")
        assert response.status_code == 200
        assert response.json() == {"suggestions": []}


class TestAutocompleteDescriptionEndpoint:
    """Tests for GET /api/autocomplete/description"""

    def test_prefix_too_short_returns_empty(self, client):
        """Returns empty suggestions when prefix is shorter than 3 characters."""
        for prefix in ["", "a", "de"]:
            response = client.get(f"/api/autocomplete/description?prefix={prefix}")
            assert response.status_code == 200
            assert response.json() == {"suggestions": []}

    def test_prefix_exact_three_chars_returns_results(self, client):
        """Returns suggestions when prefix is exactly 3 characters."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(DescriptionToken(token="description", usage_count=5))
            session.add(DescriptionToken(token="descending", usage_count=3))
            session.add(DescriptionToken(token="desktop", usage_count=1))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/description?prefix=des")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert "description" in data["suggestions"]
        assert "descending" in data["suggestions"]
        assert "desktop" in data["suggestions"]

    def test_no_match_returns_empty_array(self, client):
        """Returns empty suggestions when no token matches the prefix."""
        response = client.get("/api/autocomplete/description?prefix=xyz")
        assert response.status_code == 200
        assert response.json() == {"suggestions": []}

    def test_results_ordered_by_usage_count_desc(self, client):
        """Suggestions are ordered by usage_count descending."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(DescriptionToken(token="implement", usage_count=10))
            session.add(DescriptionToken(token="improvement", usage_count=20))
            session.add(DescriptionToken(token="import", usage_count=5))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/description?prefix=imp")
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        # improvement(20) > implement(10) > import(5)
        assert suggestions.index("improvement") < suggestions.index("implement")
        assert suggestions.index("implement") < suggestions.index("import")

    def test_returns_at_most_five_suggestions(self, client):
        """Returns no more than 5 suggestions."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            for i in range(8):
                session.add(DescriptionToken(token=f"word{i:02d}x", usage_count=i))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/description?prefix=wor")
        assert response.status_code == 200
        assert len(response.json()["suggestions"]) <= 5

    def test_missing_prefix_returns_empty(self, client):
        """Returns empty suggestions when prefix parameter is omitted."""
        response = client.get("/api/autocomplete/description")
        assert response.status_code == 200
        assert response.json() == {"suggestions": []}


class TestAutocompleteCategoryEndpoint:
    """Tests for GET /api/autocomplete/category"""

    def test_prefix_too_short_returns_empty(self, client):
        """Returns empty suggestions when prefix is shorter than 3 characters."""
        for prefix in ["", "a", "fr"]:
            response = client.get(f"/api/autocomplete/category?prefix={prefix}")
            assert response.status_code == 200
            assert response.json() == {"suggestions": []}

    def test_prefix_exact_three_chars_returns_results(self, client):
        """Returns suggestions when prefix is exactly 3 characters."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Seed category_tokens directly
        session = main_module.get_session()
        try:
            session.add(CategoryToken(token="category", usage_count=5))
            session.add(CategoryToken(token="cat", usage_count=3))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/category?prefix=cat")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert "category" in data["suggestions"]
        assert "cat" in data["suggestions"]

    def test_no_match_returns_empty_array(self, client):
        """Returns empty suggestions when no token matches the prefix."""
        response = client.get("/api/autocomplete/category?prefix=xyz")
        assert response.status_code == 200
        assert response.json() == {"suggestions": []}

    def test_results_ordered_by_usage_count_desc(self, client):
        """Suggestions are ordered by usage_count descending."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(CategoryToken(token="backend", usage_count=10))
            session.add(CategoryToken(token="backlog", usage_count=20))
            session.add(CategoryToken(token="backup", usage_count=5))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/category?prefix=back")
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        # backlog(20) > backend(10) > backup(5)
        assert "backlog" in suggestions
        assert "backend" in suggestions
        assert suggestions.index("backlog") < suggestions.index("backend")
        assert suggestions.index("backend") < suggestions.index("backup")

    def test_returns_at_most_five_suggestions(self, client):
        """Returns no more than 5 suggestions."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            for i in range(8):
                session.add(CategoryToken(token=f"cat{i:02d}", usage_count=i))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/category?prefix=cat")
        assert response.status_code == 200
        assert len(response.json()["suggestions"]) <= 5

    def test_missing_prefix_returns_empty(self, client):
        """Returns empty suggestions when prefix parameter is omitted."""
        response = client.get("/api/autocomplete/category")
        assert response.status_code == 200
        assert response.json() == {"suggestions": []}

    def test_create_feature_populates_category_tokens(self, client):
        """Creating a feature populates category_tokens with tokens from the category."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Create a feature with a category
        response = client.post("/api/features", json={
            "name": "Test Feature",
            "description": "Test description",
            "category": "Frontend UI",
            "steps": ["Step 1"]
        })
        assert response.status_code == 201

        # Check category_tokens were populated
        session = main_module.get_session()
        try:
            tokens = {row.token: row.usage_count for row in session.query(CategoryToken).all()}
            # "frontend" and "ui" are the tokens from "Frontend UI"
            assert "frontend" in tokens or "ui" in tokens
        finally:
            session.close()

    def test_update_feature_category_populates_category_tokens(self, client):
        """Updating a feature's category populates category_tokens with new tokens."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Create a feature
        response = client.post("/api/features", json={
            "name": "Test Feature",
            "description": "Test description",
            "category": "Backend",
            "steps": ["Step 1"]
        })
        assert response.status_code == 201
        feature_id = response.json()["id"]

        # Update the category
        response = client.put(f"/api/features/{feature_id}", json={
            "category": "API Service"
        })
        assert response.status_code == 200

        # Check category_tokens were populated with new tokens
        session = main_module.get_session()
        try:
            tokens = {row.token: row.usage_count for row in session.query(CategoryToken).all()}
            # "api" and "service" are the tokens from "API Service"
            assert "api" in tokens or "service" in tokens
        finally:
            session.close()


class TestAutocompleteTwoWordSuggestions:
    """Tests for two-word (bigram) suggestions in autocomplete endpoints."""

    def test_name_autocomplete_returns_two_word_suggestion_when_bigram_exists(self, client):
        """Returns 'token nextword' when a bigram exists for the matched token."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(NameToken(token="dashboard", usage_count=10))
            session.add(NameBigram(word1="dashboard", word2="widget", usage_count=5))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/name?prefix=das")
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert "dashboard widget" in suggestions

    def test_name_autocomplete_returns_single_word_when_no_bigram(self, client):
        """Returns just the token when no bigram exists for it."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(NameToken(token="singleword", usage_count=5))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/name?prefix=sin")
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert "singleword" in suggestions
        # No second word should be appended
        assert not any(" " in s and s.startswith("singleword") for s in suggestions)

    def test_name_autocomplete_bigram_uses_highest_count_next_word(self, client):
        """Returns the bigram with the highest usage_count as the next word."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(NameToken(token="config", usage_count=10))
            session.add(NameBigram(word1="config", word2="file", usage_count=3))
            session.add(NameBigram(word1="config", word2="panel", usage_count=20))
            session.add(NameBigram(word1="config", word2="screen", usage_count=1))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/name?prefix=con")
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        # "panel" has the highest count (20) so "config panel" should appear
        assert "config panel" in suggestions

    def test_description_autocomplete_returns_two_word_suggestion_when_bigram_exists(self, client):
        """Description endpoint returns 'token nextword' when a bigram exists."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(DescriptionToken(token="implement", usage_count=15))
            session.add(DescriptionBigram(word1="implement", word2="feature", usage_count=8))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/description?prefix=imp")
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert "implement feature" in suggestions

    def test_description_autocomplete_returns_single_word_when_no_bigram(self, client):
        """Description endpoint returns just the token when no bigram exists."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(DescriptionToken(token="standalone", usage_count=5))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/description?prefix=sta")
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert "standalone" in suggestions
        assert not any(" " in s and s.startswith("standalone") for s in suggestions)

    def test_create_feature_populates_name_bigrams(self, client):
        """Creating a feature populates name_bigrams with consecutive word pairs."""
        import backend.main as main_module
        import backend.deps as deps_module

        response = client.post("/api/features", json={
            "name": "Kanban Board Feature",
            "description": "A test feature",
            "category": "UI",
            "steps": []
        })
        assert response.status_code == 201

        session = main_module.get_session()
        try:
            bigrams = {(b.word1, b.word2) for b in session.query(NameBigram).all()}
            # "kanban board feature" → ("kanban","board"), ("board","feature")
            assert ("kanban", "board") in bigrams
            assert ("board", "feature") in bigrams
        finally:
            session.close()

    def test_create_feature_populates_description_bigrams(self, client):
        """Creating a feature populates description_bigrams with consecutive word pairs."""
        import backend.main as main_module
        import backend.deps as deps_module

        response = client.post("/api/features", json={
            "name": "Test Feature",
            "description": "allow user authentication via OAuth",
            "category": "Auth",
            "steps": []
        })
        assert response.status_code == 201

        session = main_module.get_session()
        try:
            bigrams = {(b.word1, b.word2) for b in session.query(DescriptionBigram).all()}
            # "allow user authentication via oauth" → pairs include ("allow","user"), ("user","authentication")
            assert ("allow", "user") in bigrams
            assert ("user", "authentication") in bigrams
        finally:
            session.close()

    def test_update_feature_name_populates_name_bigrams(self, client):
        """Updating a feature name populates name_bigrams with new consecutive pairs."""
        import backend.main as main_module
        import backend.deps as deps_module

        create_response = client.post("/api/features", json={
            "name": "Old Name",
            "description": "desc",
            "category": "Test",
            "steps": []
        })
        assert create_response.status_code == 201
        feature_id = create_response.json()["id"]

        update_response = client.put(f"/api/features/{feature_id}", json={
            "name": "Settings Page Navigation"
        })
        assert update_response.status_code == 200

        session = main_module.get_session()
        try:
            bigrams = {(b.word1, b.word2) for b in session.query(NameBigram).all()}
            assert ("settings", "page") in bigrams
            assert ("page", "navigation") in bigrams
        finally:
            session.close()

    def test_mixed_results_some_with_bigrams_some_without(self, client):
        """When multiple tokens match, each gets a next word only if its bigram exists."""
        import backend.main as main_module
        import backend.deps as deps_module

        session = main_module.get_session()
        try:
            session.add(NameToken(token="workflow", usage_count=10))
            session.add(NameToken(token="worker", usage_count=8))
            # Only "workflow" has a bigram
            session.add(NameBigram(word1="workflow", word2="manager", usage_count=5))
            session.commit()
        finally:
            session.close()

        response = client.get("/api/autocomplete/name?prefix=wor")
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        assert "workflow manager" in suggestions
        assert "worker" in suggestions


class TestAutocompletePerformance:
    """Performance tests ensuring autocomplete endpoints respond in < 20ms."""

    @pytest.fixture
    def perf_client(self, monkeypatch):
        """Test client pre-loaded with 1000 tokens for performance testing."""
        import backend.main as main_module
        import backend.deps as deps_module

        temp_dir = tempfile.mkdtemp()
        temp_db_path = Path(temp_dir) / "features.db"
        engine, session_maker = create_database(Path(temp_dir))

        session = session_maker()
        try:
            session.add(Feature(id=1, priority=100, category="Test", name="Feature 1",
                                description="Test", steps=["Step 1"], passes=False, in_progress=False))
            for i in range(1000):
                session.add(NameToken(token=f"perf{i:04d}", usage_count=i))
            for i in range(1000):
                session.add(DescriptionToken(token=f"desc{i:04d}", usage_count=i))
            session.commit()
        finally:
            session.close()

        monkeypatch.setattr(deps_module, '_session_maker', session_maker)
        monkeypatch.setattr(deps_module, '_current_db_path', temp_db_path)
        monkeypatch.setattr(main_module.asyncio, 'create_task',
                            lambda coro: (coro.close(), None)[1])

        yield TestClient(app), engine

        engine.dispose()
        try:
            shutil.rmtree(temp_dir)
        except PermissionError:
            pass

    def test_name_endpoint_executes_single_query(self, perf_client):
        """Name autocomplete endpoint executes exactly one SQL SELECT query."""
        from sqlalchemy import event as sa_event

        client, engine = perf_client
        query_count = [0]

        def count_selects(conn, cursor, statement, parameters, context, executemany):
            if statement.strip().upper().startswith('SELECT'):
                query_count[0] += 1

        sa_event.listen(engine, 'before_cursor_execute', count_selects)
        try:
            response = client.get("/api/autocomplete/name?prefix=per")
            assert response.status_code == 200
        finally:
            sa_event.remove(engine, 'before_cursor_execute', count_selects)

        assert query_count[0] == 1, f"Expected 1 SELECT query, got {query_count[0]}"

    def test_description_endpoint_executes_single_query(self, perf_client):
        """Description autocomplete endpoint executes exactly one SQL SELECT query."""
        from sqlalchemy import event as sa_event

        client, engine = perf_client
        query_count = [0]

        def count_selects(conn, cursor, statement, parameters, context, executemany):
            if statement.strip().upper().startswith('SELECT'):
                query_count[0] += 1

        sa_event.listen(engine, 'before_cursor_execute', count_selects)
        try:
            response = client.get("/api/autocomplete/description?prefix=des")
            assert response.status_code == 200
        finally:
            sa_event.remove(engine, 'before_cursor_execute', count_selects)

        assert query_count[0] == 1, f"Expected 1 SELECT query, got {query_count[0]}"

    def test_name_endpoint_responds_under_20ms(self, perf_client):
        """Name autocomplete endpoint responds in < 20ms for warm requests."""
        import time

        client, _ = perf_client

        # Warm-up to prime SQLite page cache and Python import caches
        client.get("/api/autocomplete/name?prefix=per")

        times = []
        for _ in range(5):
            start = time.perf_counter()
            response = client.get("/api/autocomplete/name?prefix=per")
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert response.status_code == 200

        avg_ms = sum(times) / len(times)
        assert avg_ms < 20, f"Average response time {avg_ms:.1f}ms exceeds 20ms limit"

    def test_description_endpoint_responds_under_20ms(self, perf_client):
        """Description autocomplete endpoint responds in < 20ms for warm requests."""
        import time

        client, _ = perf_client

        # Warm-up to prime SQLite page cache and Python import caches
        client.get("/api/autocomplete/description?prefix=des")

        times = []
        for _ in range(5):
            start = time.perf_counter()
            response = client.get("/api/autocomplete/description?prefix=des")
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert response.status_code == 200

        avg_ms = sum(times) / len(times)
        assert avg_ms < 20, f"Average response time {avg_ms:.1f}ms exceeds 20ms limit"

