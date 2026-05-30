#!/usr/bin/env python3
"""
Data setup script for Brigade Road, Bangalore (STORE_ST1008).

Performs two operations:
1. Preprocesses the real 39-column POS CSV into the 4-column format
   required by the API's pos_transactions table.
2. Generates store_layout.json for STORE_ST1008 from the brigade road
   blueprint spatial analysis.

Usage:
    python3 scripts/setup_data.py
"""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path("data")


def preprocess_pos_data():
    """
    Transform the 39-column line-item POS CSV into 4-column invoice-level CSV.

    Input: data/pos_transactions_raw.csv
    Output: data/pos_transactions.csv (4 columns matching API schema)

    Schema output: store_id, transaction_id, timestamp, basket_value_inr
    """
    raw_path = DATA_DIR / "pos_transactions_raw.csv"
    out_path = DATA_DIR / "pos_transactions.csv"

    if not raw_path.exists():
        print(f"ERROR: {raw_path} not found. Place the Brigade Road CSV here.")
        return False

    print(f"Reading {raw_path}...")
    df = pd.read_csv(raw_path)
    print(f"  Loaded {len(df)} line items, {df['invoice_number'].nunique()} invoices")

    # Aggregate line items to invoice level
    invoices = df.groupby('invoice_number').agg(
        basket_value_inr=('total_amount', 'sum'),
        order_date=('order_date', 'first'),
        order_time=('order_time', 'first'),
        store_id=('store_id', 'first'),
    ).reset_index().rename(columns={'invoice_number': 'transaction_id'})

    # Convert store_id from "ST1008" to "STORE_ST1008"
    invoices['store_id'] = invoices['store_id'].apply(
        lambda x: f"STORE_{x}" if not str(x).startswith("STORE_") else x
    )

    # Combine date + time into ISO-8601 UTC timestamp
    # Original format: order_date="10-04-2026", order_time="16:55:36"
    # Target: "2026-04-10T16:55:36Z" (IST is UTC+5:30, keeping as-is per store local time)
    def build_timestamp(row):
        day, month, year = row['order_date'].split('-')
        return f"{year}-{month}-{day}T{row['order_time']}+05:30"

    invoices['timestamp'] = invoices.apply(build_timestamp, axis=1)

    # Select and order final 4 columns
    result = invoices[['store_id', 'transaction_id', 'timestamp', 'basket_value_inr']]

    result.to_csv(out_path, index=False)
    print(f"  Written {len(result)} invoices to {out_path}")
    print(f"  Total basket value: ₹{result['basket_value_inr'].sum():.2f}")
    print(f"  Time range: {result['timestamp'].min()} to {result['timestamp'].max()}")
    return True


def generate_store_layout():
    """
    Generate store_layout.json for STORE_ST1008 (Brigade Road, Bangalore).

    Zone polygons are normalised coordinates (0.0-1.0) derived from the
    revised store blueprint. Coordinates represent normalised [x, y] positions
    within the camera frame, estimated from the spatial layout diagram.

    Camera coverage assumptions (from blueprint):
    - CAM_ENTRY_01: Covers entrance threshold (left side glass door)
    - CAM_FLOOR_01: Covers top wall (skincare brands)
    - CAM_FLOOR_02: Covers centre floor (makeup + fragrance units)
    - CAM_FLOOR_03: Covers bottom wall (beauty + wellness brands)
    - CAM_BILLING_01: Covers cash counter (right side)
    """
    layout = {
        "STORE_ST1008": {
            "store_name": "Brigade Road, Bangalore",
            "city": "Bangalore",
            "open_hours": {
                "open": "10:00",
                "close": "22:00"
            },
            "cameras": {
                # Entry camera — has threshold_y, no zones
                "CAM_ENTRY_01": {
                    "type": "entry_exit",
                    "source_file": "CAM 1.mp4",
                    "fps": 29.97,
                    "threshold_y": 0.50,
                    "description": "Glass entrance doorway, left side"
                },
                # Floor camera 1 — Skincare wall (top wall units)
                "CAM_FLOOR_01": {
                    "type": "floor",
                    "source_file": "CAM 2.mp4",
                    "fps": 29.97,
                    "description": "Top wall skincare brands",
                    "zones": {
                        "SKINCARE": [
                            [0.0, 0.0], [0.7, 0.0],
                            [0.7, 0.6], [0.0, 0.6]
                        ],
                        "HAIRCARE": [
                            [0.7, 0.0], [1.0, 0.0],
                            [1.0, 0.6], [0.7, 0.6]
                        ],
                        "WALKWAY": [
                            [0.0, 0.6], [1.0, 0.6],
                            [1.0, 1.0], [0.0, 1.0]
                        ]
                    }
                },
                # Floor camera 2 — Makeup + Fragrance (centre floor)
                "CAM_FLOOR_02": {
                    "type": "floor",
                    "source_file": "CAM 3.mp4",
                    "fps": 29.97,
                    "description": "Centre floor makeup and fragrance units",
                    "zones": {
                        "MAKEUP": [
                            [0.0, 0.1], [0.55, 0.1],
                            [0.55, 0.8], [0.0, 0.8]
                        ],
                        "FRAGRANCE": [
                            [0.55, 0.1], [1.0, 0.1],
                            [1.0, 0.8], [0.55, 0.8]
                        ],
                        "WALKWAY": [
                            [0.0, 0.8], [1.0, 0.8],
                            [1.0, 1.0], [0.0, 1.0]
                        ]
                    }
                },
                # Floor camera 3 — Bottom wall (beauty brands)
                "CAM_FLOOR_03": {
                    "type": "floor",
                    "source_file": "CAM 4.mp4",
                    "fps": 24.98,
                    "description": "Bottom wall beauty and wellness brands",
                    "zones": {
                        "BEAUTY": [
                            [0.0, 0.0], [0.6, 0.0],
                            [0.6, 0.65], [0.0, 0.65]
                        ],
                        "WELLNESS": [
                            [0.6, 0.0], [1.0, 0.0],
                            [1.0, 0.65], [0.6, 0.65]
                        ],
                        "WALKWAY": [
                            [0.0, 0.65], [1.0, 0.65],
                            [1.0, 1.0], [0.0, 1.0]
                        ]
                    }
                },
                # Billing camera — Cash counter
                "CAM_BILLING_01": {
                    "type": "billing",
                    "source_file": "CAM 5.mp4",
                    "fps": 24.98,
                    "description": "Cash counter / billing area",
                    "zones": {
                        "BILLING": [
                            [0.0, 0.0], [1.0, 0.0],
                            [1.0, 0.75], [0.0, 0.75]
                        ],
                        "BILLING_QUEUE": [
                            [0.0, 0.75], [1.0, 0.75],
                            [1.0, 1.0], [0.0, 1.0]
                        ]
                    }
                }
            }
        }
    }

    out_path = DATA_DIR / "store_layout.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(layout, f, indent=2, ensure_ascii=False)

    print(f"\nStore layout written to {out_path}")
    cameras = layout["STORE_ST1008"]["cameras"]
    for cam_id, cam in cameras.items():
        zones = list(cam.get("zones", {}).keys())
        print(f"  {cam_id}: {cam['type']} | zones={zones} | file={cam['source_file']}")
    return True


def update_pipeline_camera_map():
    """
    Write pipeline/camera_map.json mapping real filenames to logical camera IDs.
    Used by pipeline/run.sh to process each clip with the correct camera_id.
    """
    camera_map = {
        "CAM 1.mp4": {
            "camera_id": "CAM_ENTRY_01",
            "store_id": "STORE_ST1008",
            "fps": 29.97
        },
        "CAM 2.mp4": {
            "camera_id": "CAM_FLOOR_01",
            "store_id": "STORE_ST1008",
            "fps": 29.97
        },
        "CAM 3.mp4": {
            "camera_id": "CAM_FLOOR_02",
            "store_id": "STORE_ST1008",
            "fps": 29.97
        },
        "CAM 4.mp4": {
            "camera_id": "CAM_FLOOR_03",
            "store_id": "STORE_ST1008",
            "fps": 24.98
        },
        "CAM 5.mp4": {
            "camera_id": "CAM_BILLING_01",
            "store_id": "STORE_ST1008",
            "fps": 24.98
        }
    }
    out_path = Path("pipeline") / "camera_map.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(camera_map, f, indent=2)
    print(f"\nCamera map written to {out_path}")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Store Intelligence — Data Setup")
    print("Store: Brigade Road, Bangalore (STORE_ST1008)")
    print("=" * 60)

    DATA_DIR.mkdir(exist_ok=True)

    pos_ok     = preprocess_pos_data()
    layout_ok  = generate_store_layout()
    cam_map_ok = update_pipeline_camera_map()

    print("\n" + "=" * 60)
    if pos_ok and layout_ok and cam_map_ok:
        print("SETUP COMPLETE — All data files generated.")
        print("Next: docker compose up --build")
        print("Then: bash pipeline/run.sh")
        print("Then: python3 scripts/ingest_events.py")
    else:
        print("SETUP INCOMPLETE — Check errors above.")
