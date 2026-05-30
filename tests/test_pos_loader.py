"""
# PROMPT: Generate pytest-asyncio tests for app.pos_loader
"""

import pytest
import tempfile
import os
from unittest.mock import patch

from app.db import AsyncSessionLocal
from app.pos_loader import load_pos_transactions
from app.config import get_settings

pytestmark = pytest.mark.asyncio


class TestPOSLoader:
    async def test_load_pos_transactions_not_found(self):
        settings = get_settings()
        with patch.object(settings, "pos_csv_path", "non_existent_file.csv"):
            async with AsyncSessionLocal() as db:
                inserted = await load_pos_transactions(db)
                assert inserted == 0

    async def test_load_pos_transactions_bad_headers(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
            f.write("wrong,headers\n1,2\n")
            temp_path = f.name
            
        settings = get_settings()
        try:
            with patch.object(settings, "pos_csv_path", temp_path):
                async with AsyncSessionLocal() as db:
                    inserted = await load_pos_transactions(db)
                    assert inserted == 0
        finally:
            os.remove(temp_path)

    async def test_load_pos_transactions_success(self):
        csv_content = (
            "store_id,transaction_id,timestamp,basket_value_inr\n"
            "STORE_ST1008,TX_1,2026-03-03T10:00:00Z,150.5\n"
            "STORE_ST1008,TX_2,2026-03-03T10:05:00Z,malformed\n"
            "STORE_ST1008,TX_3,,250.0\n" # skipped
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
            f.write(csv_content)
            temp_path = f.name
            
        settings = get_settings()
        try:
            with patch.object(settings, "pos_csv_path", temp_path):
                async with AsyncSessionLocal() as db:
                    inserted = await load_pos_transactions(db)
                    # 1 success, 1 malformed, 1 skipped
                    assert inserted == 1
        finally:
            os.remove(temp_path)
