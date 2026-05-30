# PROMPT: "Generate pytest-asyncio tests for GET /stores/{id}/funnel covering:
#  exactly 4 stages in correct order (Entry/Zone Visit/Billing Queue/Purchase),
#  entry stage dropoff_pct always 0.0,
#  funnel law (each stage count <= previous stage count),
#  empty store returns all counts=0 all dropoff_pct=0.0,
#  re-entry visitor counts as 1 session not 2 in entry stage.
#  Use conftest reentry_events fixture."
# CHANGES MADE: Added parametrised funnel law check across all stage pairs.
#   Fixed stage names to match actual API response ('Zone Visit' not 'Zone').
#   AI used assert len==4 only - added explicit stage order check.

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
