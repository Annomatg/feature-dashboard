"""
Test script for multi-database API endpoints.
Run this after starting DevServer to test the new endpoints.
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_root():
    """Test root endpoint shows new database endpoints."""
    print("Testing root endpoint...")
    response = requests.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(json.dumps(data, indent=2))

    # Check new endpoints are listed
    assert "databases" in data["endpoints"]
    assert "databases_active" in data["endpoints"]
    assert "databases_select" in data["endpoints"]
    print("✓ Root endpoint includes database endpoints\n")


def test_get_databases():
    """Test GET /api/databases."""
    print("Testing GET /api/databases...")
    response = requests.get(f"{BASE_URL}/api/databases")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(json.dumps(data, indent=2))

    # Should return list with at least features.db
    assert isinstance(data, list)
    assert len(data) > 0
    assert any(db["path"] == "features.db" for db in data)
    print("✓ Databases list retrieved successfully\n")


def test_get_active_database():
    """Test GET /api/databases/active."""
    print("Testing GET /api/databases/active...")
    response = requests.get(f"{BASE_URL}/api/databases/active")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(json.dumps(data, indent=2))

    # Should return current database info
    assert "path" in data
    assert "is_active" in data
    assert data["is_active"] == True
    print("✓ Active database retrieved successfully\n")


def test_select_database():
    """Test POST /api/databases/select."""
    print("Testing POST /api/databases/select...")

    # Try to select features.db (should already be active)
    payload = {"path": "features.db"}
    response = requests.post(f"{BASE_URL}/api/databases/select", json=payload)
    print(f"Status: {response.status_code}")
    data = response.json()
    print(json.dumps(data, indent=2))

    # Should succeed
    assert response.status_code == 200
    assert "message" in data
    print("✓ Database selection works\n")

    # Try to select non-existent database
    print("Testing invalid database path...")
    payload = {"path": "nonexistent.db"}
    response = requests.post(f"{BASE_URL}/api/databases/select", json=payload)
    print(f"Status: {response.status_code}")

    # Should fail with 404
    assert response.status_code == 404
    print("✓ Invalid path correctly rejected\n")


def test_features_still_work():
    """Test that existing features endpoints still work."""
    print("Testing existing features endpoints...")

    # Test stats
    response = requests.get(f"{BASE_URL}/api/features/stats")
    print(f"Stats status: {response.status_code}")
    stats = response.json()
    print(f"  Total features: {stats['total']}")
    assert response.status_code == 200

    # Test features list
    response = requests.get(f"{BASE_URL}/api/features")
    print(f"Features status: {response.status_code}")
    features = response.json()
    print(f"  Retrieved {len(features)} features")
    assert response.status_code == 200

    print("✓ Existing features endpoints still work\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Multi-Database API Test Suite")
    print("=" * 60)
    print()

    try:
        test_root()
        test_get_databases()
        test_get_active_database()
        test_select_database()
        test_features_still_work()

        print("=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to backend server")
        print("Make sure DevServer is running:")
        print("  dotnet run --project DevServer")
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
