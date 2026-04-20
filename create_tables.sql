-- SQL command to create the table for flagged events
CREATE TABLE flagged_events (
    id SERIAL PRIMARY KEY,                     -- Auto-incrementing primary key
    rc_id BIGINT NOT NULL,                     -- RecentChanges ID from Wikimedia stream
    event_timestamp TIMESTAMPTZ,               -- Timestamp from the event (with timezone)
    processed_timestamp TIMESTAMPTZ DEFAULT NOW(), -- When the flag was recorded by this script
    item_qid VARCHAR(20),                      -- Wikidata item/property ID (e.g., Q42)
    event_user VARCHAR(255),                   -- User who made the change
    indicator_name VARCHAR(100) NOT NULL,      -- Name of the indicator that triggered (e.g., 'large_removal')
    indicator_details JSONB,                   -- Store the details dict from the indicator as JSONB
    revision_old BIGINT,                       -- Old revision ID (if available)
    revision_new BIGINT,                       -- New revision ID (if available)
    reverted_at TIMESTAMPTZ,                   -- When a revert/undo of revision_new was observed; NULL = still standing
    corrected_at TIMESTAMPTZ                   -- When a subsequent non-flagging edit on the same slot fixed the content; NULL = not corrected
    -- Optional: Add an index for faster querying on rc_id or item_qid
    -- CREATE INDEX idx_flagged_events_rc_id ON flagged_events(rc_id);
    -- CREATE INDEX idx_flagged_events_item_qid ON flagged_events(item_qid);
);

-- Index used by the stream-side revert listener to match an Undo on a specific revision.
CREATE INDEX idx_flagged_events_revision_new_active
    ON flagged_events(revision_new)
    WHERE reverted_at IS NULL;

COMMENT ON COLUMN flagged_events.rc_id IS 'RecentChanges ID from Wikimedia stream';
COMMENT ON COLUMN flagged_events.event_timestamp IS 'Timestamp from the event (with timezone)';
COMMENT ON COLUMN flagged_events.processed_timestamp IS 'When the flag was recorded by this script';
COMMENT ON COLUMN flagged_events.item_qid IS 'Wikidata item/property ID (e.g., Q42)';
COMMENT ON COLUMN flagged_events.event_user IS 'User who made the change';
COMMENT ON COLUMN flagged_events.indicator_name IS 'Name of the indicator that triggered';
COMMENT ON COLUMN flagged_events.indicator_details IS 'Details dict from the indicator function';
COMMENT ON COLUMN flagged_events.revision_old IS 'Old revision ID (if available)';
COMMENT ON COLUMN flagged_events.revision_new IS 'New revision ID (if available)';
COMMENT ON COLUMN flagged_events.reverted_at IS 'Set when a subsequent stream event undoes revision_new; NULL = not yet reverted';
COMMENT ON COLUMN flagged_events.corrected_at IS 'Set when a subsequent non-flagging edit on the same slot (e.g. (item_qid, lang) for description flags) fixes the content; NULL = not yet corrected';