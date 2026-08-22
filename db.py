"""SQLite database helpers for MindTrail."""

import json
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "mindtrail.db")


def get_db():
    """Get a database connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thoughts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            audio_path TEXT,
            transcript TEXT,
            summary TEXT,
            topics TEXT,
            entities TEXT,
            mood TEXT,
            key_insights TEXT,
            embedding TEXT,
            raw_response TEXT,
            connections TEXT
        )
    """)
    # Migrate: add connections column if missing (existing DBs)
    try:
        conn.execute("ALTER TABLE thoughts ADD COLUMN connections TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    conn.close()


def save_thought(thought_data: dict) -> int:
    """Save a processed thought and return its ID."""
    conn = get_db()
    conn.execute(
        """
        INSERT INTO thoughts
            (created_at, audio_path, transcript, summary, topics,
             entities, mood, key_insights, embedding, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thought_data.get("created_at", datetime.now().isoformat()),
            thought_data.get("audio_path"),
            thought_data.get("transcript"),
            thought_data.get("summary"),
            json.dumps(thought_data.get("topics", [])),
            json.dumps(thought_data.get("entities", [])),
            thought_data.get("mood"),
            json.dumps(thought_data.get("key_insights", [])),
            json.dumps(thought_data.get("embedding", [])),
            thought_data.get("raw_response"),
        ),
    )
    conn.commit()
    thought_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return thought_id


def _parse_row(row) -> dict:
    """Convert a DB row to a dict with parsed JSON fields."""
    thought = dict(row)
    thought["topics"] = json.loads(thought["topics"] or "[]")
    thought["entities"] = json.loads(thought["entities"] or "[]")
    thought["key_insights"] = json.loads(thought["key_insights"] or "[]")
    return thought


def get_all_thoughts() -> list[dict]:
    """Get all thoughts, newest first. Excludes embeddings."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM thoughts ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    thoughts = []
    for row in rows:
        t = _parse_row(row)
        t.pop("embedding", None)
        t.pop("raw_response", None)
        thoughts.append(t)
    return thoughts


def get_thoughts_with_embeddings() -> list[dict]:
    """Get all thoughts including embeddings (for search/RAG)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM thoughts ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    thoughts = []
    for row in rows:
        t = _parse_row(row)
        t["embedding"] = json.loads(t["embedding"] or "[]")
        thoughts.append(t)
    return thoughts


def get_thought_by_id(thought_id: int) -> dict | None:
    """Get a single thought by ID."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM thoughts WHERE id = ?", (thought_id,)
    ).fetchone()
    conn.close()
    if row:
        t = _parse_row(row)
        t.pop("embedding", None)
        t.pop("raw_response", None)
        return t
    return None


def update_thought_connections(thought_id: int, connections_json: str):
    """Store Connector agent's analysis for a thought."""
    conn = get_db()
    conn.execute(
        "UPDATE thoughts SET connections = ? WHERE id = ?",
        (connections_json, thought_id),
    )
    conn.commit()
    conn.close()


def get_thought_connections(thought_id: int) -> dict | None:
    """Get Connector agent's analysis for a thought."""
    conn = get_db()
    row = conn.execute(
        "SELECT connections FROM thoughts WHERE id = ?", (thought_id,)
    ).fetchone()
    conn.close()
    if row and row["connections"]:
        return json.loads(row["connections"])
    return None
