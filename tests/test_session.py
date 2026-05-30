"""
# PROMPT: Generate pytest-asyncio tests for app.session helper functions
"""

import pytest
from datetime import datetime, timezone

from app.db import AsyncSessionLocal
from app.session import (
    count_unique_sessions,
    get_session_summary,
    get_visitor_zone_presence,
    detect_reentry_inflation
)

pytestmark = pytest.mark.asyncio

VALID_STORE = "STORE_ST1008"

class TestSessionHelpers:
    async def test_empty_store_session_helpers(self):
        async with AsyncSessionLocal() as db:
            cnt = await count_unique_sessions(db, "STORE_EMPTY_999")
            assert cnt == 0
            
            summary = await get_session_summary(db, "STORE_EMPTY_999")
            assert summary == []
            
            inflation = await detect_reentry_inflation(db, "STORE_EMPTY_999")
            assert inflation["total_visitors"] == 0
            assert inflation["reentry_visitors"] == 0
            
            presence = await get_visitor_zone_presence(
                db, "STORE_EMPTY_999", "VIS_01", "ZONE_01", 300, datetime.now(timezone.utc)
            )
            assert presence is False

    async def test_valid_store_session_helpers(self, async_client, sample_events):
        # We use async_client just to ingest the sample events easily
        await async_client.post("/events/ingest", json={"events": sample_events})
        
        async with AsyncSessionLocal() as db:
            cnt = await count_unique_sessions(db, VALID_STORE)
            assert isinstance(cnt, int)
            
            summary = await get_session_summary(db, VALID_STORE)
            assert isinstance(summary, list)
            
            inflation = await detect_reentry_inflation(db, VALID_STORE)
            assert "reentry_rate" in inflation
            
            presence = await get_visitor_zone_presence(
                db, VALID_STORE, "VIS_1", "SKINCARE", 300, datetime.now(timezone.utc)
            )
            assert isinstance(presence, bool)
