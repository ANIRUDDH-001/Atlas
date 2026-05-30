from fastapi import APIRouter
router = APIRouter(tags=["analytics"])

async def compute_metrics(store_id: str):
    raise NotImplementedError

@router.get("/{store_id}/metrics")
async def get_metrics(store_id: str):
    return {"status": "not_implemented"}, 501
