from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    store_layout_path: str = "./data/store_layout.json"
    pos_csv_path: str = "./data/pos_transactions.csv"
    pipeline_output_path: str = "./data/events.jsonl"
    staff_color_hue_lower: int = 130
    staff_color_hue_upper: int = 160
    reentry_similarity_threshold: float = 0.72
    reentry_window_seconds: int = 1800
    queue_warn_threshold: int = 5
    queue_critical_threshold: int = 8
    conversion_drop_threshold: float = 0.70
    dead_zone_minutes: int = 30
    stale_feed_minutes: int = 10
    metrics_cache_ttl_seconds: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
