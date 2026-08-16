#!/usr/bin/env python3
"""
Web dashboard for wdemon flagged_events.

Serves a single-page live dashboard (dashboard.html) and a JSON API over the
flagged_events table. The server only slices by time window; sorting and
filtering by indicator / user / score happen client-side so they respond
instantly and stay consistent while new rows stream in.

Usage:
    python dashboard.py [--host 127.0.0.1] [--port 8000]
"""
import argparse
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DB_CONNINFO = "dbname=algae"
HTML_PATH = Path(__file__).parent / "dashboard.html"

# Hard cap on rows returned per request, newest first.
MAX_ROWS = 20000

app = FastAPI(title="wdemon dashboard")
pool = ConnectionPool(conninfo=DB_CONNINFO, min_size=1, max_size=4, open=False)


@app.on_event("startup")
def _open_pool():
    pool.open()


@app.on_event("shutdown")
def _close_pool():
    pool.close()


@app.get("/")
def index():
    return FileResponse(HTML_PATH, media_type="text/html")


@app.get("/api/flags")
def flags(
    since_hours: float = Query(24, gt=0, le=24 * 90),
    limit: int = Query(5000, gt=0, le=MAX_ROWS),
):
    """
    Flagged events within the last `since_hours`, newest first.
    `score` is pulled out of indicator_details when present (currently only
    bad_description emits one); null otherwise.
    """
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, rc_id, event_timestamp, processed_timestamp,
                   item_qid, event_user, indicator_name, indicator_details,
                   revision_old, revision_new, reverted_at, corrected_at,
                   (indicator_details->>'score')::float AS score
              FROM flagged_events
             WHERE processed_timestamp > NOW() - make_interval(secs => %s)
             ORDER BY id DESC
             LIMIT %s
            """,
            (since_hours * 3600, limit),
        )
        rows = cur.fetchall()

    for r in rows:
        for k in ("event_timestamp", "processed_timestamp",
                  "reverted_at", "corrected_at"):
            if r[k] is not None:
                r[k] = r[k].isoformat()
    return {"rows": rows, "truncated": len(rows) >= limit}


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
