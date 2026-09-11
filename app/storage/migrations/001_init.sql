PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS site_states (
  session_id TEXT PRIMARY KEY REFERENCES sessions(session_id), profile_json TEXT NOT NULL,
  summary_json TEXT NOT NULL, last_event_seq INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
  observation_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id), event_seq INTEGER NOT NULL,
  field TEXT NOT NULL, operation TEXT NOT NULL, payload_json TEXT NOT NULL, turn_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
  turn_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id), input_json TEXT NOT NULL,
  output_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (source_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chunks (chunk_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, parent_id TEXT NOT NULL, text TEXT NOT NULL, locator_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence_cards (evidence_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, card_json TEXT NOT NULL, review_status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS retrieval_traces (trace_id TEXT PRIMARY KEY, turn_id TEXT NOT NULL, trace_json TEXT NOT NULL, timings_json TEXT NOT NULL);
