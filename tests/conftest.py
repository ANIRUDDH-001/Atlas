"""
Shared pytest fixtures for Store Intelligence test suite.

Database strategy:
- Unit tests (default): in-memory SQLite via aiosqlite
- Integration tests: live PostgreSQL (set TEST_USE_LIVE_DB=1)

All test files include a PROMPT block header per hackathon requirements.
"""
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"
# Also mock Redis URL so it doesn't fail on cache warm-up if Redis is not running
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

import json
import pytest
import asyncio
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture(scope="session", autouse=True)
def mock_redis_and_sqlite():
    from app.main import app
    from app.cache import get_redis
    from unittest.mock import AsyncMock
    mock_redis = AsyncMock()
    app.dependency_overrides[get_redis] = lambda: mock_redis

    import sys
    # Also patch the actual function so app.health.py can call it directly
    from unittest.mock import patch
    patcher = patch("app.health.get_redis", new_callable=AsyncMock, return_value=mock_redis)
    patcher.start()
    yield
    patcher.stop()

@pytest.fixture(scope="function", autouse=True)
def setup_sqlite_schema():
    from sqlalchemy import create_engine, text, event
    import re
    sync_engine = create_engine("sqlite:///test.db")
    
    @event.listens_for(sync_engine, "before_cursor_execute", retval=True)
    def translate_postgres_to_sqlite(conn, cursor, statement, parameters, context, executemany):
        statement = re.sub(r'([a-zA-Z0-9_\.]*timestamp)::date', r'DATE(\1)', statement)
        statement = re.sub(r"NOW\(\)\s*-\s*INTERVAL\s*'5 minutes'", r"datetime('now', '-5 minutes')", statement)
        statement = statement.replace("NOW()", "datetime('now')")
        statement = re.sub(r"NOW\(\)\s*-\s*INTERVAL\s*'1 minute'\s*\*\s*(?:\?|:[a-zA-Z0-9_]+)", r"datetime('now', '-' || ? || ' minutes')", statement)
        statement = re.sub(r"([a-zA-Z0-9_\.]*timestamp|\?|:[a-zA-Z0-9_]+)\s*-\s*INTERVAL\s*'1 second'\s*\*\s*(?:\?|:[a-zA-Z0-9_]+)", r"datetime(\1, '-' || ? || ' seconds')", statement)
        statement = re.sub(r"BOOL_OR\(([\s\S]*?)\)", r"MAX(\1)", statement)
        return statement, parameters
        
    with sync_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS events;"))
        conn.execute(text("DROP TABLE IF EXISTS pos_transactions;"))
        conn.execute(text("""
            CREATE TABLE events (
                event_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                visitor_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                zone_id TEXT,
                dwell_ms INTEGER NOT NULL DEFAULT 0,
                is_staff BOOLEAN NOT NULL DEFAULT FALSE,
                confidence FLOAT,
                queue_depth INTEGER,
                sku_zone TEXT,
                session_seq INTEGER,
                ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("""
            CREATE TABLE pos_transactions (
                transaction_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                basket_value FLOAT
            );
        """))
        
    from app.db import engine
    @event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def translate_postgres_to_sqlite_async(conn, cursor, statement, parameters, context, executemany):
        original = statement
        statement = re.sub(r'([a-zA-Z0-9_\.]*timestamp)::date', r'DATE(\1)', statement)
        statement = re.sub(r"NOW\(\)\s*-\s*INTERVAL\s*'5 minutes'", r"datetime('now', '-5 minutes')", statement)
        statement = statement.replace("NOW()", "datetime('now')")
        statement = re.sub(r"NOW\(\)\s*-\s*INTERVAL\s*'1 minute'\s*\*\s*(?:\?|:[a-zA-Z0-9_]+)", r"datetime('now', '-' || ? || ' minutes')", statement)
        statement = re.sub(r"([a-zA-Z0-9_\.]*timestamp|\?|:[a-zA-Z0-9_]+)\s*-\s*INTERVAL\s*'1 second'\s*\*\s*(?:\?|:[a-zA-Z0-9_]+)", r"datetime(\1, '-' || ? || ' seconds')", statement)
        statement = re.sub(r"BOOL_OR\(([\s\S]*?)\)", r"MAX(\1)", statement)
        if "INTERVAL" in statement:
            print("FAILED TO TRANSLATE INTERVAL:", original)
            print("NEW STATEMENT:", statement)
        return statement, parameters
        statement = re.sub(r"NOW\(\)\s*-\s*INTERVAL\s*'5 minutes'", r"datetime('now', '-5 minutes')", statement)
        statement = statement.replace("NOW()", "datetime('now')")
        statement = re.sub(r"NOW\(\)\s*-\s*INTERVAL\s*'1 minute'\s*\*\s*(?:\?|:[a-zA-Z0-9_]+)", r"datetime('now', '-' || ? || ' minutes')", statement)
        statement = re.sub(r"([a-zA-Z0-9_\.]*timestamp|\?|:[a-zA-Z0-9_]+)\s*-\s*INTERVAL\s*'1 second'\s*\*\s*(?:\?|:[a-zA-Z0-9_]+)", r"datetime(\1, '-' || ? || ' seconds')", statement)
        return statement, parameters


def _patch_timestamps(events):
    now_str = datetime.now(timezone.utc).isoformat()
    for e in events:
        if "timestamp" in e:
            e["timestamp"] = now_str
    return events

# ── Event fixtures ────────────────────────────────────────────────────────────
@pytest.fixture
def sample_events():
    lines = (FIXTURES_DIR / "sample_events.jsonl").read_text().splitlines()
    return _patch_timestamps([json.loads(l) for l in lines if l.strip()])

@pytest.fixture
def staff_only_events():
    lines = (FIXTURES_DIR / "staff_events.jsonl").read_text().splitlines()
    return _patch_timestamps([json.loads(l) for l in lines if l.strip()])

@pytest.fixture
def reentry_events():
    lines = (FIXTURES_DIR / "reentry_events.jsonl").read_text().splitlines()
    return _patch_timestamps([json.loads(l) for l in lines if l.strip()])

# ── App client ────────────────────────────────────────────────────────────────
@pytest.fixture
async def async_client():
    """
    AsyncClient pointed at the FastAPI app.
    Uses ASGI transport — no live server needed for unit tests.
    """
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=10.0,
    ) as client:
        yield client

# ── Convenience fixtures ──────────────────────────────────────────────────────
@pytest.fixture
def valid_single_event():
    """One valid ENTRY event for STORE_ST1008."""
    import uuid
    return {
        "event_id":   str(uuid.uuid4()),
        "store_id":   "STORE_ST1008",
        "camera_id":  "CAM_ENTRY_01",
        "visitor_id": "VIS_abc123",
        "event_type": "ENTRY",
        "timestamp":  "2026-03-03T14:22:10Z",
        "zone_id":    None,
        "dwell_ms":   0,
        "is_staff":   False,
        "confidence": 0.91,
        "metadata":   {"queue_depth": None, "sku_zone": None, "session_seq": 1},
    }

@pytest.fixture
def malformed_event():
    """An event missing required fields."""
    return {"event_id": "not-a-uuid", "store_id": "STORE_ST1008"}
