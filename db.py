"""Database write helpers for wdemon."""
import logging
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from utils import parse_edit_comment

logger = logging.getLogger(__name__)

# How far back to look when matching a "Reverted edits by X" event (no specific
# revision id) to prior flagged rows by that user on the same item.
REVERT_LOOKBACK = "1 day"


def record_flag(db_pool, event, indicator_name, result):
    """
    INSERT a triggered indicator into flagged_events. Swallows errors
    after logging so DB issues don't stop the monitor.
    """
    if not db_pool:
        return

    rc_id = event.get('id') or event.get('rc_id')
    if rc_id is None:
        return

    ts = event.get('timestamp')
    event_ts = (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(ts, (int, float)) else None
    )
    revision = event.get('revision') or {}

    if isinstance(result, dict):
        details_payload = result
    elif result:
        details_payload = {"value": str(result)}
    else:
        return

    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO flagged_events
                        (rc_id, event_timestamp, item_qid, event_user,
                         indicator_name, indicator_details,
                         revision_old, revision_new)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        rc_id, event_ts,
                        event.get('title'), event.get('user'),
                        indicator_name,
                        Jsonb(details_payload),
                        revision.get('old'), revision.get('new'),
                    ),
                )
    except Exception as e:
        logger.error(
            f"record_flag failed for {indicator_name} on {event.get('title')}: {e}",
            exc_info=True,
        )


REVERT_TAGS = frozenset({'mw-undo', 'mw-manual-revert', 'mw-rollback'})


def mark_reverts(db_pool, event):
    """
    If `event` looks like an undo/revert, mark matching flagged_events rows as
    reverted and return the total rowcount across strategies. Returns 0 on no
    match, error, or non-revert events.

    Strategies (combined; a row reverted_at by one is skipped by the next):
      1. Specific revision match. The revision being reverted-away-from is:
         - details['undone_rev_id'] when the comment parses as 'Undo revision N';
         - otherwise event['revision']['old'] when any tag in REVERT_TAGS is set
           (covers mw-undo / mw-manual-revert / mw-rollback without a parseable
           comment, and non-English revert comments).
         UPDATEs rows where revision_new = that revision.
      2. Mass-rollback by user. When the comment parses as 'Reverted edits by X'
         (typically co-occurs with mw-rollback), UPDATE rows matching
         (item_qid, event_user) within REVERT_LOOKBACK.
    """
    if not db_pool:
        return 0

    parsed = parse_edit_comment(event.get('comment', ''))
    action = parsed.get('action')
    details = parsed.get('details') or {}
    tags = event.get('tags') or ()
    has_revert_tag = any(t in REVERT_TAGS for t in tags)

    undone_rev = details.get('undone_rev_id') if action == 'undo' else None
    if undone_rev is None and has_revert_tag:
        undone_rev = (event.get('revision') or {}).get('old')

    if undone_rev is None and action != 'revert':
        return 0

    total = 0
    try:
        with db_pool.connection() as conn, conn.cursor() as cur:
            if undone_rev is not None:
                cur.execute(
                    """
                    UPDATE flagged_events
                       SET reverted_at = NOW()
                     WHERE revision_new = %s AND reverted_at IS NULL
                    """,
                    (undone_rev,),
                )
                total += cur.rowcount
            if action == 'revert':
                reverted_user = details.get('reverted_user')
                item = event.get('title')
                if reverted_user and item:
                    cur.execute(
                        f"""
                        UPDATE flagged_events
                           SET reverted_at = NOW()
                         WHERE item_qid = %s
                           AND event_user = %s
                           AND reverted_at IS NULL
                           AND processed_timestamp > NOW() - INTERVAL '{REVERT_LOOKBACK}'
                        """,
                        (item, reverted_user),
                    )
                    total += cur.rowcount
        return total
    except Exception as e:
        logger.error(
            f"mark_reverts failed on event {event.get('id')}: {e}", exc_info=True
        )
        return 0
