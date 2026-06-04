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

        required = {"order_id", "order_date", "order_time", "store_id", "total_amount"}
        if not required.issubset(set(reader.fieldnames)):
            logger.error("pos_csv_bad_headers",
                         found=reader.fieldnames,
                         required=list(required))
            return 0

        # Group by order_id to get invoice-level data
        invoices = {}

        for line_num, row in enumerate(reader, start=2):
            try:
                order_id = row["order_id"].strip()
                date_str = row["order_date"].strip()
                time_str = row["order_time"].strip()
                store_id = row["store_id"].strip()
                # Handle store_id format mismatch. Events use STORE_ST1008, POS might use ST1008
                if not store_id.startswith("STORE_"):
                    store_id = f"STORE_{store_id}"
                    
                amount_str = row["total_amount"].strip()

                if not all([order_id, date_str, time_str, store_id, amount_str]):
                    skipped += 1
                    continue

                # Expected format: 10-04-2026, 12:15:05
                # We assume IST (+05:30) for POS transactions if not specified, 
                dt_str = f"{date_str[6:10]}-{date_str[3:5]}-{date_str[0:2]}T{time_str}+05:30"
                ts = datetime.fromisoformat(dt_str)
                
                amount = float(amount_str)
                
                if order_id not in invoices:
                    invoices[order_id] = {
                        "store_id": store_id,
                        "timestamp": ts,
                        "basket": 0.0
                    }
                invoices[order_id]["basket"] += amount

            except (ValueError, KeyError) as exc:
                malformed += 1
                logger.warning("pos_row_malformed",
                               line=line_num, error=str(exc))
                continue

        for transaction_id, inv in invoices.items():
            result = await db.execute(text("""
                INSERT INTO pos_transactions
                    (transaction_id, store_id, timestamp, basket_value)
                VALUES
                    (:transaction_id, :store_id, :timestamp, :basket)
                ON CONFLICT (transaction_id) DO NOTHING
            """), {
                "transaction_id": transaction_id,
                "store_id": inv["store_id"],
                "timestamp": inv["timestamp"],
                "basket": inv["basket"],
            })
            if result.rowcount != 0:  # type: ignore
                inserted += 1

    await db.commit()
    logger.info("pos_load_complete",
                inserted=inserted, skipped=skipped, malformed=malformed,
                path=str(csv_path))
    return inserted
