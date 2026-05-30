from fastapi import APIRouter
router = APIRouter(tags=["events"])

@router.post("/events/ingest")
async def ingest_events():
    return {"status": "not_implemented"}, 501
