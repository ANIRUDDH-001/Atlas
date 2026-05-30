import pytest, json
from pathlib import Path
from httpx import AsyncClient, ASGITransport

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_events():
    return [json.loads(l) for l in
            (FIXTURES_DIR / "sample_events.jsonl").read_text().splitlines()]

@pytest.fixture
def staff_only_events():
    return [json.loads(l) for l in
            (FIXTURES_DIR / "staff_events.jsonl").read_text().splitlines()]

@pytest.fixture
def reentry_events():
    return [json.loads(l) for l in
            (FIXTURES_DIR / "reentry_events.jsonl").read_text().splitlines()]

@pytest.fixture
async def async_client():
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
