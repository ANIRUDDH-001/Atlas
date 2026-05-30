"""
# PROMPT: Generate pytest-asyncio tests for GET /stores/{store_id}/heatmap
# covering empty store, invalid store_id, and correct heatmap grid response.
"""

import pytest

pytestmark = pytest.mark.asyncio

VALID_STORE = "STORE_ST1008"
INVALID_STORE = "not-a-store"


class TestHeatmapSchema:
    async def test_invalid_store_id_returns_400(self, async_client):
        r = await async_client.get(f"/stores/{INVALID_STORE}/heatmap")
        assert r.status_code == 400

    async def test_heatmap_response_schema(self, async_client, sample_events):
        await async_client.post("/events/ingest", json={"events": sample_events})
        r = await async_client.get(f"/stores/{VALID_STORE}/heatmap")
        assert r.status_code == 200
        body = r.json()
        assert "store_id" in body
        assert "zones" in body
        assert "as_of" in body
        assert isinstance(body["zones"], list)
        
        if len(body["zones"]) > 0:
            zone = body["zones"][0]
            assert "zone_id" in zone
            assert "normalised_score" in zone
            assert "avg_dwell_sec" in zone


class TestEmptyStoreHeatmap:
    async def test_empty_store_returns_empty_grid(self, async_client):
        r = await async_client.get("/stores/STORE_EMPTY_999/heatmap")
        assert r.status_code == 200
        assert r.json()["zones"] == []
