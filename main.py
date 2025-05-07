#!/usr/bin/env python3
"""
Monitors the Wikidata recent changes stream in real-time, identifies potentially
problematic edits using checks defined in indicators.py, and logs findings.
"""

import json
import multiprocessing as mp
import time
import logging
import os
import datetime # For timestamps
import traceback

# Use modern psycopg (version 3)
import psycopg
import psycopg_pool
from sseclient import SSEClient as EventSource

# Import indicator functions from the separate file
import indicators

tier_1_indicators = (
    indicators.ip_edit,
    indicators.large_removal)
tier_2_indicators = () # may depend on tier 1; may involve local DB queries
tier_3_indicators = () # may depend on tier 1 and/or 2; may involve API calls; use sparingly

# --- Configuration ---
# Load sensitive credentials from environment variables
DB_NAME = os.environ.get("DB_NAME", "wikidata_db") # Example DB name
DB_USER = os.environ.get("DB_USER", "monitor_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password") # Keep passwords out of code!
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")

# Wikidata Stream Configuration
SSE_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
TARGET_WIKI = 'wikidatawiki'
# Consider filtering by relevant event types if needed
# RELEVANT_EVENT_TYPES = {'edit', 'new'} # 'log' events might also be useful

# --- Logging Setup ---
# Configure logging format and level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(processName)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__) # Get logger for the main module

# --- Database Connection Pool (psycopg v3) ---
# Global variable for the pool (use with care across processes if needed,
# but initializing in main and passing connections/using pool in functions is fine)
db_pool = None

def initialize_db_pool():
    """Initializes the PostgreSQL connection pool."""
    global db_pool
    conninfo = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    min_size = 1 # Minimum connections in pool
    max_size = 5 # Maximum connections in pool
    try:
        # Use ConnectionPool for managing connections
        db_pool = psycopg_pool.ConnectionPool(conninfo=conninfo, min_size=min_size, max_size=max_size)
        logger.info(f"Database connection pool initialized (min: {min_size}, max: {max_size})")
    except psycopg.OperationalError as e:
        logger.critical(f"Fatal: Failed to initialize database pool: {e}", exc_info=True)
        db_pool = None # Ensure pool is None if setup fails
        # Consider exiting if the database is essential
        # exit(1)

def close_db_pool():
    """Closes all connections in the pool."""
    if db_pool:
        db_pool.close()
        logger.info("Database connection pool closed.")

def store_flagged_event(db_pool, processed_event, flag_data):
    """
    Inserts a record into the flagged_events table.

    Args:
        db_pool (psycopg_pool.ConnectionPool): The database connection pool.
        processed_event (dict): The dictionary containing processed event data.
        flag_data (dict): The dictionary returned by the triggered indicator function.
    """
    if not db_pool:
        logger.error("Cannot store flagged event: Database pool is not available.")
        return

    sql = """
        INSERT INTO flagged_events (
            rc_id, event_timestamp, item_qid, event_user,
            indicator_name, indicator_details, revision_old, revision_new
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """
    rc_id = processed_event.get('rc_id')
    timestamp_dt = processed_event.get('timestamp_dt') # Already a datetime object
    qid = processed_event.get('title')
    user = processed_event.get('user')
    indicator_name = flag_data.get('indicator', 'unknown_indicator')
    # Convert details dict to JSON string for storing in JSONB field
    details_json = json.dumps(flag_data)
    rev_old = processed_event.get('revision', {}).get('old')
    rev_new = processed_event.get('revision', {}).get('new')

    # Basic validation
    if not rc_id or not indicator_name:
         logger.warning(f"Skipping flag storage: Missing rc_id or indicator_name. Event: {rc_id}")
         return

    conn = None # Initialize conn to None
    try:
        # Get a connection from the pool
        with db_pool.connection() as conn:
            # Use the connection (autocommit is often default or managed by 'with')
            with conn.cursor() as cur:
                cur.execute(sql, (
                    rc_id,
                    timestamp_dt, # Pass datetime object directly
                    qid,
                    user,
                    indicator_name,
                    details_json, # Pass JSON string
                    rev_old,
                    rev_new
                ))
            # No explicit conn.commit() needed typically with psycopg3 pools and 'with'
            logger.debug(f"Successfully stored flag for RC_ID:{rc_id}, Indicator:{indicator_name}")

    except psycopg.Error as e:
        # Catch specific psycopg errors or broader Exception
        logger.error(f"Database error storing flag for RC_ID:{rc_id}, Indicator:{indicator_name}: {e}", exc_info=True)
        # Optional: Rollback if needed and autocommit is off (less common with 'with')
        # if conn:
        #     conn.rollback()
    except Exception as e:
         logger.error(f"Unexpected error storing flag for RC_ID:{rc_id}, Indicator:{indicator_name}: {e}", exc_info=True)
    # The 'with db_pool.connection()' ensures the connection is returned to the pool

# --- Stream Processing Function ---
def check_recent_changes(output_queue):
    """
    Connects to the Wikimedia SSE stream, processes events,
    and puts relevant, structured data onto the output queue.
    Runs in a separate process.
    """
    process_name = mp.current_process().name
    stream_logger = logging.getLogger(process_name) # Logger specific to this process
    stream_logger.info("Stream listener started.")

    while True: # Automatically attempt to reconnect on failure
        stream_logger.info(f"Connecting to SSE stream: {SSE_URL}")
        try:
            # Use a reasonable timeout
            client = EventSource(SSE_URL, timeout=30)
            for event in client:
                if event.event == 'message':
                    try:
                        # Quickly check to avoid excessive errors in non-relevant wikis
                        if TARGET_WIKI not in event.data: # Check if 'wikidatawiki' is roughly in the string
                            logger.debug(f"Skipping non-{TARGET_WIKI} event data snippet: {event.data[:100]}...")
                            continue
                        change = json.loads(event.data)

                        # --- Filter for relevant events ---
                        if change.get('wiki') == TARGET_WIKI:
                            # Optional: Filter by type, e.g.,
                            # if change.get('type') not in RELEVANT_EVENT_TYPES:
                            #     continue

                            # --- Extract key information reliably ---
                            # Convert timestamp to datetime object if possible
                            timestamp = change.get('timestamp')
                            dt_object = None
                            if timestamp:
                                try:
                                    dt_object = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
                                except (TypeError, ValueError):
                                    stream_logger.warning(f"Could not parse timestamp: {timestamp}")

                            processed_event = {
                                'rc_id': change.get('id'), # RecentChanges ID
                                'type': change.get('type'),
                                'namespace': change.get('namespace'),
                                'title': change.get('title'), # Usually the QID for items/props
                                'comment': change.get('comment', ''),
                                'timestamp_unix': timestamp,
                                'timestamp_dt': dt_object, # Datetime object
                                'user': change.get('user'),
                                'patrolled': change.get('patrolled', False),
                                # how to use 'patrolled'?  Exclude entirely, de-prioritize, and/or cancel out less-definite indicators?
                                'bot': change.get('bot', False),
                                'revision': change.get('revision'), # Dict with 'old', 'new' IDs
                                'length': change.get('length'), # Dict with 'old', 'new' byte sizes
                                'meta': change.get('meta'), # Contains dt, uri, stream id, etc.
                                'raw_event': event.data # Keep raw event for debugging if needed (optional)
                            }
                            output_queue.put(processed_event)

                    except json.JSONDecodeError:
                        stream_logger.warning(f"Failed to decode JSON: {event.data[:200]}...") # Log snippet
                        traceback.print_exc()
                        print(event.data)
                    except Exception as e:
                        # Catch other processing errors within the loop
                        stream_logger.error(f"Error processing event data: {e}", exc_info=True)
                        stream_logger.debug(f"Problematic event data: {event.data}")

                elif event.event == 'error':
                    # Log stream-reported errors
                    stream_logger.warning(f"SSE stream error event received: {event.data}")
                    # Consider breaking and reconnecting depending on the error type

        # Handle exceptions during connection or iteration
        except TimeoutError:
            stream_logger.warning("SSE connection timed out, reconnecting in 5s...")
            time.sleep(5)
        except ConnectionError as e:
            stream_logger.warning(f"SSE connection error ({e}), reconnecting in 10s...")
            time.sleep(10)
        except Exception as e:
            # Catch broader exceptions (e.g., from sseclient internal issues)
            stream_logger.error(f"Unhandled exception in SSE stream loop: {e}", exc_info=True)
            stream_logger.info("Attempting to reconnect in 15 seconds...")
            time.sleep(15)


# --- Main Execution Block ---
if __name__ == '__main__':
    logger.info("Starting Wikidata Monitor application...")
    initialize_db_pool()

    # Check if DB pool initialization failed
    if not db_pool:
         logger.critical("Exiting due to database pool initialization failure.")
         exit(1)

    # Use 'spawn' for better cross-platform compatibility if needed, 'fork' is default on Unix
    # mp.set_start_method('spawn')
    event_queue = mp.Queue()

    try:
        print(f"Queue Size: {event_queue.qsize()}")
        queue_size_available = True
    except NotImplementedError:
        logger.info(f"qsize() not available")
        queue_size_available = False

    # Start the stream listener process as a daemon
    # Daemon processes are terminated automatically when the main process exits
    stream_listener_process = mp.Process(
        target=check_recent_changes,
        args=(event_queue,),
        name="StreamListener",
        daemon=True
    )
    stream_listener_process.start()
    logger.info(f"Stream listener process started (PID: {stream_listener_process.pid})")

    processed_count = 0
    flagged_count = 0

    # --- List of indicator functions to run on each event ---
    # Add more functions from indicators.py here as they are created
    active_indicators = [
        indicators.large_removal,
        indicators.self_reference_added,
        indicators.life_dates_changed,
        # indicators.another_check,
        # indicators.check_requiring_db,
    ]

    logger.info(f"Monitoring started with {len(active_indicators)} active indicator(s). Press Ctrl+C to stop.")

    try:
        while True:
            if not event_queue.empty():
                processed_event = event_queue.get()
                processed_count += 1
                event_title = processed_event.get('title', 'N/A')
                rc_id = processed_event.get('rc_id', 'N/A')

                logger.debug(f"Processing event RC_ID:{rc_id} for Title:{event_title}")

                triggered_flags = []
                # --- Run active indicators ---
                for indicator_func in active_indicators:
                    try:
                        # Pass the event data and potentially other needed dependencies
                        # If indicators need DB, pass the pool or manage connections inside
                        # If indicators need logging, pass the logger object
                        result = indicator_func(processed_event, logger=logger, db_pool=db_pool)
                        if result: # Indicator function returns data if triggered
                            triggered_flags.append(result)
                    except Exception as e:
                        # Log errors from individual indicators but continue processing
                        logger.error(f"Error running indicator '{indicator_func.__name__}' for RC_ID:{rc_id}: {e}", exc_info=True)

                # --- Handle results ---
                if triggered_flags:
                    flagged_count += 1
                    logger.warning(f"FLAGS TRIGGERED for Title:{event_title} (RC_ID:{rc_id}): {triggered_flags}")
                    for flag in triggered_flags:
                        store_flagged_event(db_pool, processed_event, flag)

                # Log progress periodically
                if processed_count % 500 == 0:
                    if queue_size_available:
                        logger.info(f"Processed: {processed_count} events. Flagged: {flagged_count}. Queue Size: {event_queue.qsize()}")
                    else:
                        logger.info(f"Processed: {processed_count} events. Flagged: {flagged_count}")

            else:
                # Avoid busy-waiting when the queue is empty
                time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Shutdown signal received (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Unexpected error in main loop: {e}", exc_info=True)
    finally:
        # --- Clean Shutdown ---
        logger.info("Initiating shutdown sequence...")
        # The stream listener is a daemon, so it should exit when main does,
        # but explicit termination can be attempted if needed (less critical for daemons)
        # if stream_listener_process.is_alive():
        #     logger.info("Terminating stream listener process...")
        #     stream_listener_process.terminate()
        #     stream_listener_process.join(timeout=5)

        close_db_pool() # Ensure database connections are closed
        logger.info("Wikidata Monitor stopped.")