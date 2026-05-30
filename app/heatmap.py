from fastapi import APIRouter
router = APIRouter(tags=["analytics"])

@router.get("/{store_id}/heatmap")
async def get_heatmap(store_id: str):
    return {"status": "not_implemented"}, 501
