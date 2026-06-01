import uuid
# PROMPT: "Generate pytest-asyncio tests for GET /stores/{id}/metrics covering:
#  zero-visitor store (unique_visitors=0, conversion_rate=null not 0),
#  data_confidence=LOW when unique_visitors<20,
#  invalid store_id returns HTTP 400,
#  all required fields present in response schema,
#  as_of field is parseable ISO-8601 datetime.
#  Use httpx AsyncClient, pytest-asyncio."
# CHANGES MADE: Added assertion that avg_dwell_by_zone is [] not null for empty store.
#   Added current_queue_depth=0 assertion for empty store (not null).
#   Fixed store ID to STORE_ST1008 in all assertions.
#   AI generated conversion_rate==0.0 assertion - corrected to asserting it is None.

#   Added as_of field check (must be present and parseable datetime).

import pytest
from datetime import datetime

pytestmark = pytest.mark.asyncio

VALID_STORE   = "STORE_ST1008"
INVALID_STORE = "not-a-store"


class TestMetricsSchema:

    async def test_response_has_all_required_fields(self, async_client):
        r = await async_client.get(f"/stores/{VALID_STORE}/metrics")
        assert r.status_code == 200
        body = r.json()
        required = [
            "store_id", "unique_visitors", "conversion_rate",
            "avg_dwell_by_zone", "current_queue_depth",
            "abandonment_rate", "as_of", "data_confidence",
        ]
        for field in required:
            assert field in body, f"Missing field: {field}"

    async def test_as_of_is_parseable_datetime(self, async_client):
        r = await async_client.get(f"/stores/{VALID_STORE}/metrics")
        as_of = r.json()["as_of"]
        datetime.fromisoformat(as_of.replace("Z", "+00:00"))  # Must not raise


class TestZeroTrafficStore:

    async def test_empty_store_unique_visitors_zero(self, async_client):
        r = await async_client.get("/stores/STORE_EMPTY_999/metrics")
        assert r.status_code == 200
        body = r.json()
        assert body["unique_visitors"] == 0
        assert body["conversion_rate"] is None   # null, not 0
        assert body["abandonment_rate"] is None  # null, not 0
        assert body["current_queue_depth"] == 0
        assert body["data_confidence"] == "LOW"

    async def test_empty_store_avg_dwell_is_empty_list(self, async_client):
        r = await async_client.get("/stores/STORE_EMPTY_999/metrics")
        assert r.json()["avg_dwell_by_zone"] == []


class TestInputValidation:

    async def test_invalid_store_id_returns_400(self, async_client):
        r = await async_client.get(f"/stores/{INVALID_STORE}/metrics")
        assert r.status_code == 400

    async def test_valid_store_returns_200(self, async_client):
        r = await async_client.get(f"/stores/{VALID_STORE}/metrics")
        assert r.status_code == 200

class TestQueueDepthDateFilter:
    """Regression tests for P3_F3 — queue_depth must only show today's data."""

    @pytest.mark.asyncio
    async def test_stale_queue_depth_not_returned(self, async_client):
        """Events from yesterday must not inflate today's queue_depth."""
        from datetime import datetime, timedelta

        # Insert a queue event from yesterday
        yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat() + 'Z'
        stale_event = {
            "event_id": "069382e3-34e5-48fc-8147-eccacb5ec12b",
            "store_id": "STORE_TESTQ",
            "camera_id": "CAM_BILLING_01",
            "visitor_id": "VIS_STALE",
            "event_type": "BILLING_QUEUE_JOIN",
            "timestamp": yesterday,
            "zone_id": "BILLING",
            "metadata": {"queue_depth": 15, "session_seq": 1},
            "is_staff": False,
            "dwell_ms": 0,
            "confidence": 0.9,
        }
        await async_client.post("/events/ingest", json={"events": [stale_event]})

        # Today's metrics must NOT show queue_depth=15
        r = await async_client.get("/stores/STORE_TESTQ/metrics")
        assert r.status_code == 200
        data = r.json()
        assert data.get('current_queue_depth', 0) == 0, (
            f"current_queue_depth={data.get('current_queue_depth')} from yesterday's event. "
            "Date filter in queue_depth query is missing or wrong."
        )


class TestDataConfidence:
    """Tests for P3_F3 — data_confidence threshold must be 5, not 20."""

    @pytest.mark.asyncio
    async def test_low_confidence_threshold_is_five(self, async_client):
        """A store with 6 visitors must report HIGH confidence, not LOW."""
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).isoformat()
        events = [
            {
                "event_id": str(uuid.uuid4()),
                "store_id": "STORE_TESTC",
                "camera_id": "CAM_ENTRY_01",
                "visitor_id": f"VIS_{i:03d}",
                "event_type": "ENTRY",
                "timestamp": today,
                "zone_id": None,
                "metadata": {"queue_depth": None, "session_seq": 1},
                "is_staff": False,
                "dwell_ms": 0,
                "confidence": 0.9,
            }
            for i in range(6)
        ]
        await async_client.post("/events/ingest", json={"events": events})

        r = await async_client.get("/stores/STORE_TESTC/metrics")
        data = r.json()
        assert data.get('data_confidence') == 'HIGH', (
            f"data_confidence='{data.get('data_confidence')}' for 6 visitors. "
            "Threshold must be <= 5 for this to return HIGH."
        )


class TestStaffExclusion:
    """Tests for staff exclusion in metrics."""

    @pytest.mark.asyncio
    async def test_staff_events_not_counted_as_visitors(self, async_client):
        """Events with is_staff=True must not inflate unique_visitors."""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).isoformat()

        events = [
            {
                "event_id": "6ca8e040-d01a-48fe-a14d-b32891d33912",
                "store_id": "STORE_TESTS",
                "camera_id": "CAM_ENTRY_01",
                "visitor_id": "STAFF_001",
                "event_type": "ENTRY",
                "timestamp": today,
                "zone_id": None,
                "metadata": {"queue_depth": None, "session_seq": 1},
                "is_staff": True,  # ← staff
                "dwell_ms": 0,
                "confidence": 0.9,
            }
        ]
        await async_client.post("/events/ingest", json={"events": events})

        r = await async_client.get("/stores/STORE_TESTS/metrics")
        data = r.json()
        assert data.get('unique_visitors', 0) == 0, (
            f"unique_visitors={data.get('unique_visitors')} — staff event was counted. "
            "is_staff=TRUE events must be excluded from unique_visitors."
        )


class TestReentryDeduplication:
    """Tests for P4_F2 — re-entering visitors must count as one session."""

    @pytest.mark.asyncio
    async def test_reentry_counts_as_one_session_in_funnel(self, async_client):
        """A visitor who exits and re-enters must appear once in funnel entry count."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)

        events = [
            {
                "event_id": "0e5e6d07-bfb6-40fa-a4f0-85ea5d1d997b",
                "store_id": "STORE_TESTR",
                "camera_id": "CAM_ENTRY_01",
                "visitor_id": "VIS_REENTRY",
                "event_type": "ENTRY",
                "timestamp": now.isoformat(),
                "zone_id": None,
                "metadata": {"queue_depth": None, "session_seq": 1},
                "is_staff": False,
                "dwell_ms": 0,
                "confidence": 0.9,
            },
            {
                "event_id": "bcceb932-8e99-41ab-9afe-5dceec43dca4",
                "store_id": "STORE_TESTR",
                "camera_id": "CAM_ENTRY_01",
                "visitor_id": "VIS_REENTRY",   # same visitor_id
                "event_type": "REENTRY",         # came back
                "timestamp": (now + timedelta(minutes=20)).isoformat(),
                "zone_id": None,
                "metadata": {"queue_depth": None, "session_seq": 1},
                "is_staff": False,
                "dwell_ms": 0,
                "confidence": 0.9,
            }
        ]
        await async_client.post("/events/ingest", json={"events": events})

        r = await async_client.get("/stores/STORE_TESTR/funnel")
        data = r.json()
        entry_count = data['funnel'][0]['count']
        assert entry_count == 1, (
            f"Funnel entry count={entry_count} for one visitor with ENTRY+REENTRY. "
            "Re-entry should not create a second session."
        )
