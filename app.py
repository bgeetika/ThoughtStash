"""ThoughtStash — Long-Horizon Voice Agent Backend with Multi-Agent Swarm.

Agents:
  🖊️ Scribe     — Transcribes audio → structured thought (Structured Output Schema)
  🔗 Connector  — Autonomously tracks cross-session themes & spatio-temporal patterns
  🔮 Oracle     — Context-aware thinking partner with hierarchical RAG memory
"""

import asyncio
import json
import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import numpy as np
from pydantic import BaseModel

import agents
import db

load_dotenv()

app = FastAPI(title="ThoughtStash — Long-Horizon Voice Thought Agent")

# Initialise database on startup
db.init_db()

# Paths
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "data", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# In-memory store for latest connector insights (per-session)
latest_connector_insights: dict = {}

# Serve the static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serve the single-page app."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ── Thoughts — Agentic Pipeline with Guaranteed Durability ───────────


@app.post("/api/thoughts")
async def create_thought(
    audio: UploadFile = File(...),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    location_name: str | None = Form(None),
    client_timestamp: str | None = Form(None),
):
    """Upload audio + location + time → Scribe transcribes → Connector links.

    Durability Guarantee:
    1. Audio is saved to disk with collision-proof UUID
    2. Pending thought record created in SQLite immediately (no orphaned files)
    3. Scribe processes audio with structured schema
    4. On success: marked completed with vector embedding
    5. On failure: marked failed_transcription with error reason (reprocessable)
    6. Connector runs autonomously in background
    """
    audio_bytes = await audio.read()
    created_at = client_timestamp or datetime.now().isoformat()

    # Determine file extension safely
    ctype = audio.content_type or ""
    ext = (
        "mp4"
        if ("mp4" in ctype or "m4a" in ctype or "aac" in ctype)
        else "ogg"
        if "ogg" in ctype
        else "wav"
        if "wav" in ctype
        else "webm"
    )

    # Collision-proof filename with UUID
    unique_id = uuid.uuid4().hex[:8]
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_path = os.path.join(AUDIO_DIR, f"thought_{ts_str}_{unique_id}.{ext}")

    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    # 1. Immediate SQLite durability row
    thought_id = db.create_pending_thought(
        audio_path=audio_path,
        created_at=created_at,
        lat=latitude,
        lon=longitude,
        loc_name=location_name,
    )

    # Location context description for Scribe
    location_context = location_name or ""
    if latitude is not None and longitude is not None:
        coords_str = f"Latitude: {latitude:.5f}, Longitude: {longitude:.5f}"
        location_context = (
            f"{location_name} ({coords_str})" if location_name else coords_str
        )
    if not location_context:
        location_context = "Location not available"

    # 2. Agent 1: SCRIBE
    try:
        structured = await agents.scribe_process(
            audio_bytes,
            mime_type=audio.content_type or "audio/webm",
            timestamp=created_at,
            location_context=location_context,
        )
    except Exception as e:
        db.mark_thought_failed(thought_id, str(e))
        raise HTTPException(
            500, detail=f"Scribe agent failed: {e}. Audio saved as pending id={thought_id}"
        )

    # Location fallback
    final_location_name = location_name or structured.get("location_name")
    if (
        not final_location_name
        and latitude is not None
        and longitude is not None
    ):
        final_location_name = f"{latitude:.4f}, {longitude:.4f}"

    # 3. Vector Embedding
    try:
        embedding = await agents.get_embedding_async(structured.get("transcript", ""))
    except Exception:
        embedding = []

    thought_data = {
        "id": thought_id,
        "created_at": created_at,
        "audio_path": audio_path,
        "transcript": structured.get("transcript", ""),
        "summary": structured.get("summary", ""),
        "topics": structured.get("topics", []),
        "entities": structured.get("entities", []),
        "mood": structured.get("mood", ""),
        "key_insights": structured.get("key_insights", []),
        "thought_type": structured.get("thought_type", "reflection"),
        "urgency": structured.get("urgency", "low"),
        "implicit_questions": structured.get("implicit_questions", []),
        "latitude": latitude,
        "longitude": longitude,
        "location_name": final_location_name,
        "embedding": embedding,
        "embedding_model": "gemini-embedding-001",
        "raw_response": json.dumps(structured),
    }

    db.save_thought(thought_data)

    # 4. Agent 2: CONNECTOR (autonomous non-blocking background task)
    asyncio.create_task(_run_connector(thought_data))

    result = {
        k: v
        for k, v in thought_data.items()
        if k not in ("embedding", "raw_response")
    }
    return result


async def _run_connector(new_thought: dict):
    """Connector agent: runs autonomously with dynamic retrieval across infinite horizons."""
    global latest_connector_insights
    try:
        insights = await agents.connector_analyze(new_thought)
        latest_connector_insights = insights

        db.update_thought_connections(new_thought["id"], json.dumps(insights))

        print(f"🔗 Connector linked thought #{new_thought['id']}:")
        if insights.get("proactive_insight"):
            print(f"   💡 Proactive insight: {insights['proactive_insight']}")
        if insights.get("connections"):
            print(f"   🔗 {len(insights['connections'])} connection(s) identified")
    except Exception as e:
        print(f"⚠️ Connector agent error: {e}")


# ── Reprocess Endpoint (Durability) ──────────────────────────────────


@app.post("/api/reprocess/{thought_id}")
async def reprocess_thought(thought_id: int):
    """Reprocess an audio recording that previously failed transcription."""
    thought = db.get_thought_by_id(thought_id)
    if not thought or not thought.get("audio_path"):
        raise HTTPException(404, "Thought or audio file not found")

    audio_path = thought["audio_path"]
    if not os.path.exists(audio_path):
        raise HTTPException(404, f"Audio file not on disk: {audio_path}")

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    structured = await agents.scribe_process(
        audio_bytes,
        timestamp=thought.get("created_at", ""),
        location_context=thought.get("location_name", ""),
    )
    embedding = await agents.get_embedding_async(structured.get("transcript", ""))

    thought.update({
        "transcript": structured.get("transcript", ""),
        "summary": structured.get("summary", ""),
        "topics": structured.get("topics", []),
        "entities": structured.get("entities", []),
        "mood": structured.get("mood", ""),
        "key_insights": structured.get("key_insights", []),
        "thought_type": structured.get("thought_type", "reflection"),
        "urgency": structured.get("urgency", "low"),
        "implicit_questions": structured.get("implicit_questions", []),
        "embedding": embedding,
        "raw_response": json.dumps(structured),
    })

    db.save_thought(thought)
    asyncio.create_task(_run_connector(thought))
    return {"status": "success", "thought": thought}


# ── Thoughts CRUD ───────────────────────────────────────────────────


@app.get("/api/thoughts")
async def list_thoughts():
    """Return all completed thoughts, newest first."""
    return db.get_all_thoughts(status="completed")


@app.get("/api/thoughts/{thought_id}")
async def get_thought(thought_id: int):
    """Return a single thought."""
    thought = db.get_thought_by_id(thought_id)
    if not thought:
        raise HTTPException(404, "Thought not found")
    return thought


@app.get("/api/themes")
async def list_themes():
    """Return all durable, persistent themes."""
    return db.get_all_themes()


# ── Connector: Connections & Patterns ───────────────────────────────


@app.get("/api/thoughts/{thought_id}/connections")
async def get_thought_connections(thought_id: int):
    """Get the Connector agent's analysis for a specific thought."""
    connections = db.get_thought_connections(thought_id)
    if not connections:
        return {
            "status": "pending",
            "message": "Connector agent hasn't processed this yet",
        }
    return connections


@app.get("/api/connections/latest")
async def get_latest_connections():
    """Get the most recent Connector agent insights."""
    if not latest_connector_insights:
        return {
            "status": "none",
            "message": "No connector insights yet. Record some thoughts!",
        }
    return latest_connector_insights


@app.get("/api/patterns")
async def get_patterns():
    """Run hierarchical pattern analysis across all thoughts."""
    thoughts = db.get_all_thoughts(status="completed")
    if len(thoughts) < 2:
        return {
            "error": "Need at least 2 thoughts to find patterns",
            "thought_count": len(thoughts),
        }
    try:
        return await agents.connector_full_analysis(thoughts)
    except Exception as e:
        raise HTTPException(
            500, detail=f"Connector pattern analysis failed: {e}"
        )


# ── Semantic Search ─────────────────────────────────────────────────


@app.get("/api/search")
async def search_thoughts(q: str):
    """Semantic search across all thoughts."""
    all_thoughts = db.get_thoughts_with_embeddings()
    if not all_thoughts:
        return []

    try:
        query_emb = await agents.get_embedding_async(q)
    except Exception:
        return []

    def cosine(a, b):
        if not a or not b:
            return 0.0
        a, b = np.array(a), np.array(b)
        return float(
            np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)
        )

    scored = []
    for t in all_thoughts:
        sim = cosine(query_emb, t.get("embedding", []))
        t_out = {k: v for k, v in t.items() if k != "embedding"}
        t_out["relevance"] = round(sim, 4)
        scored.append((sim, t_out))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:10]]


# ── Oracle: Context-Aware Chat ──────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Oracle agent: chat with RAG over thought history, durable themes, and connector insights."""
    all_thoughts = db.get_thoughts_with_embeddings()

    if not all_thoughts:
        return {
            "response": (
                "You haven't captured any thoughts yet! "
                "Hit the 🎙️ button and start talking."
            )
        }

    # Retrieve most relevant thoughts via cosine similarity
    try:
        query_emb = await agents.get_embedding_async(req.message)

        def cosine(a, b):
            if not a or not b:
                return 0.0
            a, b = np.array(a), np.array(b)
            return float(
                np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)
            )

        scored = [
            (cosine(query_emb, t.get("embedding", [])), t) for t in all_thoughts
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        relevant = [t for _, t in scored[:8]]
    except Exception:
        relevant = all_thoughts[:8]

    response = await agents.oracle_chat(
        req.message,
        relevant,
        connector_data=latest_connector_insights,
        chat_history=req.history,
    )
    return {"response": response}


# ── Agent Status ────────────────────────────────────────────────────


@app.get("/api/agents/status")
async def agent_status():
    """Return status of all agents and durable memory."""
    thoughts = db.get_all_thoughts(status="completed")
    themes = db.get_all_themes()
    return {
        "agents": [
            {
                "name": "🖊️ Scribe",
                "role": "Structured Voice Capture (Pydantic)",
                "status": "ready",
                "thoughts_processed": len(thoughts),
            },
            {
                "name": "🔗 Connector",
                "role": "Dynamic Long-Horizon Memory Engine",
                "status": "active" if latest_connector_insights else "waiting",
                "durable_themes_tracked": len(themes),
                "last_insight": latest_connector_insights.get(
                    "proactive_insight", "None yet"
                ),
            },
            {
                "name": "🔮 Oracle",
                "role": "Hierarchical Context Thinking Partner",
                "status": "ready",
            },
        ],
        "total_thoughts": len(thoughts),
        "durable_themes_count": len(themes),
        "connector_has_insights": bool(latest_connector_insights),
    }
