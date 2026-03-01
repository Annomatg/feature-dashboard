/**
 * Test Backend Startup Script
 * ============================
 *
 * Sets up test database and starts backend server for E2E tests.
 */

import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '../..');
const testDbPath = path.join(projectRoot, 'features.test.db');
const pythonPath = path.join(projectRoot, 'venv', 'Scripts', 'python.exe');

console.log('Setting up test environment...');

// Remove existing test database
if (fs.existsSync(testDbPath)) {
  fs.unlinkSync(testDbPath);
  console.log('[OK] Removed existing test database');
}

// Create and seed test database
const setupScript = `
import sys
from pathlib import Path
sys.path.insert(0, r'${projectRoot}')

from api.database import Feature, NameToken, DescriptionToken
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.database import Base

# Create test database directly (not using create_database helper)
test_db_path = Path(r'${testDbPath}')
db_url = f"sqlite:///{test_db_path.as_posix()}"
engine = create_engine(db_url, connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Seed test data
session = SessionLocal()

test_features = [
    Feature(
        id=1,
        priority=1,
        category='Backend',
        name='Test Feature with Description',
        description='This is a test feature with a description',
        steps=['Step 1', 'Step 2'],
        passes=False,
        in_progress=False
    ),
    Feature(
        id=2,
        priority=2,
        category='Frontend',
        name='Test Feature in Progress',
        description='This feature is currently being worked on',
        steps=['Step 1', 'Step 2', 'Step 3'],
        passes=False,
        in_progress=True
    ),
    Feature(
        id=3,
        priority=3,
        category='Backend',
        name='Completed Test Feature',
        description='This feature is done',
        steps=['Step 1'],
        passes=True,
        in_progress=False
    ),
]

for feature in test_features:
    session.add(feature)

# Seed name tokens for autocomplete ghost-text tests
name_tokens = [
    NameToken(token='Feature', usage_count=10),
    NameToken(token='Frontend', usage_count=8),
    NameToken(token='Backend', usage_count=7),
    NameToken(token='Authentication', usage_count=6),
    NameToken(token='Dashboard', usage_count=5),
    NameToken(token='Configuration', usage_count=4),
    NameToken(token='Management', usage_count=3),
]
for token in name_tokens:
    session.add(token)

# Seed description tokens for autocomplete ghost-text tests
description_tokens = [
    DescriptionToken(token='feature', usage_count=10),
    DescriptionToken(token='description', usage_count=8),
    DescriptionToken(token='implement', usage_count=7),
    DescriptionToken(token='integration', usage_count=6),
    DescriptionToken(token='backend', usage_count=5),
    DescriptionToken(token='frontend', usage_count=4),
    DescriptionToken(token='authentication', usage_count=3),
]
for token in description_tokens:
    session.add(token)

session.commit()
session.close()

print('[OK] Test database created and seeded')
`;

const setupDb = spawn(pythonPath, ['-c', setupScript], { cwd: projectRoot });

setupDb.stdout.on('data', (data) => process.stdout.write(data));
setupDb.stderr.on('data', (data) => process.stderr.write(data));

setupDb.on('close', (code) => {
  if (code !== 0) {
    console.error('[ERROR] Test database setup failed');
    process.exit(code);
  }

  // Start backend server with test database on port 8001 (to avoid conflict with DevServer on 8000)
  console.log('Starting test backend server on port 8001...');
  const backend = spawn(pythonPath, ['-m', 'uvicorn', 'backend.main:app', '--host', '0.0.0.0', '--port', '8001'], {
    cwd: projectRoot,
    env: { ...process.env, TEST_DB_PATH: testDbPath },
    stdio: 'inherit'
  });

  backend.on('error', (err) => {
    console.error('[ERROR] Failed to start backend:', err);
    process.exit(1);
  });

  // Handle cleanup on exit
  process.on('SIGINT', () => {
    backend.kill();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    backend.kill();
    process.exit(0);
  });
});
