"""ThoughtStash — Voice Thought Capture with 3-Agent Swarm.

Agents:
  🖊️ Scribe     — Transcribes audio → structured thought
  🔗 Connector  — Autonomously finds patterns after each new thought
  🔮 Oracle     — Context-aware chat with thought history
"""

import asyncio
import json
import os
from datetime import datetime

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agents
import db

app = FastAPI(title="ThoughtStash — Voice Thought Capture (Agentic)")

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


# ── Thoughts — Agentic Pipeline ─────────────────────────────────────


@app.post("/api/thoughts")
async def create_thought(audio: UploadFile = File(...)):
    """Upload audio → Scribe agent transcribes → Connector agent finds patterns.

    This is the core agentic flow:
    1. Scribe processes the audio (transcribe + structure)
    2. Thought is saved to DB
    3. Connector AUTONOMOUSLY runs to find connections (async, non-blocking)
    """
    audio_bytes = await audio.read()

    # Persist the raw audio
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_path = os.path.join(AUDIO_DIR, f"thought_{ts}.webm")
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    # ── Agent 1: SCRIBE ──────────────────────────────────────────
    try:
        structured = await agents.scribe_process(
            audio_bytes, mime_type=audio.content_type or "audio/webm"
        )
    except Exception as e:
        raise HTTPException(500, detail=f"Scribe agent failed: {e}")

    # Embedding for semantic search
    try:
        embedding = agents.get_embedding(structured.get("transcript", ""))
    except Exception:
        embedding = []

    thought_data = {
        "created_at": datetime.now().isoformat(),
        "audio_path": audio_path,
        "transcript": structured.get("transcript", ""),
        "summary": structured.get("summary", ""),
        "topics": structured.get("topics", []),
        "entities": structured.get("entities", []),
        "mood": structured.get("mood", ""),
        "key_insights": structured.get("key_insights", []),
        "thought_type": structured.get("thought_type", "observation"),
        "urgency": structured.get("urgency", "low"),
        "implicit_questions": structured.get("implicit_questions", []),
        "embedding": embedding,
        "raw_response": json.dumps(structured),
    }

    thought_data["id"] = db.save_thought(thought_data)

    # ── Agent 2: CONNECTOR (autonomous, runs in background) ──────
    asyncio.create_task(_run_connector(thought_data))

    # Response to user — don't wait for Connector
    result = {k: v for k, v in thought_data.items() if k not in ("embedding", "raw_response")}
    return result


async def _run_connector(new_thought: dict):
    """Connector agent runs autonomously after each thought is captured."""
    global latest_connector_insights
    try:
        past_thoughts = db.get_all_thoughts()
        # Exclude the thought we just added
        past_thoughts = [t for t in past_thoughts if t.get("id") != new_thought.get("id")]

        if not past_thoughts:
            return  # First thought, nothing to connect

        insights = await agents.connector_analyze(new_thought, past_thoughts)
        latest_connector_insights = insights

        # Store connection data with the thought
        db.update_thought_connections(new_thought["id"], json.dumps(insights))

        print(f"🔗 Connector agent found patterns for thought #{new_thought['id']}:")
        if insights.get("proactive_insight"):
            print(f"   💡 Proactive insight: {insights['proactive_insight']}")
        if insights.get("connections"):
            print(f"   🔗 {len(insights['connections'])} connections found")
    except Exception as e:
        print(f"⚠️ Connector agent error: {e}")


# ── Thoughts CRUD ───────────────────────────────────────────────────


@app.get("/api/thoughts")
async def list_thoughts():
    """Return all thoughts, newest first."""
    return db.get_all_thoughts()


@app.get("/api/thoughts/{thought_id}")
async def get_thought(thought_id: int):
    """Return a single thought."""
    thought = db.get_thought_by_id(thought_id)
    if not thought:
        raise HTTPException(404, "Thought not found")
    return thought


# ── Connector: Connections for a thought ─────────────────────────────


@app.get("/api/thoughts/{thought_id}/connections")
async def get_thought_connections(thought_id: int):
    """Get the Connector agent's analysis for a specific thought."""
    connections = db.get_thought_connections(thought_id)
    if not connections:
        return {"status": "pending", "message": "Connector agent hasn't processed this yet"}
    return connections


@app.get("/api/connections/latest")
async def get_latest_connections():
    """Get the most recent Connector agent insights."""
    if not latest_connector_insights:
        return {"status": "none", "message": "No connector insights yet. Record some thoughts!"}
    return latest_connector_insights


# ── Connector: Full Pattern Analysis ────────────────────────────────


@app.get("/api/patterns")
async def get_patterns():
    """Run the Connector agent's full pattern analysis across all thoughts."""
    thoughts = db.get_all_thoughts()
    if len(thoughts) < 2:
        return {
            "error": "Need at least 2 thoughts to find patterns",
            "thought_count": len(thoughts),
        }
    try:
        return await agents.connector_full_analysis(thoughts)
    except Exception as e:
        raise HTTPException(500, detail=f"Connector pattern analysis failed: {e}")


# ── Semantic Search ─────────────────────────────────────────────────


@app.get("/api/search")
async def search_thoughts(q: str):
    """Semantic search across all thoughts."""
    all_thoughts = db.get_thoughts_with_embeddings()
    if not all_thoughts:
        return []

    try:
        query_emb = agents.get_embedding(q)
    except Exception:
        return []

    def cosine(a, b):
        if not a or not b:
            return 0.0
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

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
    """Oracle agent: chat with AI that knows your thoughts + connector insights."""
    all_thoughts = db.get_thoughts_with_embeddings()

    if not all_thoughts:
        return {
            "response": (
                "You haven't captured any thoughts yet! "
                "Hit the 🎙️ button and start talking."
            )
        }

    # Retrieve the most relevant thoughts via embedding search
    try:
        query_emb = agents.get_embedding(req.message)

        def cosine(a, b):
            if not a or not b:
                return 0.0
            a, b = np.array(a), np.array(b)
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

        scored = [(cosine(query_emb, t.get("embedding", [])), t) for t in all_thoughts]
        scored.sort(key=lambda x: x[0], reverse=True)
        relevant = [t for _, t in scored[:7]]
    except Exception:
        relevant = all_thoughts[:7]

    # Oracle agent gets connector insights + relevant thoughts
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
    """Return status of all agents."""
    thoughts = db.get_all_thoughts()
    return {
        "agents": [
            {
                "name": "🖊️ Scribe",
                "role": "Transcribe + Structure",
                "status": "ready",
                "thoughts_processed": len(thoughts),
            },
            {
                "name": "🔗 Connector",
                "role": "Pattern Finding (Autonomous)",
                "status": "active" if latest_connector_insights else "waiting",
                "last_insight": latest_connector_insights.get("proactive_insight", "None yet"),
            },
            {
                "name": "🔮 Oracle",
                "role": "Context-Aware Chat",
                "status": "ready",
            },
        ],
        "total_thoughts": len(thoughts),
        "connector_has_insights": bool(latest_connector_insights),
    }
