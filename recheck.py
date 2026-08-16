"""
API-based recheck of active flagged_events rows.

The stream-side listeners (db.mark_reverts / db.mark_corrections) only see
events while the monitor is running and only understand a few edit-comment
shapes. This module answers "is the flagged issue still live?" directly from
the Wikidata API, so it catches reverts made while the monitor was down and
fixes made through edit paths the stream listeners don't watch.

Two checks, both batched (50 per request):
  1. Revert check (all indicators): MediaWiki retroactively tags reverted
     revisions with 'mw-reverted', regardless of revert method or UI language.
     Revisions the API reports as bad (deleted item, suppressed revision) also
     count as no longer live.
  2. Term check (bad_description, labels_less_consistent): fetch the item's
     current label/description and test whether the flagged issue is still
     present; if not, mark the row corrected.
"""
import logging
from collections import defaultdict

import requests

from indicators import score_description, BAD_DESC_THRESHOLD

logger = logging.getLogger(__name__)

API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "wdemon/0.1 (https://github.com/jlcx/wdemon)"
API_BATCH = 50
DEFAULT_MAX_ROWS = 500
TERM_INDICATORS = ('bad_description', 'labels_less_consistent')


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _api_get(session, params):
    resp = session.get(API_URL, params={**params, 'format': 'json',
                                        'formatversion': '2', 'maxlag': '5'},
                       timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if 'error' in data:
        raise RuntimeError(f"API error: {data['error'].get('code')}")
    return data


def _check_reverted(session, rows):
    """Returns (set of flag ids whose revision_new is reverted/gone, error count)."""
    by_rev = defaultdict(list)
    for r in rows:
        if r['revision_new']:
            by_rev[r['revision_new']].append(r['id'])

    reverted, errors = set(), 0
    for chunk in _chunks(list(by_rev), API_BATCH):
        try:
            data = _api_get(session, {
                'action': 'query',
                'prop': 'revisions',
                'revids': '|'.join(str(rev) for rev in chunk),
                'rvprop': 'ids|tags',
            })
        except Exception as e:
            logger.warning(f"recheck revision query failed: {e}")
            errors += 1
            continue
        query = data.get('query', {})
        for page in query.get('pages', []):
            for rev in page.get('revisions', []):
                if 'mw-reverted' in rev.get('tags', ()):
                    reverted.update(by_rev[rev['revid']])
        # Deleted/suppressed revisions: the flagged content is no longer live.
        for bad in query.get('badrevids', {}).values():
            rev = bad.get('revid')
            if rev in by_rev:
                reverted.update(by_rev[rev])
    return reverted, errors


def _term_issue_gone(row, entity):
    """True if the flagged label/description issue is no longer present."""
    details = row['indicator_details'] or {}
    lang = details.get('lang')
    if not lang:
        return False

    if row['indicator_name'] == 'labels_less_consistent':
        bad_label = details.get('new_label')
        if bad_label is None:
            return False
        current = (entity.get('labels', {}).get(lang) or {}).get('value')
        return current != bad_label

    if row['indicator_name'] == 'bad_description':
        current = (entity.get('descriptions', {}).get(lang) or {}).get('value')
        if not current:
            return True  # description removed
        total, _ = score_description(current, lang)
        return total < details.get('threshold', BAD_DESC_THRESHOLD)

    return False


def _check_terms(session, rows):
    """Returns (set of flag ids whose term issue is gone, error count)."""
    by_qid = defaultdict(list)
    for r in rows:
        qid = r['item_qid']
        if qid and r['indicator_name'] in TERM_INDICATORS and not qid.startswith(
                ('Property:', 'Lexeme:', 'EntitySchema:')):
            by_qid[qid].append(r)

    corrected, errors = set(), 0
    for chunk in _chunks(list(by_qid), API_BATCH):
        try:
            data = _api_get(session, {
                'action': 'wbgetentities',
                'ids': '|'.join(chunk),
                'props': 'labels|descriptions',
            })
        except Exception as e:
            logger.warning(f"recheck entity query failed: {e}")
            errors += 1
            continue
        entities = data.get('entities', {})
        for qid in chunk:
            entity = entities.get(qid)
            # Skip missing/redirected items: the revert check is the authority
            # on whether their flagged revisions are still live.
            if not entity or 'missing' in entity:
                continue
            for row in by_qid[qid]:
                if _term_issue_gone(row, entity):
                    corrected.add(row['id'])
    return corrected, errors


def recheck_flags(db_pool, ids=None, max_rows=DEFAULT_MAX_ROWS):
    """
    Rechecks active flags (optionally restricted to `ids`) against the live
    API and stamps reverted_at / corrected_at on rows whose issue is gone.
    Returns {"checked", "reverted", "corrected", "api_errors"} where reverted/
    corrected are lists of flag ids updated.
    """
    with db_pool.connection() as conn, conn.cursor() as cur:
        sql = """
            SELECT id, item_qid, indicator_name, indicator_details, revision_new
              FROM flagged_events
             WHERE reverted_at IS NULL AND corrected_at IS NULL
        """
        params = []
        if ids:
            sql += " AND id = ANY(%s)"
            params.append(list(ids))
        sql += " ORDER BY id DESC LIMIT %s"
        params.append(max_rows)
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, rec)) for rec in cur.fetchall()]

    if not rows:
        return {"checked": 0, "reverted": [], "corrected": [], "api_errors": 0}

    session = requests.Session()
    session.headers['User-Agent'] = USER_AGENT

    reverted, rev_errors = _check_reverted(session, rows)
    remaining = [r for r in rows if r['id'] not in reverted]
    corrected, term_errors = _check_terms(session, remaining)

    with db_pool.connection() as conn, conn.cursor() as cur:
        if reverted:
            cur.execute(
                """
                UPDATE flagged_events SET reverted_at = NOW()
                 WHERE id = ANY(%s) AND reverted_at IS NULL AND corrected_at IS NULL
                """,
                (list(reverted),),
            )
        if corrected:
            cur.execute(
                """
                UPDATE flagged_events SET corrected_at = NOW()
                 WHERE id = ANY(%s) AND reverted_at IS NULL AND corrected_at IS NULL
                """,
                (list(corrected),),
            )

    return {
        "checked": len(rows),
        "reverted": sorted(reverted),
        "corrected": sorted(corrected),
        "api_errors": rev_errors + term_errors,
    }
