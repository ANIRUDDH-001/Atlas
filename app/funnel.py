from fastapi import APIRouter
router = APIRouter(tags=["analytics"])

@router.get("/{store_id}/funnel")
async def get_funnel(store_id: str):
    return {"status": "not_implemented"}, 501
