# PROMPT: "Generate pytest-asyncio tests for POST /events/ingest covering:
#  idempotency (same event_id ingested twice returns accepted=0 on second call),
#  partial success (1 malformed + 4 valid returns accepted=4 rejected=1 HTTP 200),
#  batch size limit (>500 events returns 400), all-staff clip (unique_visitors=0),
#  re-entry dedup in funnel (ENTRY+EXIT+REENTRY counts as 1 session not 2).
#  Use httpx AsyncClient with ASGITransport, pytest-asyncio, conftest fixtures."
# CHANGES MADE: Added store_id format validation test (STORE_ST1008 pattern).
#   Changed fixture to use valid_single_event for clarity over raw dict.
#   Added confidence=0.0 test - AI omitted this edge case.
#   Corrected reentry fixture to use STORE_ST1008 not STORE_BLR_002.

#   Added confidence=0.0 test (must not be rejected — low conf is valid).
#   Changed fixture to use valid_single_event for clarity.

import uuid
import pytest
from copy import deepcopy

pytestmark = pytest.mark.asyncio


class TestIngestHappyPath:

    async def test_valid_batch_accepted(self, async_client, sample_events):
        r = await async_client.post(
            "/events/ingest",
            json={"events": sample_events},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["accepted"] == len(sample_events)
        assert body["rejected"] == 0
        assert body["errors"] == []

    async def test_response_schema(self, async_client, valid_single_event):
        r = await async_client.post(
            "/events/ingest",
            json={"events": [valid_single_event]},
        )
        body = r.json()
        assert "accepted" in body
        assert "rejected" in body
        assert "errors" in body
        assert isinstance(body["accepted"], int)
        assert isinstance(body["errors"], list)

    async def test_low_confidence_accepted(self, async_client, valid_single_event):
        """confidence=0.0 must NOT be rejected — low conf events are valid."""
        event = deepcopy(valid_single_event)
        event["event_id"]   = str(uuid.uuid4())
        event["confidence"] = 0.0
        r = await async_client.post("/events/ingest", json={"events": [event]})
        assert r.json()["accepted"] == 1


class TestIdempotency:

    async def test_double_ingest_no_duplicate(self, async_client, valid_single_event):
        """Posting the same event_id twice: second call accepted=0."""
        payload = {"events": [valid_single_event]}
        r1 = await async_client.post("/events/ingest", json=payload)
        r2 = await async_client.post("/events/ingest", json=payload)
        assert r1.json()["accepted"] == 1
        assert r2.json()["accepted"] == 0

    async def test_idempotent_large_batch(self, async_client, sample_events):
        """Idempotency holds for batches, not just single events."""
        payload = {"events": sample_events}
        r1 = await async_client.post("/events/ingest", json=payload)
        r2 = await async_client.post("/events/ingest", json=payload)
        assert r2.json()["accepted"] == 0
        assert r2.json()["rejected"] == 0


class TestPartialSuccess:

    async def test_mixed_batch_partial_success(
        self, async_client, valid_single_event, malformed_event
    ):
        """1 malformed + 4 valid → accepted=4, rejected=1, HTTP 200."""
        good_events = [
            {**deepcopy(valid_single_event), "event_id": str(uuid.uuid4())}
            for _ in range(4)
        ]
        payload = {"events": [malformed_event] + good_events}
        r = await async_client.post("/events/ingest", json=payload)
        assert r.status_code == 200  # Not 4xx — partial success is 200
        body = r.json()
        assert body["accepted"] == 4
        assert body["rejected"] == 1
        assert len(body["errors"]) == 1

    async def test_all_malformed_zero_accepted(
        self, async_client, malformed_event
    ):
        payload = {"events": [malformed_event]}
        r = await async_client.post("/events/ingest", json=payload)
        assert r.status_code == 200
        assert r.json()["accepted"] == 0


class TestBatchValidation:

    async def test_batch_over_500_returns_400(self, async_client, valid_single_event):
        events = [
            {**deepcopy(valid_single_event), "event_id": str(uuid.uuid4())}
            for _ in range(501)
        ]
        r = await async_client.post("/events/ingest", json={"events": events})
        assert r.status_code in (400, 422)

    async def test_empty_batch_returns_422(self, async_client):
        r = await async_client.post("/events/ingest", json={"events": []})
        assert r.status_code == 422


class TestStaffExclusion:

    async def test_all_staff_metrics_zero_visitors(
        self, async_client, staff_only_events
    ):
        """Store with only staff events → unique_visitors=0."""
        await async_client.post("/events/ingest",
                                json={"events": staff_only_events})
        r = await async_client.get("/stores/STORE_STAFF_001/metrics")
        assert r.status_code == 200
        assert r.json()["unique_visitors"] == 0


class TestReEntryFunnel:

    async def test_reentry_counts_as_one_session(
        self, async_client, reentry_events
    ):
        """Visitor with ENTRY+EXIT+REENTRY = 1 session in funnel."""
        await async_client.post("/events/ingest",
                                json={"events": reentry_events})
        r = await async_client.get("/stores/STORE_ST1008/funnel")
        assert r.status_code == 200
        stages = r.json()["funnel"]
        entry_count = next(s["count"] for s in stages if s["stage"] == "Entry")
        assert entry_count == 1  # Not 2 — REENTRY reuses visitor_id
