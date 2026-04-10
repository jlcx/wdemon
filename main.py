#!/usr/bin/env python3
import logging
import time
import pywikibot
from pywikibot.comms.eventstreams import EventStreams
from indicators import ip_edit, temp_edit, large_removal, self_reference_added, life_dates_changed

logger = logging.getLogger('wdemon')

# Tier 1 indicators — need only the event dict
TIER1_INDICATORS = [ip_edit, temp_edit, large_removal, self_reference_added, life_dates_changed]

def run_wikidata_monitor():
    """
    Consumes the Wikimedia 'recentchange' stream and filters for Wikidata.
    Runs Tier 1 indicators on every event and prints any that trigger.
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

                # Run Tier 1 indicators
                for indicator in TIER1_INDICATORS:
                    try:
                        result = indicator(event, logger=logger)
                    except Exception as e:
                        logger.warning(f"{indicator.__name__} error on {title}: {e}")
                        continue
                    if result:
                        rev = event.get('revision', {}).get('new', '?')
                        pywikibot.output(f"  ⚑ {indicator.__name__} [{title} r{rev}]: {result}")

        except (ConnectionError, Exception) as e:
            # Catch network issues or unexpected API errors
            pywikibot.error(f"Stream interrupted: {e}")
            pywikibot.output(">>> Retrying in 10 seconds...")
            time.sleep(10)
        except KeyboardInterrupt:
            # Allow graceful exit via Ctrl+C
            pywikibot.output("\n>>> Monitor stopped by user.")
            break

if __name__ == "__main__":
    # Ensure pywikibot is configured (requires a user-config.py in the same dir)
    try:
        run_wikidata_monitor()
    except Exception as fatal_e:
        print(f"Fatal error outside of loop: {fatal_e}")