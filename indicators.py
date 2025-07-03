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

# --- Helper Functions ---

from utils import parse_edit_comment

# --- Indicator Functions ---

## Tier 1 indicators - only event data needed

def ip_edit(processed_event):
    """
    Checks if the "user" field contains an IP address.
    """
    user = processed_event.get('user', '')
    try:
        return "IPv4" if type(ipaddress.ip_address(user)) is ipaddress.IPv4Address else "IPv6"
    except ValueError:
        return None

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

## Tier 2 indicators - tier 1 results and/or local DB queries needed

def time_travel_edge(processed_event, logger=None, db_pool=None):
    """
    Checks if an edit results in a causal claim pointing back in time.
    """
    # what are we checking for here?  Nodes with dates linked to/from the edited one, I guess
    pass

def high_wp_count_removed(processed_event, logger=None, db_pool=None):
    # statement_wp_count = get_statement_wp_count(statement)
    # do I have one threshold for a high wp_count, or generate a higher score the higher a statement's wp_count was?

    # too much stuff to put in each indicator?  How could we move the DB and logging into something general?

    threshold = 2 # if it's in multiple Wikipedias, maybe that's high enough?

    if not db_pool:
        if logger: logger.warning("DB pool not available for check_something_in_db")
        return None # Cannot perform check without DB pool

    qid = processed_event.get('title')
    if not qid or not qid.startswith('Q'): return None

    conn = None
    try:
        with db_pool.connection() as conn: # Get connection from pool
            with conn.cursor() as cur:
                cur.execute("SELECT wp_count FROM wp_links WHERE qid = %s and dst_qid = %s", (qid, dst_qid))
                result = cur.fetchone()
                if result and result[0] >= threshold: #TODO test
                    if logger: logger.info(f"high_wp_count_removed triggered for {qid}")
                    return {"indicator": "high_wp_count_removed", "details": "Found problematic value"}
    except Exception as e:
        if logger: logger.error(f"DB error in high_wp_count_removed for {qid}: {e}", exc_info=True)
    # No 'finally' needed to return connection when using 'with db_pool.connection()'
    return None

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