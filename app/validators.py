import re
from fastapi import HTTPException

STORE_ID_PATTERN = re.compile(r"^STORE_[A-Z]{2,6}_\d{3}$")

def validate_store_id(store_id: str) -> str:
    """
    Validate store_id format. Returns store_id if valid.
    Raises HTTP 400 if invalid.
    Pattern: STORE_<2-6 uppercase letters>_<3 digits>
    Example: STORE_BLR_002
    """
    if not STORE_ID_PATTERN.match(store_id):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_store_id",
                "message": f"store_id must match pattern STORE_<CITY>_<NNN>",
                "received": store_id,
            },
        )
    return store_id
