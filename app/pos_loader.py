import csv
import structlog
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


async def load_pos_transactions(db: AsyncSession) -> int:
    """
    Load POS transactions from CSV into the database.
    Idempotent: ON CONFLICT (transaction_id) DO NOTHING.
    Returns the number of rows newly inserted.
    """
    csv_path = Path(settings.pos_csv_path)
    if not csv_path.exists():
        logger.warning("pos_csv_not_found", path=str(csv_path))
        return 0

    inserted = 0
    skipped = 0
    malformed = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        # Strip whitespace from field names (CSV may have spaces after commas)
        reader = csv.DictReader(f)
        reader.fieldnames = [name.strip() for name in reader.fieldnames or []]

        required = {"store_id", "transaction_id", "timestamp", "basket_value_inr"}
        if not required.issubset(set(reader.fieldnames)):
            logger.error("pos_csv_bad_headers",
                         found=reader.fieldnames,
                         required=list(required))
            return 0

        for line_num, row in enumerate(reader, start=2):
            try:
                store_id       = row["store_id"].strip()
                transaction_id = row["transaction_id"].strip()
                ts_str         = row["timestamp"].strip()
                basket_str     = row["basket_value_inr"].strip()

                if not all([store_id, transaction_id, ts_str, basket_str]):
                    skipped += 1
                    continue

                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                basket = float(basket_str)

                result = await db.execute(text("""
                    INSERT INTO pos_transactions
                        (transaction_id, store_id, timestamp, basket_value)
                    VALUES
                        (:transaction_id, :store_id, :timestamp, :basket)
                    ON CONFLICT (transaction_id) DO NOTHING
                """), {
                    "transaction_id": transaction_id,
                    "store_id": store_id,
                    "timestamp": ts,
                    "basket": basket,
                })
                if result.rowcount != 0:  # type: ignore
                    inserted += 1

            except (ValueError, KeyError) as exc:
                malformed += 1
                logger.warning("pos_row_malformed",
                               line=line_num, error=str(exc))
                continue

    await db.commit()
    logger.info("pos_load_complete",
                inserted=inserted, skipped=skipped, malformed=malformed,
                path=str(csv_path))
    return inserted
