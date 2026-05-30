"""
# PROMPT: Generate pytest-asyncio tests for GET /health
"""

import pytest

pytestmark = pytest.mark.asyncio


class TestHealthEndpoint:
    async def test_health_returns_200(self, async_client):
        r = await async_client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert "status" in body
        assert body["status"] == "OK"
        assert "database" in body
        assert "cache" in body
