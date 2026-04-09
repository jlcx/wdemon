#!/usr/bin/env python3
import time
import pywikibot
from pywikibot.comms.eventstreams import EventStreams

def run_wikidata_monitor():
    """
    Consumes the Wikimedia 'recentchange' stream and filters for Wikidata.
    Includes robust error handling and automatic restarts.
    """
    pywikibot.output(">>> Starting Wikidata Recent Changes Monitor...")
    
    while True:
        try:
            # Initialize the stream for 'recentchange'
            # The 'retry' parameter (in ms) is handled internally by pywikibot/requests-sse,
            # but we wrap it in a while-loop for extra resilience against fatal disconnects.
            stream = EventStreams(streams='recentchange')
            
            # Filter for Wikidata edits specifically
            stream.register_filter(wiki='wikidatawiki')
            
            pywikibot.output(">>> Connection established. Listening for changes...")

            for event in stream:
                # Extract basic info
                user = event.get('user', 'Unknown User')
                title = event.get('title', 'Unknown Title')
                comment = event.get('comment', 'No comment')
                timestamp = event.get('timestamp', int(time.time()))
                
                # Format a short readable timestamp
                readable_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamp))
                
                # Print the summary
                pywikibot.output(f"[{readable_time}] {user}: {title} — {comment}")

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