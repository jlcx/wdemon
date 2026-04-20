#!/usr/bin/env python3
"""
CLI report of unreverted flagged_events.

Two sections:
  1. Top users by unreverted flag count
  2. Most recent unreverted flags (detail lines)

Usage:
    python report.py [--since '7 days'] [--limit 20] [--user USERNAME]
"""
import argparse

from psycopg_pool import ConnectionPool

DB_CONNINFO = "dbname=algae"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--since', default='7 days',
                    help="PostgreSQL interval string (default: '7 days')")
    ap.add_argument('--limit', type=int, default=20,
                    help="Max rows per section (default: 20)")
    ap.add_argument('--user', default=None,
                    help="Restrict to one user (skips the rollup section)")
    args = ap.parse_args()

    pool = ConnectionPool(conninfo=DB_CONNINFO, min_size=1, max_size=2, open=True)
    try:
        with pool.connection() as conn, conn.cursor() as cur:
            if args.user is None:
                print_user_rollup(cur, args.since, args.limit)
                print()
            print_recent_flags(cur, args.since, args.limit, args.user)
    finally:
        pool.close()


def print_user_rollup(cur, since, limit):
    cur.execute(
        """
        SELECT event_user,
               COUNT(*) AS n_flags,
               COUNT(DISTINCT item_qid) AS n_items,
               ARRAY_AGG(DISTINCT indicator_name ORDER BY indicator_name) AS indicators,
               MAX(processed_timestamp) AS last_flag_at
          FROM flagged_events
         WHERE reverted_at IS NULL
           AND corrected_at IS NULL
           AND processed_timestamp > NOW() - %s::interval
         GROUP BY event_user
         ORDER BY n_flags DESC, last_flag_at DESC
         LIMIT %s
        """,
        (since, limit),
    )
    rows = cur.fetchall()
    print(f"=== Top users by unreverted flags (last {since}, top {limit}) ===")
    if not rows:
        print("(none)")
        return
    print(f"{'user':<30} {'flags':>6} {'items':>6}  {'last_flag_at':<20}  indicators")
    print("-" * 100)
    for user, n, items, inds, last in rows:
        user_s = (user or '(unknown)')
        if len(user_s) > 29:
            user_s = user_s[:28] + '…'
        print(f"{user_s:<30} {n:>6} {items:>6}  "
              f"{last.strftime('%Y-%m-%d %H:%M:%S'):<20}  {', '.join(inds)}")


def print_recent_flags(cur, since, limit, user_filter):
    sql = """
        SELECT processed_timestamp, event_user, item_qid, indicator_name,
               indicator_details, revision_new
          FROM flagged_events
         WHERE reverted_at IS NULL
           AND corrected_at IS NULL
           AND processed_timestamp > NOW() - %s::interval
    """
    params = [since]
    if user_filter is not None:
        sql += " AND event_user = %s"
        params.append(user_filter)
    sql += " ORDER BY processed_timestamp DESC LIMIT %s"
    params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()

    hdr = f"=== Most recent unreverted flags (last {since}, top {limit}"
    if user_filter:
        hdr += f", user={user_filter}"
    hdr += ") ==="
    print(hdr)
    if not rows:
        print("(none)")
        return
    for ts, user, qid, ind, details, rev in rows:
        summary = ''
        if isinstance(details, dict):
            summary = details.get('details') or details.get('value') or ''
        rev_s = f"r{rev}" if rev else ''
        user_s = (user or '?')[:20]
        print(f"{ts.strftime('%Y-%m-%d %H:%M:%S')}  {ind:<25} {qid or '?':<10}  "
              f"by {user_s:<20} {rev_s:<12} {summary}")


if __name__ == '__main__':
    main()
