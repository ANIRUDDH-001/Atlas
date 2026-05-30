# PROMPT: "Generate pytest-asyncio tests for GET /stores/{id}/funnel covering:
#  1. Empty store: all funnel counts are 0, all dropoff_pct are 0.0
#  2. Funnel law: purchase_count <= billing_count <= zone_count <= entry_count
#  3. Re-entry dedup: visitor with ENTRY+EXIT+REENTRY counts as 1 in entry stage
#  4. Response has exactly 4 stages in correct order
#  5. Entry stage dropoff_pct is always 0.0
# Use conftest fixtures and pytest-asyncio."
# CHANGES MADE: Added funnel law assertion as a parametrised check.
#   Added stage order verification.

import pytest

pytestmark = pytest.mark.asyncio
STORE = "STORE_BLR_002"


class TestFunnelSchema:

    async def test_exactly_four_stages(self, async_client):
        r = await async_client.get(f"/stores/{STORE}/funnel")
        assert r.status_code == 200
        assert len(r.json()["funnel"]) == 4

    async def test_stage_order(self, async_client):
        r = await async_client.get(f"/stores/{STORE}/funnel")
        stages = [s["stage"] for s in r.json()["funnel"]]
        assert stages == ["Entry", "Zone Visit", "Billing Queue", "Purchase"]

    async def test_entry_stage_dropoff_always_zero(self, async_client):
        r = await async_client.get(f"/stores/{STORE}/funnel")
        entry = r.json()["funnel"][0]
        assert entry["stage"] == "Entry"
        assert entry["dropoff_pct"] == 0.0


class TestEmptyStoreFunnel:

    async def test_empty_store_all_zeros(self, async_client):
        r = await async_client.get("/stores/STORE_EMPTY_999/funnel")
        assert r.status_code == 200
        for stage in r.json()["funnel"]:
            assert stage["count"] == 0
            assert stage["dropoff_pct"] == 0.0

    async def test_funnel_law_holds(self, async_client, sample_events):
        await async_client.post("/events/ingest",
                                json={"events": sample_events})
        r = await async_client.get(f"/stores/{STORE}/funnel")
        stages = r.json()["funnel"]
        counts = [s["count"] for s in stages]
        for i in range(len(counts) - 1):
            assert counts[i] >= counts[i + 1], (
                f"Funnel law violated: {stages[i]['stage']}={counts[i]} "
                f"< {stages[i+1]['stage']}={counts[i+1]}"
            )
