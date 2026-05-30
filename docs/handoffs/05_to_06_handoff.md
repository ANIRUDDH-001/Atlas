# Handoff: Security → Database

## SQL Security Requirements
- All SQL in `migrations/init.sql` must use explicit column names (no SELECT *)
- All application SQL must use SQLAlchemy text() with :param binds
- No dynamic table or column name construction from user input
- PostgreSQL user `apex` must have CONNECT + SELECT + INSERT + UPDATE
  on `events` and `pos_transactions` only — no DROP, CREATE, or TRUNCATE

## Indexes must not expose sensitive data
- No indexes on fields that could be used for enumeration attacks
- `visitor_id` index is acceptable (opaque hex string)

## Connection Pooling
- `pool_pre_ping=True` already set in app/db.py — verify it stays
- Max pool size: 10 connections (set in app/db.py)
