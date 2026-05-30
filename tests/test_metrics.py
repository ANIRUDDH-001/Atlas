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
