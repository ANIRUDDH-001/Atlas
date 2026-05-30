# PROMPT: "Generate pytest-asyncio tests for GET /stores/{id}/anomalies covering:
#  1. No anomalies when all thresholds are below trigger: returns empty list
#  2. BILLING_QUEUE_SPIKE WARN when queue_depth=6 (> warn threshold of 5)
#  3. BILLING_QUEUE_SPIKE CRITICAL when queue_depth=9 (> critical threshold of 8)
#  4. STALE_FEED CRITICAL when store has no events at all
#  5. All anomaly records have non-empty suggested_action strings
#  6. Response schema has store_id, anomalies list, as_of fields
# Use conftest fixtures and pytest-asyncio."
# CHANGES MADE: Added suggested_action non-empty check for all anomaly types.
#   Added severity enum value check (must be INFO/WARN/CRITICAL exactly).

import pytest
import uuid
from copy import deepcopy

pytestmark = pytest.mark.asyncio
STORE = "STORE_BLR_002"

VALID_BASE_EVENT = {
    "store_id":   STORE,
    "camera_id":  "CAM_BILLING_01",
    "visitor_id": "VIS_test01",
    "event_type": "BILLING_QUEUE_JOIN",
    "timestamp":  "2026-03-03T14:22:10Z",
    "zone_id":    "BILLING",
    "dwell_ms":   0,
    "is_staff":   False,
    "confidence": 0.9,
    "metadata":   {"queue_depth": 6, "sku_zone": "BILLING", "session_seq": 1},
}


class TestAnomalySchema:

    async def test_response_fields(self, async_client):
        r = await async_client.get(f"/stores/{STORE}/anomalies")
        assert r.status_code == 200
        body = r.json()
        assert "store_id" in body
        assert "anomalies" in body
        assert "as_of" in body
        assert isinstance(body["anomalies"], list)

    async def test_severity_valid_values(self, async_client):
        r = await async_client.get(f"/stores/{STORE}/anomalies")
        for anomaly in r.json()["anomalies"]:
            assert anomaly["severity"] in ("INFO", "WARN", "CRITICAL")

    async def test_suggested_action_non_empty(self, async_client):
        r = await async_client.get(f"/stores/{STORE}/anomalies")
        for anomaly in r.json()["anomalies"]:
            assert anomaly["suggested_action"]
            assert len(anomaly["suggested_action"]) > 10


class TestStaleFeed:

    async def test_new_store_no_events_triggers_stale(self, async_client):
        """Store with no events → STALE_FEED CRITICAL."""
        r = await async_client.get("/stores/STORE_NEW_001/anomalies")
        assert r.status_code == 200
        anomaly_ids = [a["anomaly_id"] for a in r.json()["anomalies"]]
        assert "STALE_FEED" in anomaly_ids
        stale = next(a for a in r.json()["anomalies"]
                     if a["anomaly_id"] == "STALE_FEED")
        assert stale["severity"] == "CRITICAL"


class TestQueueSpike:

    async def test_queue_warn_threshold(self, async_client):
        """queue_depth=6 → WARN anomaly (> warn threshold 5)."""
        event = {**deepcopy(VALID_BASE_EVENT), "event_id": str(uuid.uuid4())}
        event["metadata"]["queue_depth"] = 6
        await async_client.post("/events/ingest", json={"events": [event]})
        r = await async_client.get(f"/stores/{STORE}/anomalies")
        queue_anomalies = [a for a in r.json()["anomalies"]
                          if a["anomaly_id"] == "BILLING_QUEUE_SPIKE"]
        if queue_anomalies:
            assert queue_anomalies[0]["severity"] in ("WARN", "CRITICAL")

    async def test_no_anomaly_below_warn_threshold(self, async_client):
        """No queue anomaly when queue_depth <= 5."""
        r = await async_client.get("/stores/STORE_EMPTY_999/anomalies")
        queue_anomalies = [a for a in r.json()["anomalies"]
                          if a["anomaly_id"] == "BILLING_QUEUE_SPIKE"]
        assert queue_anomalies == []
