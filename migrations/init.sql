-- Store Intelligence API Database Schema

CREATE TABLE IF NOT EXISTS events (
    event_id      TEXT        PRIMARY KEY,
    store_id      TEXT        NOT NULL,
    camera_id     TEXT        NOT NULL,
    visitor_id    TEXT        NOT NULL,
    event_type    TEXT        NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL,
    zone_id       TEXT,
    dwell_ms      INTEGER     NOT NULL DEFAULT 0,
    is_staff      BOOLEAN     NOT NULL DEFAULT FALSE,
    confidence    FLOAT,
    queue_depth   INTEGER,
    sku_zone      TEXT,
    session_seq   INTEGER,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pos_transactions (
    transaction_id  TEXT        PRIMARY KEY,
    store_id        TEXT        NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    basket_value    FLOAT
);

-- Analytics queries filter on store_id + timestamp most frequently
CREATE INDEX IF NOT EXISTS idx_events_store_time
    ON events (store_id, timestamp DESC);

-- Funnel deduplication uses visitor_id
CREATE INDEX IF NOT EXISTS idx_events_visitor
    ON events (visitor_id);

-- Anomaly detection filters on event_type per store
CREATE INDEX IF NOT EXISTS idx_events_store_type
    ON events (store_id, event_type);

-- Staff filter used in every customer query
CREATE INDEX IF NOT EXISTS idx_events_staff
    ON events (store_id, is_staff, timestamp DESC);

-- Zone heatmap and dwell queries
CREATE INDEX IF NOT EXISTS idx_events_zone
    ON events (store_id, zone_id, event_type)
    WHERE zone_id IS NOT NULL;

-- POS correlation join
CREATE INDEX IF NOT EXISTS idx_pos_store_time
    ON pos_transactions (store_id, timestamp DESC);

-- Ensure event_type is one of the valid 8 values
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_event_type') THEN
        ALTER TABLE events ADD CONSTRAINT chk_event_type
            CHECK (event_type IN (
                'ENTRY','EXIT','ZONE_ENTER','ZONE_EXIT','ZONE_DWELL',
                'BILLING_QUEUE_JOIN','BILLING_QUEUE_ABANDON','REENTRY'
            ));
    END IF;
END $$;

-- Confidence must be in valid range
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_confidence') THEN
        ALTER TABLE events ADD CONSTRAINT chk_confidence
            CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0));
    END IF;
END $$;

-- session_seq must be positive
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_session_seq') THEN
        ALTER TABLE events ADD CONSTRAINT chk_session_seq
            CHECK (session_seq IS NULL OR session_seq >= 1);
    END IF;
END $$;
