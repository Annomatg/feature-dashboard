"""
JSON to SQLite Migration
========================

Automatically migrates existing feature_list.json files to SQLite database.
"""

import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session, sessionmaker

from api.database import CategoryToken, DescriptionToken, Feature, NameToken, create_database
from api.tokens import normalize_tokens


def tokenize_name(name: str) -> list:
    """Tokenize a feature name into normalized word tokens.

    Delegates to the shared :func:`api.tokens.normalize_tokens` function.

    Args:
        name: Raw feature name string.

    Returns:
        List of normalized token strings.
    """
    return normalize_tokens(name)


def backfill_name_tokens(session_maker: sessionmaker) -> int:
    """Populate name_tokens from all existing feature names.

    Reads every row from features.name, tokenizes the text, and upserts
    the aggregated usage counts into name_tokens.

    Idempotent: if name_tokens already contains rows the function returns -1
    and makes no changes.

    Args:
        session_maker: SQLAlchemy session factory bound to the target DB.

    Returns:
        Number of distinct tokens inserted, or -1 if the table was not empty
        (guard skipped the backfill).
    """
    session: Session = session_maker()
    try:
        existing_count = session.query(NameToken).count()
        if existing_count > 0:
            print(f"name_tokens already has {existing_count} tokens, skipping backfill")
            return -1

        names = [row[0] for row in session.query(Feature.name).all()]

        token_counts: Counter = Counter()
        for name in names:
            token_counts.update(tokenize_name(name))

        for token, count in token_counts.items():
            session.add(NameToken(token=token, usage_count=count))

        session.commit()
        total = len(token_counts)
        print(f"Backfilled {total} distinct tokens into name_tokens")
        return total
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def tokenize_description(description: str) -> list:
    """Tokenize a feature description into normalized word tokens.

    Delegates to the shared :func:`api.tokens.normalize_tokens` function.

    Args:
        description: Raw feature description string.

    Returns:
        List of normalized token strings.
    """
    return normalize_tokens(description)


def backfill_description_tokens(session_maker: sessionmaker) -> int:
    """Populate description_tokens from all existing feature descriptions.

    Reads every row from features.description, tokenizes the text, and upserts
    the aggregated usage counts into description_tokens.

    Idempotent: if description_tokens already contains rows the function returns
    -1 and makes no changes.

    Args:
        session_maker: SQLAlchemy session factory bound to the target DB.

    Returns:
        Number of distinct tokens inserted, or -1 if the table was not empty
        (guard skipped the backfill).
    """
    session: Session = session_maker()
    try:
        existing_count = session.query(DescriptionToken).count()
        if existing_count > 0:
            print(f"description_tokens already has {existing_count} tokens, skipping backfill")
            return -1

        descriptions = [row[0] for row in session.query(Feature.description).all()]

        token_counts: Counter = Counter()
        for desc in descriptions:
            token_counts.update(tokenize_description(desc))

        for token, count in token_counts.items():
            session.add(DescriptionToken(token=token, usage_count=count))

        session.commit()
        total = len(token_counts)
        print(f"Backfilled {total} distinct tokens into description_tokens")
        return total
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def tokenize_category(category: str) -> list:
    """Tokenize a feature category into normalized word tokens.

    Delegates to the shared :func:`api.tokens.normalize_tokens` function.

    Args:
        category: Raw feature category string.

    Returns:
        List of normalized token strings.
    """
    return normalize_tokens(category)


def backfill_category_tokens(session_maker: sessionmaker) -> int:
    """Populate category_tokens from all existing feature categories.

    Reads every row from features.category, tokenizes the text, and upserts
    the aggregated usage counts into category_tokens.

    Idempotent: if category_tokens already contains rows the function returns
    -1 and makes no changes.

    Args:
        session_maker: SQLAlchemy session factory bound to the target DB.

    Returns:
        Number of distinct tokens inserted, or -1 if the table was not empty
        (guard skipped the backfill).
    """
    session: Session = session_maker()
    try:
        existing_count = session.query(CategoryToken).count()
        if existing_count > 0:
            print(f"category_tokens already has {existing_count} tokens, skipping backfill")
            return -1

        categories = [row[0] for row in session.query(Feature.category).all()]

        token_counts: Counter = Counter()
        for cat in categories:
            token_counts.update(tokenize_category(cat))

        for token, count in token_counts.items():
            session.add(CategoryToken(token=token, usage_count=count))

        session.commit()
        total = len(token_counts)
        print(f"Backfilled {total} distinct tokens into category_tokens")
        return total
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def migrate_json_to_sqlite(
    project_dir: Path,
    session_maker: sessionmaker,
) -> bool:
    """
    Detect existing feature_list.json, import to SQLite, rename to backup.

    This function:
    1. Checks if feature_list.json exists
    2. Checks if database already has data (skips if so)
    3. Imports all features from JSON
    4. Renames JSON file to feature_list.json.backup.<timestamp>

    Args:
        project_dir: Directory containing the project
        session_maker: SQLAlchemy session maker

    Returns:
        True if migration was performed, False if skipped
    """
    json_file = project_dir / "feature_list.json"

    if not json_file.exists():
        return False  # No JSON file to migrate

    # Check if database already has data
    session: Session = session_maker()
    try:
        existing_count = session.query(Feature).count()
        if existing_count > 0:
            print(
                f"Database already has {existing_count} features, skipping migration"
            )
            return False
    finally:
        session.close()

    # Load JSON data
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            features_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing feature_list.json: {e}")
        return False
    except IOError as e:
        print(f"Error reading feature_list.json: {e}")
        return False

    if not isinstance(features_data, list):
        print("Error: feature_list.json must contain a JSON array")
        return False

    # Import features into database
    session = session_maker()
    try:
        imported_count = 0
        for i, feature_dict in enumerate(features_data):
            # Handle both old format (no id/priority/name) and new format
            feature = Feature(
                id=feature_dict.get("id", i + 1),
                priority=feature_dict.get("priority", i + 1),
                category=feature_dict.get("category", "uncategorized"),
                name=feature_dict.get("name", f"Feature {i + 1}"),
                description=feature_dict.get("description", ""),
                steps=feature_dict.get("steps", []),
                passes=feature_dict.get("passes", False),
                in_progress=feature_dict.get("in_progress", False),
            )
            session.add(feature)
            imported_count += 1

        session.commit()

        # Verify import
        final_count = session.query(Feature).count()
        print(f"Migrated {final_count} features from JSON to SQLite")

    except Exception as e:
        session.rollback()
        print(f"Error during migration: {e}")
        return False
    finally:
        session.close()

    # Rename JSON file to backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = project_dir / f"feature_list.json.backup.{timestamp}"

    try:
        shutil.move(json_file, backup_file)
        print(f"Original JSON backed up to: {backup_file.name}")
    except IOError as e:
        print(f"Warning: Could not backup JSON file: {e}")
        # Continue anyway - the data is in the database

    return True


def migrate_all_dashboards(config_path: Optional[Path] = None) -> None:
    """
    Run schema migrations on all databases listed in dashboards.json.

    Reads the dashboards config and calls create_database() on each path
    so that every DB is brought up to the latest schema version.

    Args:
        config_path: Path to dashboards.json (defaults to the feature-dashboard root)
    """
    _feature_dashboard_dir = Path(__file__).parent.parent

    if config_path is None:
        config_path = _feature_dashboard_dir / "dashboards.json"

    if not config_path.exists():
        print(f"No dashboards config found at {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        dashboards = json.load(f)

    for db_config in dashboards:
        db_path_str = db_config.get("path", "")
        db_path = Path(db_path_str)

        # Resolve relative paths against feature-dashboard directory
        if not db_path.is_absolute():
            db_path = _feature_dashboard_dir / db_path

        name = db_config.get("name", db_path_str)

        if not db_path.exists():
            print(f"Skipping '{name}': DB not found at {db_path}")
            continue

        print(f"Migrating '{name}'...")
        try:
            _, session_maker = create_database(db_path.parent, db_filename=db_path.name)
            print(f"  OK: {db_path}")
            backfill_name_tokens(session_maker)
            backfill_description_tokens(session_maker)
            backfill_category_tokens(session_maker)
        except Exception as e:
            print(f"  ERROR: {e}")


def export_to_json(
    project_dir: Path,
    session_maker: sessionmaker,
    output_file: Optional[Path] = None,
) -> Path:
    """
    Export features from database back to JSON format.

    Useful for debugging or if you need to revert to the old format.

    Args:
        project_dir: Directory containing the project
        session_maker: SQLAlchemy session maker
        output_file: Output file path (default: feature_list_export.json)

    Returns:
        Path to the exported file
    """
    if output_file is None:
        output_file = project_dir / "feature_list_export.json"

    session: Session = session_maker()
    try:
        features = (
            session.query(Feature)
            .order_by(Feature.priority.asc(), Feature.id.asc())
            .all()
        )

        features_data = [f.to_dict() for f in features]

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(features_data, f, indent=2)

        print(f"Exported {len(features_data)} features to {output_file}")
        return output_file

    finally:
        session.close()
