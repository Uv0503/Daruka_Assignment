from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "app.sqlite3"

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        sql = (Path(__file__).parent / "migrations" / "001_init.sql").read_text()
        with self.connection() as conn:
            conn.executescript(sql)

    def create_session(self) -> dict:
        session_id, site_id, now = str(uuid4()), str(uuid4()), utcnow()
        profile = {"site_id": site_id, "current": {}, "unresolved_conflicts": [], "declined_questions": [], "last_question_fields": [], "asked_question_fields": [], "notes": [], "hypothetical": None}
        with self.connection() as conn:
            conn.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (session_id, site_id, now, now))
            conn.execute("INSERT INTO site_states VALUES (?, ?, ?, 0)", (session_id, json.dumps(profile), "{}"))
        return {"session_id": session_id, "site_id": site_id, "profile": profile}

    def load_state(self, session_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT profile_json, last_event_seq FROM site_states WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        state = json.loads(row["profile_json"])
        state["last_event_seq"] = row["last_event_seq"]
        # Backfill for sessions created before asked_question_fields was added
        state.setdefault("asked_question_fields", [])
        return state

    def save_turn(self, *, session_id: str, state: dict, events: list[dict], turn_id: str, request: dict, response: dict, trace: dict) -> None:
        now = utcnow()
        with self.connection() as conn:
            for event in events:
                conn.execute(
                    "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (event["observation_id"], session_id, event["event_seq"], event["field"], event["operation"], json.dumps(event), turn_id),
                )
            conn.execute("UPDATE site_states SET profile_json=?, summary_json=?, last_event_seq=? WHERE session_id=?", (json.dumps(state), "{}", state["last_event_seq"], session_id))
            conn.execute("UPDATE sessions SET updated_at=? WHERE session_id=?", (now, session_id))
            conn.execute("INSERT INTO turns VALUES (?, ?, ?, ?, ?, ?)", (turn_id, session_id, json.dumps(request), json.dumps(response), response["status"], now))
            conn.execute("INSERT INTO retrieval_traces VALUES (?, ?, ?, ?)", (trace["trace_id"], turn_id, json.dumps(trace), json.dumps(trace.get("timings", {}))))

    def seed_knowledge(self, sources: list[dict], cards: list[dict], passages: dict[str, dict] | None = None) -> None:
        with self.connection() as conn:
            # Knowledge is a replaceable, versioned corpus.  Leaving old rows
            # here would make a newly disabled card visible through SQLite.
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM evidence_cards")
            conn.execute("DELETE FROM sources")
            for source in sources:
                conn.execute("INSERT OR REPLACE INTO sources VALUES (?, ?)", (source["source_id"], json.dumps(source)))
            for chunk_id, passage in (passages or {}).items():
                locator = {"source_id": passage["source_id"], "locator": passage.get("locator"), "section": passage.get("section"), "paragraph_index": passage.get("paragraph_index"), "pdf_page_index": passage.get("pdf_page_index"), "raw_sha256": passage.get("raw_sha256"), "text_sha256": passage.get("text_sha256")}
                conn.execute("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?)", (chunk_id, passage["source_id"], passage.get("parent_id", chunk_id), passage["text"], json.dumps(locator)))
            for card in cards:
                conn.execute("INSERT OR REPLACE INTO evidence_cards VALUES (?, ?, ?, ?)", (card["evidence_id"], card["source_id"], json.dumps(card), card["review_status"]))

    def evidence(self, evidence_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT card_json FROM evidence_cards WHERE evidence_id=?", (evidence_id,)).fetchone()
        return json.loads(row["card_json"]) if row else None

    def knowledge_counts(self) -> dict:
        with self.connection() as conn:
            return {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in ("sources", "chunks", "evidence_cards")}
