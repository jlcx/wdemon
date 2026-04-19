#!/usr/bin/env python3
"""
Collection of functions (indicators) to detect potentially problematic changes
in Wikidata events. Each function should accept a processed event dictionary
and optionally other dependencies (like logger, db_pool).
They should return None if the indicator is not triggered, or a dictionary
describing the triggered flag if it is.
"""

import logging
import ipaddress
import re
import string

TEMP_ACCOUNT_PATTERN = re.compile(r"^~20\d{2}(?:-\d{1,5})+$")
FIRST_CENTURY_DATE = re.compile(r'\b(\d{1,2})\s+CE\b')

# --- Helper Functions ---

from utils import parse_edit_comment

# --- Indicator Functions ---

## Tier 1 indicators - only event data needed

# description indicators needed: see ideas in descgusting.py

# where to put indicators needing full item data, e.g. labels_less_consistent?

def ip_edit(processed_event, logger=None, db_pool=None):
    """
    Checks if the "user" field contains an IP address.
    """
    user = processed_event.get('user', '')
    try:
        return "IPv4" if type(ipaddress.ip_address(user)) is ipaddress.IPv4Address else "IPv6"
    except ValueError:
        return None

def temp_edit(processed_event, logger=None, db_pool=None):
    """
    Checks if the "user" field contains a Wikimedia temporary account identifier
    """
    user = processed_event.get('user', '')
    return bool(TEMP_ACCOUNT_PATTERN.match(user))


def large_removal(processed_event, logger=None, db_pool=None, removal_threshold_bytes=2500):
    """
    Checks if an edit resulted in a large removal of content (bytes).

    Args:
        processed_event (dict): The structured event data from the stream.
        logger (logging.Logger, optional): Logger instance for internal logging.
        db_pool (psycopg.pool.ConnectionPool, optional): DB pool if needed (not used here).
        removal_threshold_bytes (int): Minimum bytes removed to trigger. Defaults to 1000.

    Returns:
        dict or None: Dictionary with indicator details if triggered, else None.
    """
    length_data = processed_event.get('length')
    indicator_name = "large_removal"

    if not length_data:
        # Cannot determine length change
        return None

    old_len = length_data.get('old')
    new_len = length_data.get('new')

    # Check if lengths are valid integers
    if not isinstance(old_len, int) or not isinstance(new_len, int):
        if logger:
            # Log only if logger was passed
            logger.debug(f"{indicator_name}: Invalid or missing length data in event for {processed_event.get('title')}")
        return None

    bytes_removed = old_len - new_len

    if bytes_removed >= removal_threshold_bytes:
        if logger:
            logger.info(f"{indicator_name} triggered for {processed_event.get('title')} (RC_ID: {processed_event.get('rc_id')}): {bytes_removed} bytes removed.")

        # Return structured information about the flag
        return {
            "indicator": indicator_name,
            "threshold": removal_threshold_bytes,
            "bytes_removed": bytes_removed,
            "details": f"Removed {bytes_removed} bytes (threshold: {removal_threshold_bytes})"
        }
    else:
        # Removal was below threshold
        return None

def self_reference_added(processed_event, logger=None, db_pool=None):
    # TODO determine if this should be self_reference_added_t1 or something,
    # and then have a t3 version if the comment indicates that the item should be checked
    indicator_name = "self_reference_added"
    title = processed_event['title']
    parsed_comment = parse_edit_comment(processed_event['comment'])
    details = parsed_comment.get('details', {})
    pid = parsed_comment.get('property_id', {})
    if 'claim_value_qid' in details and details['claim_value_qid'] == title:
        return {
            "indicator": indicator_name,
            "details": f"Self-reference added: {title} {pid} {title}"
        }
    else:
        return None

# TODO what about a more general "date changed"?  what about a more specific "date changed to" (e.g. 2001-9-11)?  how should these be organized?

def life_dates_changed(processed_event, logger=None, db_pool=None):
    """
    Checks if an edit changed dates of birth (P569), death (P570), or other life dates
    """
    # TODO figure out how to approach other beginnings and endings; it's not all people, people!
    indicator_name = "life_dates_changed"
    date_props = ("P569", "P570")
    title = processed_event['title']
    parsed_comment = parse_edit_comment(processed_event['comment'])
    pid = parsed_comment.get('property_id', {})
    if pid in date_props:
        # logger.info("well, that's interesting")
        return {
            "indicator": indicator_name,
            "details": f"Property {pid} changed on {title}"
        }
    else:
        return None

BAD_DESC_ARTICLES = ('a ', 'an ', 'the ')
BAD_DESC_AD_WORDS = ('Discover ', 'Enjoy ', 'Indulge ', 'Book ', 'Reserve ', 'Buy ', 'Get ', 'Hire ')
# First-word proper adjectives that legitimately start English descriptions.
# Extend as needed; keep alphabetized for easy editing.
PROPER_ADJECTIVES = frozenset({
    'American', 'Argentine', 'Argentinian', 'Australian', 'Brazilian',
    'British', 'Canadian', 'Chinese', 'Dutch', 'Egyptian', 'English',
    'French', 'German', 'Greek', 'Indian', 'Irish', 'Italian',
    'Japanese', 'Korean', 'Mexican', 'Nigerian', 'Norwegian', 'Polish',
    'Russian', 'Scottish', 'Spanish', 'Swedish', 'Turkish', 'Welsh',
})

def _first_word(desc):
    return desc.split(' ', 1)[0] if desc else ''

def _balanced_trailing_paren(desc):
    return desc.endswith(')') and desc.count('(') == desc.count(')')

def _len_score(desc):
    return max(0.0, (len(desc) - 42) * 0.02)

# Each rule: score(desc) -> float (0 = no fire), optional suppress_if(desc) -> bool.
# Weights are independent; total >= threshold triggers the indicator.
BAD_DESC_RULES = [
    {"name": "too_long",              "score": _len_score},
    {"name": "starts_capitalized",    "score": lambda d: 1.0 if d and d[0].isupper() else 0.0,
                                      "suppress_if": lambda d: _first_word(d) in PROPER_ADJECTIVES},
    {"name": "ends_with_punctuation", "score": lambda d: 1.0 if d and d[-1] in string.punctuation else 0.0,
                                      "suppress_if": _balanced_trailing_paren},
    {"name": "starts_with_article",   "score": lambda d: 1.0 if d.lower().startswith(BAD_DESC_ARTICLES) else 0.0},
    {"name": "ad_language",           "score": lambda d: 1.0 if any(w in d for w in BAD_DESC_AD_WORDS) else 0.0},
    {"name": "contains_trademark",    "score": lambda d: 1.0 if ('\u00ae' in d or '\u2122' in d) else 0.0},
    {"name": "double_space",          "score": lambda d: 0.5 if '  ' in d else 0.0},
    {"name": "space_before_comma",    "score": lambda d: 0.5 if ' ,' in d else 0.0},
    {"name": "html_escape",           "score": lambda d: 1.0 if ('&amp;' in d or '&lt;' in d or '&gt;' in d or '&quot;' in d) else 0.0},
]
BAD_DESC_THRESHOLD = 2.0

def bad_description(processed_event, logger=None, db_pool=None, threshold=BAD_DESC_THRESHOLD):
    """
    Flags description edits whose weighted score across BAD_DESC_RULES reaches
    `threshold`. Each rule contributes a float; some have suppress_if exceptions.
    """
    indicator_name = "bad_description"
    parsed_comment = parse_edit_comment(processed_event.get('comment', ''))
    if not parsed_comment.get('action', '').startswith('wbsetdescription'):
        return None
    desc = parsed_comment.get('details', {}).get('manual_comment_part', '')
    if not desc:
        return None

    issues = []
    total = 0.0
    for rule in BAD_DESC_RULES:
        suppress = rule.get('suppress_if')
        if suppress and suppress(desc):
            continue
        s = rule['score'](desc)
        if s > 0:
            issues.append({"name": rule['name'], "score": round(s, 2)})
            total += s

    if total < threshold:
        return None

    title = processed_event.get('title', '?')
    breakdown = ', '.join(f"{i['name']}={i['score']}" for i in issues)
    return {
        "indicator": indicator_name,
        "score": round(total, 2),
        "threshold": threshold,
        "issues": issues,
        "details": f"{title}: score={round(total, 2)} ({breakdown})",
    }

def dob_first_century(processed_event, logger=None, db_pool=None):
    """
    Flags edits that set date of birth (P569) to a first-century value (years 1-99 CE).
    These are almost always mistakes — someone entering a day or month number as the year.
    """
    indicator_name = "dob_first_century"
    parsed_comment = parse_edit_comment(processed_event.get('comment', ''))
    trailing = parsed_comment.get('details', {}).get('manual_comment_part', '')
    # property_id may be None when the value isn't a QID link (e.g. dates),
    # so also check for P569 directly in the trailing text
    pid = parsed_comment.get('property_id')
    if pid != 'P569' and '[[Property:P569]]' not in trailing:
        return None
    m = FIRST_CENTURY_DATE.search(trailing)
    if m:
        year = int(m.group(1))
        title = processed_event.get('title', '?')
        return {
            "indicator": indicator_name,
            "details": f"P569 on {title} set to year {year} CE"
        }
    return None

## Tier 2 indicators - tier 1 results and/or local DB queries needed

def time_travel_edge(processed_event, logger=None, db_pool=None):
    """
    Checks if an edit results in a causal claim pointing back in time.
    """
    # what are we checking for here?  Nodes with dates linked to/from the edited one, I guess
    pass

PROP_QID_TRAILING = re.compile(r'\[\[Property:(P\d+)\]\]:\s*\[\[(Q\d+)\]\]', re.IGNORECASE)

def high_wp_count_removed(processed_event, logger=None, db_pool=None, threshold=2):
    """
    Flags claim removals where the removed src→dst edge has a high Wikipedia
    co-occurrence count in wp_links. Default threshold=2 (present in ≥2 wikis).
    """
    indicator_name = "high_wp_count_removed"
    if not db_pool:
        if logger:
            logger.debug(f"{indicator_name}: db_pool not provided")
        return None

    src_qid = processed_event.get('title')
    if not src_qid or not src_qid.startswith('Q'):
        return None

    comment = processed_event.get('comment', '')
    parsed = parse_edit_comment(comment)
    if not parsed.get('action', '').startswith('wbremoveclaims'):
        return None

    dst_qid = parsed.get('details', {}).get('claim_value_qid')
    pid = parsed.get('property_id')
    if not dst_qid:
        # remove-claim comments carry the target as trailing "[[Property:Pxx]]: [[Qyy]]";
        # parse_edit_comment's remove branch doesn't capture it, so do it here.
        m = PROP_QID_TRAILING.search(comment)
        if m:
            pid = pid or m.group(1).upper()
            dst_qid = m.group(2).upper()
    if not dst_qid:
        return None

    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT wp_count FROM wp_links WHERE src = %s AND dst = %s",
                    (src_qid, dst_qid),
                )
                row = cur.fetchone()
    except Exception as e:
        if logger:
            logger.error(
                f"{indicator_name} DB error for {src_qid}->{dst_qid}: {e}",
                exc_info=True,
            )
        return None

    if not row or row[0] is None or row[0] < threshold:
        return None

    wp_count = row[0]
    if logger:
        logger.info(
            f"{indicator_name}: {src_qid} {pid} {dst_qid} (wp_count={wp_count})"
        )
    return {
        "indicator": indicator_name,
        "src": src_qid,
        "dst": dst_qid,
        "property_id": pid,
        "wp_count": wp_count,
        "threshold": threshold,
        "details": f"Removed {src_qid} {pid} {dst_qid} with wp_count={wp_count}",
    }

## Tier 3 indicators - web API calls needed

# What goes here again?  Can I classify some of my live_monitor.py indicators here?

# --- Add other indicator functions below ---
# Example structure for an indicator needing DB access:
#
# def check_something_in_db(processed_event, logger=None, db_pool=None):
#     if not db_pool:
#         if logger: logger.warning("DB pool not available for check_something_in_db")
#         return None # Cannot perform check without DB pool
#
#     qid = processed_event.get('title')
#     if not qid or not qid.startswith('Q'): return None
#
#     conn = None
#     try:
#         with db_pool.connection() as conn: # Get connection from pool
#             with conn.cursor() as cur:
#                 cur.execute("SELECT some_value FROM some_table WHERE qid = %s", (qid,))
#                 result = cur.fetchone()
#                 if result and result[0] == 'problematic_value':
#                     if logger: logger.info(f"check_something_in_db triggered for {qid}")
#                     return {"indicator": "check_something_in_db", "details": "Found problematic value"}
#     except Exception as e:
#         if logger: logger.error(f"DB error in check_something_in_db for {qid}: {e}", exc_info=True)
#     # No 'finally' needed to return connection when using 'with db_pool.connection()'
#     return None
