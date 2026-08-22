"""ThoughtStash — Voice Thought Capture API server."""

import json
import os
from datetime import datetime

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import gemini_client

app = FastAPI(title="MindTrail — Voice Thought Capture")

# Initialise database on startup
db.init_db()

# Paths
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "data", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Serve the static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── Routes ──────────────────────────────────────────────────────────


@app.get("/")
async def root():
    """Serve the single-page app."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ── Thoughts CRUD ───────────────────────────────────────────────────


@app.post("/api/thoughts")
async def create_thought(audio: UploadFile = File(...)):
    """Upload audio → Gemini transcribes + structures → store in DB."""
    audio_bytes = await audio.read()

    # Persist the raw audio
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_path = os.path.join(AUDIO_DIR, f"thought_{ts}.webm")
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    # AI pipeline: transcribe → structure
    try:
        structured = await gemini_client.transcribe_and_structure(
            audio_bytes, mime_type=audio.content_type or "audio/webm"
        )
    except Exception as e:
        raise HTTPException(500, detail=f"Gemini processing failed: {e}")

    # Embedding for semantic search
    try:
        embedding = gemini_client.get_embedding(
            structured.get("transcript", "")
        )
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
        "embedding": embedding,
        "raw_response": json.dumps(structured),
    }

    thought_data["id"] = db.save_thought(thought_data)
    # Strip heavy fields before returning
    thought_data.pop("embedding", None)
    thought_data.pop("raw_response", None)
    return thought_data


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


# ── Pattern Analysis ────────────────────────────────────────────────


@app.get("/api/patterns")
async def get_patterns():
    """Analyse all thoughts for recurring themes and patterns."""
    thoughts = db.get_all_thoughts()
    if len(thoughts) < 2:
        return {
            "error": "Need at least 2 thoughts to find patterns",
            "thought_count": len(thoughts),
        }
    try:
        return await gemini_client.analyze_patterns(thoughts)
    except Exception as e:
        raise HTTPException(500, detail=f"Pattern analysis failed: {e}")


# ── Semantic Search ─────────────────────────────────────────────────


@app.get("/api/search")
async def search_thoughts(q: str):
    """Semantic search across all thoughts."""
    all_thoughts = db.get_thoughts_with_embeddings()
    if not all_thoughts:
        return []

    try:
        query_emb = gemini_client.get_embedding(q)
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


# ── Context-Aware Chat ──────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Chat with an AI that knows your thoughts (RAG)."""
    all_thoughts = db.get_thoughts_with_embeddings()

    if not all_thoughts:
        return {
            "response": (
                "You haven't captured any thoughts yet! "
                "Hit the 🎙️ button and start talking."
            )
        }

    # Retrieve the most relevant thoughts
    try:
        query_emb = gemini_client.get_embedding(req.message)

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
        relevant = [t for _, t in scored[:7]]
    except Exception:
        relevant = all_thoughts[:7]

    response = await gemini_client.context_chat(
        req.message, relevant, req.history
    )
    return {"response": response}
