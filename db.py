"""SQLite database helpers for ThoughtStash — Long-Horizon Memory Architecture.

Tables:
- thoughts: raw episodic recordings and structured thoughts
- themes: durable, evolving cross-session themes
- daily_rollups: aggregated daily memory summaries
- conversations: persisted chat sessions with pinned context
- messages: turn-by-turn chat messages
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
import numpy as np

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "mindtrail.db")


def get_db():
    """Get a database connection with WAL mode and 30s busy timeout."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except sqlite3.OperationalError:
        pass
    conn.row_factory = sqlite3.Row
    return conn


def cosine(a, b) -> float:
    """Canonical, safe cosine similarity between two vector embeddings."""
    if not a or not b or len(a) != len(b):
        return 0.0
    arr_a = np.array(a, dtype=float)
    arr_b = np.array(b, dtype=float)
    norm_a = np.linalg.norm(arr_a)
    norm_b = np.linalg.norm(arr_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(arr_a, arr_b) / (norm_a * norm_b + 1e-8))


def normalize_timestamp(ts: str | None = None) -> str:
    """Normalize any timestamp string to standard ISO UTC format."""
    if not ts or not str(ts).strip():
        return datetime.now(timezone.utc).isoformat()
    ts_str = str(ts).strip()
    try:
        # Handle numeric epoch timestamps
        if ts_str.replace(".", "", 1).isdigit():
            epoch_val = float(ts_str)
            # If in milliseconds (> 1e11), convert to seconds
            if epoch_val > 1e11:
                epoch_val /= 1000.0
            return datetime.fromtimestamp(epoch_val, tz=timezone.utc).isoformat()

        # Handle ISO strings with 'Z'
        clean_ts = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        # Fallback: if starts with YYYY-MM-DD, try strptime
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(ts_str[:19], fmt).replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass
        return ts_str


def init_db():
    """Initialize schema with durability, hierarchical memory, chat persistence, and performance indexes."""
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

    # 4. Conversations table (Chat persistence)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT NOT NULL,
            pinned_thought_ids TEXT
        )
    """)

    # 5. Messages table (Turn-by-turn chat history)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
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
            pass

    # Performance Indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_thoughts_status_created ON thoughts(status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_thoughts_created ON thoughts(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id ASC)",
        "CREATE INDEX IF NOT EXISTS idx_daily_rollups_date ON daily_rollups(date)",
        "CREATE INDEX IF NOT EXISTS idx_themes_name ON themes(name)",
    ]
    for idx_sql in indexes:
        try:
            conn.execute(idx_sql)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


# ── Thoughts CRUD & Durability ──────────────────────────────────────


def create_pending_thought(audio_path: str, created_at: str, lat: float | None = None, lon: float | None = None, loc_name: str | None = None) -> int:
    """Save an initial pending thought record immediately so audio is NEVER orphaned."""
    conn = get_db()
    norm_ts = normalize_timestamp(created_at)
    cursor = conn.execute(
        """
        INSERT INTO thoughts (created_at, audio_path, latitude, longitude, location_name, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
        """,
        (norm_ts, audio_path, lat, lon, loc_name),
    )
    conn.commit()
    thought_id = cursor.lastrowid
    conn.close()
    return thought_id


def save_thought(thought_data: dict) -> int:
    """Save or update a processed thought."""
    conn = get_db()
    existing_id = thought_data.get("id")
    norm_ts = normalize_timestamp(thought_data.get("created_at"))

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
                norm_ts,
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
                norm_ts,
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

    # Automatically update daily rollup for this thought's date
    if norm_ts:
        date_str = norm_ts[:10]
        update_daily_rollup_for_date(date_str)

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
    """Upsert a durable theme with rich description and associated thoughts."""
    conn = get_db()
    norm_ts = normalize_timestamp(timestamp)
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
            (description, trend, norm_ts, json.dumps(ids), name),
        )
    else:
        conn.execute(
            """
            INSERT INTO themes (name, description, frequency, trend, first_seen, last_seen, associated_thought_ids)
            VALUES (?, ?, 1, ?, ?, ?, ?)
            """,
            (name, description, trend, norm_ts, norm_ts, json.dumps([thought_id])),
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


# ── Daily Rollups Layer (Hierarchical Consolidation) ────────────────


def update_daily_rollup_for_date(date_str: str):
    """Calculate and upsert daily summary rollup for a given YYYY-MM-DD date."""
    conn = get_db()
    rows = conn.execute(
        "SELECT summary, key_insights, mood, location_name FROM thoughts WHERE created_at LIKE ? AND status = 'completed'",
        (f"{date_str}%",),
    ).fetchall()
    
    if not rows:
        conn.close()
        return

    count = len(rows)
    all_insights = []
    locations = set()
    moods = []
    summaries = []

    for r in rows:
        if r["summary"]:
            summaries.append(r["summary"])
        if r["mood"]:
            moods.append(r["mood"])
        if r["location_name"]:
            locations.add(r["location_name"])
        insights = json.loads(r["key_insights"] or "[]")
        all_insights.extend(insights)

    combined_summary = f"{count} thought(s) recorded: " + "; ".join(summaries[:3])
    mood_summary = f"Predominantly {moods[0]}" if moods else "reflective"

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
            combined_summary,
            json.dumps(all_insights[:5]),
            count,
            mood_summary,
            json.dumps(list(locations)),
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


# ── Server-Side Chat Persistence ────────────────────────────────────


def get_or_create_conversation(conv_id: str = "default", title: str = "Thought Journal Chat") -> dict:
    """Retrieve or initialize a persistent conversation session."""
    conn = get_db()
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if not row:
        now_ts = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, pinned_thought_ids) VALUES (?, ?, ?, '[]')",
            (conv_id, title, now_ts),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    
    conv = dict(row)
    conv["pinned_thought_ids"] = json.loads(conv.get("pinned_thought_ids") or "[]")
    conn.close()
    return conv


def update_conversation_pinned_thoughts(conv_id: str, thought_ids: list[int]):
    """Update the pinned thought IDs for a conversation to maintain context continuity."""
    conn = get_db()
    conn.execute(
        "UPDATE conversations SET pinned_thought_ids = ? WHERE id = ?",
        (json.dumps(thought_ids), conv_id),
    )
    conn.commit()
    conn.close()


def save_message(conv_id: str, role: str, content: str) -> int:
    """Save a turn in the conversation history."""
    conn = get_db()
    now_ts = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conv_id, role, content, now_ts),
    )
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()
    return msg_id


def get_conversation_messages(conv_id: str, limit: int = 50) -> list[dict]:
    """Retrieve turn-by-turn chat history for a conversation."""
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC LIMIT ?",
        (conv_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
