#!/usr/bin/env python3
import csv
import logging
import os
import time
from datetime import datetime, timezone

import pywikibot
from psycopg_pool import ConnectionPool
from pywikibot.comms.eventstreams import EventStreams
from indicators import (
    large_removal, self_reference_added,
    life_dates_changed, dob_first_century, bad_description,
    high_wp_count_removed, labels_less_consistent, time_travel_edge,
    end_before_beginning, constraint_check_candidate,
)
from db import record_flag, mark_reverts, mark_corrections

logger = logging.getLogger('wdemon')

DB_CONNINFO = "dbname=algae"

# Tier 1 indicators — need only the event dict
TIER1_INDICATORS = [large_removal, self_reference_added, life_dates_changed, dob_first_century, bad_description]

# Tier 2 indicators — also need a psycopg ConnectionPool
TIER2_INDICATORS = [high_wp_count_removed, labels_less_consistent, time_travel_edge, end_before_beginning]

# Measurement-only — silent on stdout, persisted to a CSV file rather than
# flagged_events. Used to size Tier 3 API-call volume before committing.
MEASUREMENT_INDICATORS = {constraint_check_candidate}

ALL_INDICATORS = TIER1_INDICATORS + TIER2_INDICATORS + list(MEASUREMENT_INDICATORS)

CONSTRAINT_LOG_PATH = "constraint_candidates.csv"
CONSTRAINT_LOG_FIELDS = ("event_ts", "rc_id", "qid", "property_id", "action", "has_qid_value")


def _log_measurement(writer, event, result):
    ts = event.get('timestamp')
    event_ts = (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        if isinstance(ts, (int, float)) else ''
    )
    rc_id = event.get('id') or event.get('rc_id') or ''
    writer.writerow([
        event_ts, rc_id,
        result.get('qid', ''),
        result.get('property_id') or '',
        result.get('action', ''),
        '1' if result.get('has_qid_value') else '0',
    ])

def run_wikidata_monitor(db_pool=None, measurement_writer=None):
    """
    Consumes the Wikimedia 'recentchange' stream and filters for Wikidata.
    Runs Tier 1 + Tier 2 indicators on every event and prints any that trigger.
    Measurement indicators (e.g. constraint_check_candidate) are written to
    `measurement_writer` instead of stdout/flagged_events.
    """
    pywikibot.output(">>> Starting Wikidata Recent Changes Monitor...")

    while True:
        try:
            stream = EventStreams(streams='recentchange')
            stream.register_filter(wiki='wikidatawiki')

            pywikibot.output(">>> Connection established. Listening for changes...")

            for event in stream:
                user = event.get('user', 'Unknown User')
                title = event.get('title', 'Unknown Title')
                comment = event.get('comment', 'No comment')
                timestamp = event.get('timestamp', int(time.time()))

                readable_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamp))

                pywikibot.output(f"[{readable_time}] {user}: {title} — {comment}")

                fired = set()
                for indicator in ALL_INDICATORS:
                    try:
                        result = indicator(event, logger=logger, db_pool=db_pool)
                    except Exception as e:
                        logger.warning(f"{indicator.__name__} error on {title}: {e}")
                        continue
                    if not result:
                        continue
                    if indicator in MEASUREMENT_INDICATORS:
                        if measurement_writer is not None:
                            _log_measurement(measurement_writer, event, result)
                        continue
                    fired.add(indicator.__name__)
                    rev = event.get('revision', {}).get('new', '?')
                    pywikibot.output(f"  ⚑ {indicator.__name__} [{title} r{rev}]: {result}")
                    record_flag(db_pool, event, indicator.__name__, result)

                corrected = mark_corrections(db_pool, event, fired)
                if corrected:
                    pywikibot.output(f"  ✓ marked {corrected} row(s) corrected via {user}")

                reverted = mark_reverts(db_pool, event)
                if reverted:
                    pywikibot.output(f"  ↩ marked {reverted} row(s) reverted via {user}")

        except KeyboardInterrupt:
            pywikibot.output("\n>>> Monitor stopped by user.")
            break
        except (ConnectionError, Exception) as e:
            pywikibot.error(f"Stream interrupted: {e}")
            pywikibot.output(">>> Retrying in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    # Ensure pywikibot is configured (requires a user-config.py in the same dir)
    pool = ConnectionPool(conninfo=DB_CONNINFO, min_size=1, max_size=4, open=True)
    need_header = (
        not os.path.exists(CONSTRAINT_LOG_PATH)
        or os.path.getsize(CONSTRAINT_LOG_PATH) == 0
    )
    try:
        with open(CONSTRAINT_LOG_PATH, 'a', buffering=1, newline='') as csv_file:
            writer = csv.writer(csv_file)
            if need_header:
                writer.writerow(CONSTRAINT_LOG_FIELDS)
            run_wikidata_monitor(db_pool=pool, measurement_writer=writer)
    except Exception as fatal_e:
        print(f"Fatal error outside of loop: {fatal_e}")
    finally:
        pool.close()