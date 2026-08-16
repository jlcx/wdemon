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


def mark_corrections(db_pool, event, fired_indicators):
    """
    For indicators whose domain matches this event's action but which did NOT
    fire on it, mark prior unreverted + uncorrected flagged_events rows on the
    same slot as corrected. Returns total rowcount across indicators.

    Slot mapping per indicator:
      bad_description         -> (item_qid, details->>'lang')   action wbsetdescription-*
      labels_less_consistent  -> (item_qid, details->>'lang')   action wbsetlabel-set

    Known limitation: if a correction is itself later reverted, the bad content
    comes back, but the flag's corrected_at remains set (it is not cleared).
    The report will still treat the flag as resolved in that edge case.
    """
    if not db_pool:
        return 0

    parsed = parse_edit_comment(event.get('comment', ''))
    action = parsed.get('action', '') or ''
    qid = event.get('title')
    lang = parsed.get('language')
    if not qid:
        return 0

    total = 0
    try:
        with db_pool.connection() as conn, conn.cursor() as cur:
            if (action.startswith('wbsetdescription')
                    and 'bad_description' not in fired_indicators
                    and lang):
                cur.execute(
                    """
                    UPDATE flagged_events
                       SET corrected_at = NOW()
                     WHERE indicator_name = 'bad_description'
                       AND item_qid = %s
                       AND (indicator_details->>'lang') = %s
                       AND reverted_at IS NULL
                       AND corrected_at IS NULL
                    """,
                    (qid, lang),
                )
                total += cur.rowcount

            if (action == 'wbsetlabel-set'
                    and 'labels_less_consistent' not in fired_indicators
                    and lang):
                cur.execute(
                    """
                    UPDATE flagged_events
                       SET corrected_at = NOW()
                     WHERE indicator_name = 'labels_less_consistent'
                       AND item_qid = %s
                       AND (indicator_details->>'lang') = %s
                       AND reverted_at IS NULL
                       AND corrected_at IS NULL
                    """,
                    (qid, lang),
                )
                total += cur.rowcount
        return total
    except Exception as e:
        logger.error(
            f"mark_corrections failed on event {event.get('id')}: {e}", exc_info=True
        )
        return 0


def mark_reverts(db_pool, event):
    """
    If `event` looks like an undo/restore/revert, mark matching flagged_events
    rows as reverted and return the total rowcount across strategies. Returns 0
    on no match, error, or non-revert events.

    Note: the recentchange stream carries no `tags` field, so detection relies
    entirely on the edit comment. All three forms below are produced verbatim
    by MediaWiki/Wikibase; undo and restore are language-independent.

    Strategies (combined; a row reverted_at by one is skipped by the next):
      1. Undo: '/* undo:0||<rev>|<user> */' (or English 'Undo revision N')
         names the exact revision being undone. UPDATEs rows where
         revision_new = that revision.
      2. Restore: '/* restore:0||<rev>|<user> */' restores the item to <rev>,
         wiping every later revision. UPDATEs rows on the same item where
         revision_new > <rev> (revision ids are monotonic).
      3. Mass-rollback by user: 'Reverted edits by X'. UPDATEs rows matching
         (item_qid, event_user) within REVERT_LOOKBACK.
    """
    if not db_pool:
        return 0

    parsed = parse_edit_comment(event.get('comment', ''))
    action = parsed.get('action')
    details = parsed.get('details') or {}

    undone_rev = details.get('undone_rev_id') if action == 'undo' else None
    restored_rev = details.get('restored_rev_id') if action == 'restore' else None

    if undone_rev is None and restored_rev is None and action != 'revert':
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
            if restored_rev is not None and event.get('title'):
                cur.execute(
                    """
                    UPDATE flagged_events
                       SET reverted_at = NOW()
                     WHERE item_qid = %s
                       AND revision_new > %s
                       AND reverted_at IS NULL
                    """,
                    (event['title'], restored_rev),
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
