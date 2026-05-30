# Handoff: Documentation → Final Integration

## What Must Be True Before Submission

### Acceptance Gate Requirements
1. `docker compose up --build` starts all 4 services (db, redis, api, dashboard)
2. `GET /health` returns HTTP 200 within 60 seconds of startup
3. `POST /events/ingest` accepts events without 5xx
4. `GET /stores/STORE_ST1008/metrics` returns valid JSON with `unique_visitors`
5. `docs/DESIGN.md` exists, word count > 250
6. `docs/CHOICES.md` exists, word count > 250

### Final Checklist Before git push
- [ ] `docker compose down && docker compose up --build` — cold start works
- [ ] `bash pipeline/run.sh` — documented in README, exits 0
- [ ] `python3 scripts/setup_data.py` — creates pos_transactions.csv and store_layout.json
- [ ] `python3 scripts/ingest_events.py` — ingests events.jsonl into API
- [ ] `pytest tests/ --cov=app --cov-fail-under=70` — coverage >= 70%
- [ ] `wc -w docs/DESIGN.md` > 500
- [ ] `wc -w docs/CHOICES.md` > 500
- [ ] `wc -w README.md` > 400
- [ ] All 5 test files have # PROMPT: block headers
- [ ] No video files in git repo (data/ must be in .gitignore)
- [ ] No .env file in git repo
- [ ] http://localhost:3000 dashboard shows live metrics

### Store ID Consistency Check
All occurrences of store_id must be `STORE_ST1008` (not STORE_BLR_002):
```bash
grep -r "STORE_BLR_002" app/ pipeline/ tests/ docs/ --include="*.py" --include="*.md"
# Must return 0 results
```

### Video Files Must Not Be in Repo
```bash
git ls-files | grep -E "\.mp4|\.avi|\.mov"
# Must return 0 results
```
