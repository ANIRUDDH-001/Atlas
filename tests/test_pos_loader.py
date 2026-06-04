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
            "order_id,order_date,order_time,store_id,product_id,brand_name,total_amount\n"
            "1,10-04-2026,12:15:05,ST1008,123,BrandA,150.5\n"
            "2,10-04-2026,12:20:00,ST1008,124,BrandB,malformed\n"
            "3,,,ST1008,125,BrandC,250.0\n" # skipped
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
