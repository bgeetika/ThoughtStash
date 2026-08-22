"""SQLite database helpers for ThoughtStash — Long-Horizon Memory Architecture.

Tables:
- thoughts: raw episodic recordings and structured thoughts
- themes: durable, evolving cross-session themes
- daily_rollups: aggregated daily memory summaries
"""

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
    """Initialize schema with durability and hierarchical memory tables."""
    conn = get_db()
    
    # 1. Thoughts table (Raw episodic memory)
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
            thought_type TEXT,
            urgency TEXT,
            implicit_questions TEXT,
            latitude REAL,
            longitude REAL,
            location_name TEXT,
            embedding TEXT,
            embedding_model TEXT,
            status TEXT DEFAULT 'completed',
            connections TEXT,
            raw_response TEXT
        )
    """)

    # 2. Themes table (Durable, evolving memory abstractions)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS themes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            frequency INTEGER DEFAULT 1,
            trend TEXT DEFAULT 'growing',
            first_seen TEXT,
            last_seen TEXT,
            associated_thought_ids TEXT
        )
    """)

    # 3. Daily Rollups (Hierarchical summarization layer)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_rollups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            summary TEXT,
            key_takeaways TEXT,
            thought_count INTEGER DEFAULT 0,
            mood_summary TEXT,
            locations_visited TEXT
        )
    """)

    # Migrations for existing databases
    alter_cols = [
        ("thoughts", "thought_type", "TEXT"),
        ("thoughts", "urgency", "TEXT"),
        ("thoughts", "implicit_questions", "TEXT"),
        ("thoughts", "embedding_model", "TEXT"),
        ("thoughts", "status", "TEXT DEFAULT 'completed'"),
        ("thoughts", "connections", "TEXT"),
        ("thoughts", "latitude", "REAL"),
        ("thoughts", "longitude", "REAL"),
        ("thoughts", "location_name", "TEXT"),
    ]
    for table, col, col_type in alter_cols:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.commit()
    conn.close()


# ── Thoughts CRUD & Durability ──────────────────────────────────────


def create_pending_thought(audio_path: str, created_at: str, lat: float | None = None, lon: float | None = None, loc_name: str | None = None) -> int:
    """Save an initial pending thought record immediately so audio is NEVER orphaned."""
    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO thoughts (created_at, audio_path, latitude, longitude, location_name, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
        """,
        (created_at, audio_path, lat, lon, loc_name),
    )
    conn.commit()
    thought_id = cursor.lastrowid
    conn.close()
    return thought_id


def save_thought(thought_data: dict) -> int:
    """Save or update a processed thought."""
    conn = get_db()
    existing_id = thought_data.get("id")

    if existing_id:
        conn.execute(
            """
            UPDATE thoughts SET
                created_at = ?,
                audio_path = ?,
                transcript = ?,
                summary = ?,
                topics = ?,
                entities = ?,
                mood = ?,
                key_insights = ?,
                thought_type = ?,
                urgency = ?,
                implicit_questions = ?,
                latitude = ?,
                longitude = ?,
                location_name = ?,
                embedding = ?,
                embedding_model = ?,
                status = 'completed',
                raw_response = ?
            WHERE id = ?
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
                thought_data.get("thought_type", "reflection"),
                thought_data.get("urgency", "low"),
                json.dumps(thought_data.get("implicit_questions", [])),
                thought_data.get("latitude"),
                thought_data.get("longitude"),
                thought_data.get("location_name"),
                json.dumps(thought_data.get("embedding", [])),
                thought_data.get("embedding_model", "gemini-embedding-001"),
                thought_data.get("raw_response"),
                existing_id,
            ),
        )
        thought_id = existing_id
    else:
        cursor = conn.execute(
            """
            INSERT INTO thoughts
                (created_at, audio_path, transcript, summary, topics,
                 entities, mood, key_insights, thought_type, urgency,
                 implicit_questions, latitude, longitude, location_name,
                 embedding, embedding_model, status, raw_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
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
                thought_data.get("thought_type", "reflection"),
                thought_data.get("urgency", "low"),
                json.dumps(thought_data.get("implicit_questions", [])),
                thought_data.get("latitude"),
                thought_data.get("longitude"),
                thought_data.get("location_name"),
                json.dumps(thought_data.get("embedding", [])),
                thought_data.get("embedding_model", "gemini-embedding-001"),
                thought_data.get("raw_response"),
            ),
        )
        thought_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return thought_id


def mark_thought_failed(thought_id: int, error_message: str):
    """Mark thought as failed with error reason."""
    conn = get_db()
    conn.execute(
        "UPDATE thoughts SET status = 'failed_transcription', raw_response = ? WHERE id = ?",
        (error_message, thought_id),
    )
    conn.commit()
    conn.close()


def _parse_row(row) -> dict:
    """Convert a DB row to a dict with parsed JSON fields."""
    thought = dict(row)
    thought["topics"] = json.loads(thought.get("topics") or "[]")
    thought["entities"] = json.loads(thought.get("entities") or "[]")
    thought["key_insights"] = json.loads(thought.get("key_insights") or "[]")
    thought["implicit_questions"] = json.loads(thought.get("implicit_questions") or "[]")
    return thought


def get_all_thoughts(status: str | None = "completed") -> list[dict]:
    """Get all thoughts, newest first."""
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM thoughts WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    else:
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
    """Get completed thoughts including embeddings (for search/RAG)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM thoughts WHERE status = 'completed' ORDER BY created_at DESC"
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
        try:
            return json.loads(row["connections"])
        except json.JSONDecodeError:
            return None
    return None


# ── Durable Themes Layer (Long-Horizon Memory) ──────────────────────


def upsert_theme(name: str, description: str, trend: str, thought_id: int, timestamp: str):
    """Upsert a durable theme with associated thoughts."""
    conn = get_db()
    row = conn.execute("SELECT * FROM themes WHERE name = ?", (name,)).fetchone()
    if row:
        ids = json.loads(row["associated_thought_ids"] or "[]")
        if thought_id not in ids:
            ids.append(thought_id)
        conn.execute(
            """
            UPDATE themes SET
                description = ?,
                frequency = frequency + 1,
                trend = ?,
                last_seen = ?,
                associated_thought_ids = ?
            WHERE name = ?
            """,
            (description, trend, timestamp, json.dumps(ids), name),
        )
    else:
        conn.execute(
            """
            INSERT INTO themes (name, description, frequency, trend, first_seen, last_seen, associated_thought_ids)
            VALUES (?, ?, 1, ?, ?, ?, ?)
            """,
            (name, description, trend, timestamp, timestamp, json.dumps([thought_id])),
        )
    conn.commit()
    conn.close()


def get_all_themes() -> list[dict]:
    """Get all persistent themes ordered by frequency."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM themes ORDER BY frequency DESC, last_seen DESC"
    ).fetchall()
    conn.close()
    themes = []
    for row in rows:
        t = dict(row)
        t["associated_thought_ids"] = json.loads(t["associated_thought_ids"] or "[]")
        themes.append(t)
    return themes


# ── Daily Rollups Layer ─────────────────────────────────────────────


def upsert_daily_rollup(date_str: str, summary: str, takeaways: list[str], count: int, mood_summary: str, locations: list[str]):
    """Store or update daily rollup summary."""
    conn = get_db()
    conn.execute(
        """
        INSERT INTO daily_rollups (date, summary, key_takeaways, thought_count, mood_summary, locations_visited)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            summary = excluded.summary,
            key_takeaways = excluded.key_takeaways,
            thought_count = excluded.thought_count,
            mood_summary = excluded.mood_summary,
            locations_visited = excluded.locations_visited
        """,
        (
            date_str,
            summary,
            json.dumps(takeaways),
            count,
            mood_summary,
            json.dumps(locations),
        ),
    )
    conn.commit()
    conn.close()


def get_recent_daily_rollups(limit: int = 30) -> list[dict]:
    """Get recent daily rollups."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM daily_rollups ORDER BY date DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    rollups = []
    for row in rows:
        r = dict(row)
        r["key_takeaways"] = json.loads(r["key_takeaways"] or "[]")
        r["locations_visited"] = json.loads(r["locations_visited"] or "[]")
        rollups.append(r)
    return rollups
