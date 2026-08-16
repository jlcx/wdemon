# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**wdemon** is a Wikidata edit monitor. It consumes the Wikimedia real-time EventStreams API (`recentchange` stream), filters for Wikidata edits, and applies indicator functions to flag potentially problematic changes.

## Running the monitor

```bash
# Simple monitor — prints all Wikidata changes to stdout
python main.py

# Web dashboard over flagged_events (live-updating)
python dashboard.py [--host 127.0.0.1] [--port 8000]
```

`main.py` requires a pywikibot `user-config.py` in the same directory.

## Architecture

### Entry points
- **`main.py`** — Minimal monitor using `pywikibot.comms.eventstreams.EventStreams`. Connects, filters for `wikidatawiki`, and prints each change. Auto-restarts on disconnect.
- **`dashboard.py`** — FastAPI web dashboard over `flagged_events`. Serves `dashboard.html` (single-file vanilla-JS frontend) plus `GET /api/flags?since_hours=&limit=` which returns a time-window slice with `score` extracted from `indicator_details->>'score'`. The client polls every 5 s and does all indicator/user/score/status filtering and sorting locally; stat tiles are the status filter, the per-indicator bars are the indicator filter.

### Indicator system (`indicators.py`)
Indicators are functions that accept a processed event dict and return either `None` (not triggered) or a dict describing the flag. They are organized in tiers by what they need:

- **Tier 1** — event data only: `ip_edit`, `temp_edit`, `large_removal`, `self_reference_added`, `life_dates_changed`
- **Tier 2** — Tier 1 + PostgreSQL DB queries via `psycopg` connection pool: `time_travel_edge` (stub), `high_wp_count_removed`
- **Tier 3** — web API calls (not yet implemented)

All indicators have the signature `indicator(processed_event, logger=None, db_pool=None)`.

### Constants (`wd_constants.py`)
Wikidata property IDs organized by semantic role:
- `cg_rels` — causal/creative graph relationships (used to build the graph in `live_graph.py`)
- `nested_time_rels` — relationships that may carry nested date qualifiers
- `starts` / `ends` / `others` — temporal property sets for ordering checks
- `combined_inverses` — mapping of properties to their inverse properties

### Utilities (`utils.py`)
`parse_edit_comment(comment_string)` parses Wikibase-generated edit comments (e.g., `/* wbsetclaim-update:P31[[Q5]] */`) into structured dicts with keys: `action`, `property_id`, `language`, `is_standard`, `details`.

### Database (`create_tables.sql`)
PostgreSQL schema for a `flagged_events` table storing triggered indicator results. Fields include `rc_id`, `item_qid`, `event_user`, `indicator_name`, and `indicator_details` (JSONB).

## Key design notes

- The `wdemon.py` mentioned in the most recent commit is the intended new main entry point but is not yet present in the repo.
- Indicator functions are designed to be stateless and independently callable — pass `logger` and `db_pool` only when available.
- `wd_constants.all_times` is the union of `starts`, `ends`, and `others` property sets.
