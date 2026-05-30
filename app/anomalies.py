from fastapi import APIRouter
router = APIRouter(tags=["analytics"])

@router.get("/{store_id}/anomalies")
async def get_anomalies(store_id: str):
    return {"status": "not_implemented"}, 501
