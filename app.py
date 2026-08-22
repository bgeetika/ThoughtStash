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
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agents
import db

load_dotenv(override=True)

app = FastAPI(title="ThoughtStash — Long-Horizon Voice Thought Agent")

# Initialise database on startup
db.init_db()

# Paths
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "data", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Retained set of background task handles to prevent garbage collection mid-flight
background_tasks: set[asyncio.Task] = set()


def run_background_task(coro):
    """Run an async background task safely without GC dropping it."""
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task


# In-memory store for latest connector insights
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
    4. On success: marked completed with vector embedding & actual model provenance
    5. On failure: marked failed_transcription with error reason (reprocessable)
    6. Connector runs autonomously in retained background task
    """
    audio_bytes = await audio.read()
    created_at = db.normalize_timestamp(client_timestamp or datetime.now(timezone.utc).isoformat())

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
    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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

    # 3. Vector Embedding with True Model Provenance
    try:
        embedding, model_used = await agents.get_embedding_async(structured.get("transcript", ""))
    except Exception:
        embedding, model_used = [], "unknown"

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
        "embedding_model": model_used,
        "raw_response": json.dumps(structured),
    }

    db.save_thought(thought_data)

    # 4. Agent 2: CONNECTOR (autonomous retained background task)
    run_background_task(_run_connector(thought_data))

    result = {
        k: v
        for k, v in thought_data.items()
        if k not in ("embedding", "raw_response")
    }
    return result


class TextThoughtRequest(BaseModel):
    text: str
    latitude: float | None = None
    longitude: float | None = None
    location_name: str | None = None
    client_timestamp: str | None = None


@app.post("/api/thoughts/text")
async def create_text_thought(req: TextThoughtRequest):
    """Capture a thought directly from text input with Scribe structuring and Connector linking."""
    if not req.text.strip():
        raise HTTPException(400, "Thought text cannot be empty")

    created_at = db.normalize_timestamp(req.client_timestamp or datetime.now(timezone.utc).isoformat())
    loc_ctx = req.location_name or (f"{req.latitude:.4f}, {req.longitude:.4f}" if req.latitude is not None else "Not provided")

    prompt = f"""Process this captured thought:
Text: "{req.text}"
Timestamp: {created_at}
Location Context: {loc_ctx}
"""
    from google.genai import types
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=agents.ScribeOutputSchema,
    )
    resp = await agents.generate_with_fallback([prompt], config=config)
    structured = json.loads(resp.text)

    try:
        embedding, model_used = await agents.get_embedding_async(structured.get("transcript", req.text))
    except Exception:
        embedding, model_used = [], "unknown"

    final_location_name = req.location_name or structured.get("location_name") or (
        f"{req.latitude:.4f}, {req.longitude:.4f}" if req.latitude is not None else "Bay Area"
    )

    thought_data = {
        "created_at": created_at,
        "audio_path": None,
        "transcript": structured.get("transcript", req.text),
        "summary": structured.get("summary", req.text[:60]),
        "topics": structured.get("topics", []),
        "entities": structured.get("entities", []),
        "mood": structured.get("mood", "reflective"),
        "key_insights": structured.get("key_insights", []),
        "thought_type": structured.get("thought_type", "idea"),
        "urgency": structured.get("urgency", "low"),
        "implicit_questions": structured.get("implicit_questions", []),
        "latitude": req.latitude,
        "longitude": req.longitude,
        "location_name": final_location_name,
        "embedding": embedding,
        "embedding_model": model_used,
        "raw_response": json.dumps(structured),
    }

    thought_id = db.save_thought(thought_data)
    thought_data["id"] = thought_id

    run_background_task(_run_connector(thought_data))

    return {k: v for k, v in thought_data.items() if k not in ("embedding", "raw_response")}


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
    embedding, model_used = await agents.get_embedding_async(structured.get("transcript", ""))

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
        "embedding_model": model_used,
        "raw_response": json.dumps(structured),
    })

    db.save_thought(thought)
    run_background_task(_run_connector(thought))
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
    """Run hierarchical pattern analysis across thoughts."""
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


# ── Map & Neural Graph Endpoints ────────────────────────────────────


@app.get("/api/map/points")
async def get_map_points():
    """Return all geo-tagged thoughts with cluster category and connections for map visualization."""
    all_thoughts = db.get_thoughts_with_embeddings()
    points = []

    def get_category_meta(topics, transcript):
        text = " ".join(topics).lower() + " " + transcript.lower()
        if any(k in text for k in ["ai", "agent", "model", "memory", "vector", "slm", "edge", "architecture"]):
            return "Technology", "#8b5cf6", "🤖"
        elif any(k in text for k in ["meeting", "velocity", "team", "retro", "sprint", "mentor", "leadership", "offsite"]):
            return "Work", "#3b82f6", "💼"
        elif any(k in text for k in ["family", "mom", "dad", "niece", "anniversary", "birthday", "party", "piñata", "ananya", "manya"]):
            return "Family", "#ec4899", "👨‍👩‍👧"
        else:
            return "Health & Mindfulness", "#10b981", "🌿"

    for t in all_thoughts:
        if t.get("latitude") is not None and t.get("longitude") is not None:
            cat, color, icon = get_category_meta(t.get("topics", []), t.get("transcript", ""))
            points.append({
                "id": t["id"],
                "created_at": t.get("created_at"),
                "summary": t.get("summary"),
                "transcript": t.get("transcript"),
                "location_name": t.get("location_name") or "Bay Area",
                "latitude": t["latitude"],
                "longitude": t["longitude"],
                "mood": t.get("mood"),
                "category": cat,
                "color": color,
                "icon": icon,
                "topics": t.get("topics", [])
            })

    return points


@app.get("/api/graph")
async def get_neural_graph():
    """Return nodes and edges representing the multi-week thought graph."""
    all_thoughts = db.get_thoughts_with_embeddings()
    if not all_thoughts:
        return {"nodes": [], "edges": []}

    nodes = []
    edges = []

    # Theme pillar nodes
    theme_pillars = [
        {"id": "theme_tech", "label": "🤖 AI Agents & Architecture", "group": "theme", "color": "#8b5cf6", "size": 30, "font": {"size": 15, "color": "#ffffff", "face": "Inter"}},
        {"id": "theme_work", "label": "💼 Engineering Leadership", "group": "theme", "color": "#3b82f6", "size": 30, "font": {"size": 15, "color": "#ffffff", "face": "Inter"}},
        {"id": "theme_family", "label": "👨‍👩‍👧 Family & Celebrations", "group": "theme", "color": "#ec4899", "size": 30, "font": {"size": 15, "color": "#ffffff", "face": "Inter"}},
        {"id": "theme_health", "label": "🌿 Health & Mindfulness", "group": "theme", "color": "#10b981", "size": 30, "font": {"size": 15, "color": "#ffffff", "face": "Inter"}}
    ]
    nodes.extend(theme_pillars)

    def get_category_id(topics, transcript):
        text = " ".join(topics).lower() + " " + transcript.lower()
        if any(k in text for k in ["ai", "agent", "model", "memory", "vector", "slm", "edge", "architecture"]):
            return "theme_tech", "#8b5cf6"
        elif any(k in text for k in ["meeting", "velocity", "team", "retro", "sprint", "mentor", "leadership", "offsite"]):
            return "theme_work", "#3b82f6"
        elif any(k in text for k in ["family", "mom", "dad", "niece", "anniversary", "birthday", "party", "piñata", "ananya", "manya"]):
            return "theme_family", "#ec4899"
        else:
            return "theme_health", "#10b981"

    thought_nodes = []
    for t in all_thoughts:
        parent_theme, col = get_category_id(t.get("topics", []), t.get("transcript", ""))
        label = t.get("summary", "Thought")
        if len(label) > 28:
            label = label[:26] + "..."
        
        date_str = (t.get("created_at") or "")[:10]
        loc_str = t.get("location_name") or "Bay Area"

        thought_nodes.append(t)
        nodes.append({
            "id": f"thought_{t['id']}",
            "label": label,
            "title": f"📅 {date_str} @ {loc_str}\n\n{t.get('summary')}\n\nMood: {t.get('mood', 'N/A')}",
            "group": "thought",
            "color": col,
            "size": 16,
            "font": {"size": 11, "color": "#e2e8f0"},
            "full_data": {
                "id": t["id"],
                "summary": t.get("summary"),
                "transcript": t.get("transcript"),
                "location_name": loc_str,
                "created_at": t.get("created_at"),
                "mood": t.get("mood"),
                "topics": t.get("topics", [])
            }
        })

        # Edge to parent theme
        edges.append({
            "from": parent_theme,
            "to": f"thought_{t['id']}",
            "color": {"color": "rgba(255,255,255,0.18)"},
            "dashes": True,
            "width": 1
        })

    # Semantic cross-thought links
    for i in range(len(thought_nodes)):
        for j in range(i + 1, len(thought_nodes)):
            t1, t2 = thought_nodes[i], thought_nodes[j]
            sim = db.cosine(t1.get("embedding"), t2.get("embedding"))
            if sim > 0.60:
                edges.append({
                    "from": f"thought_{t1['id']}",
                    "to": f"thought_{t2['id']}",
                    "label": f"{(sim*100):.0f}%",
                    "color": "rgba(124,92,252,0.6)",
                    "width": max(1, int(sim * 3)),
                    "font": {"size": 9, "color": "#94a3b8", "align": "middle"}
                })

    # Standardize links format for 3D force graph (source/target)
    links = []
    for e in edges:
        links.append({
            "source": e["from"],
            "target": e["to"],
            "label": e.get("label", ""),
            "color": e.get("color", {}).get("color", "rgba(0, 242, 254, 0.4)") if isinstance(e.get("color"), dict) else e.get("color", "rgba(0, 242, 254, 0.4)"),
            "width": e.get("width", 1)
        })

    return {"nodes": nodes, "edges": edges, "links": links}


# ── Semantic Search ─────────────────────────────────────────────────


@app.get("/api/search")
async def search_thoughts(q: str):
    """Semantic search across all thoughts."""
    all_thoughts = db.get_thoughts_with_embeddings()
    if not all_thoughts:
        return []

    try:
        query_emb, _ = await agents.get_embedding_async(q)
    except Exception:
        return []

    scored = []
    for t in all_thoughts:
        sim = db.cosine(query_emb, t.get("embedding", []))
        t_out = {k: v for k, v in t.items() if k != "embedding"}
        t_out["relevance"] = round(sim, 4)
        scored.append((sim, t_out))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:10]]


# ── Oracle: Context-Aware Chat with Server-Side Persistence ─────────


class ChatRequest(BaseModel):
    conversation_id: str = "default"
    message: str
    history: list[dict] = []


@app.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: str):
    """Return persisted turn-by-turn chat history for a session."""
    return db.get_conversation_messages(conv_id)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Oracle agent: server-persisted chat with query expansion and pinned context."""
    all_thoughts = db.get_thoughts_with_embeddings()

    if not all_thoughts:
        return {
            "response": (
                "You haven't recorded any notes yet. "
                "Tap the record button or type a thought above to get started."
            )
        }

    conv_id = req.conversation_id or "default"
    conv = db.get_or_create_conversation(conv_id)
    pinned_ids = set(conv.get("pinned_thought_ids") or [])

    # 1. Query Expansion for follow-ups (e.g. "tell me more", "why is that?")
    expanded_query = req.message
    if req.history and len(req.message.split()) < 6:
        # Use previous assistant message snippet to anchor follow-up retrieval
        last_turn = req.history[-1].get("content", "")[:120]
        expanded_query = f"{last_turn}\nUser query: {req.message}"

    # 2. Retrieve relevant thoughts dynamically for the current prompt
    try:
        query_emb, _ = await agents.get_embedding_async(expanded_query)
        scored = [
            (db.cosine(query_emb, t.get("embedding", [])), t) for t in all_thoughts
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        newly_retrieved = [t for _, t in scored[:6]]
    except Exception:
        newly_retrieved = all_thoughts[:6]

    # 3. Dynamic Context Window (Prioritize new query matches + carry forward 2-3 prior pinned for continuity)
    retrieved_dict = {t["id"]: t for t in all_thoughts}
    pinned_thoughts = [retrieved_dict[tid] for tid in pinned_ids if tid in retrieved_dict]

    # Newly retrieved thoughts take priority so context NEVER freezes on old topics
    combined_dict = {t["id"]: t for t in newly_retrieved}
    for pt in pinned_thoughts:
        if pt["id"] not in combined_dict and len(combined_dict) < 8:
            combined_dict[pt["id"]] = pt

    combined_thoughts = list(combined_dict.values())
    db.update_conversation_pinned_thoughts(conv_id, [t["id"] for t in combined_thoughts])

    # 4. Save User Message to SQLite
    db.save_message(conv_id, "user", req.message)

    # 5. Query-conditioned Connector Insights
    conditioned_insights = None
    if latest_connector_insights:
        conditioned_insights = latest_connector_insights

    # 6. Generate Oracle response
    response_text = await agents.oracle_chat(
        req.message,
        combined_thoughts,
        connector_data=conditioned_insights,
        chat_history=req.history,
    )

    # 7. Save Assistant Message to SQLite
    db.save_message(conv_id, "model", response_text)

    return {
        "conversation_id": conv_id,
        "response": response_text
    }


# ── Agent Status ────────────────────────────────────────────────────


@app.get("/api/agents/status")
async def agent_status():
    """Return status of all agents and durable memory."""
    thoughts = db.get_all_thoughts(status="completed")
    themes = db.get_all_themes()
    return {
        "agents": [
            {
                "name": "Scribe",
                "role": "Voice Transcription & Tagging",
                "status": "ready",
                "thoughts_processed": len(thoughts),
            },
            {
                "name": "Connector",
                "role": "Connection & Pattern Discovery",
                "status": "active" if latest_connector_insights else "waiting",
                "durable_themes_tracked": len(themes),
                "last_insight": latest_connector_insights.get(
                    "proactive_insight", "None yet"
                ),
            },
            {
                "name": "Assistant",
                "role": "Interactive Memory Search",
                "status": "ready",
            },
        ],
        "total_thoughts": len(thoughts),
        "durable_themes_count": len(themes),
        "connector_has_insights": bool(latest_connector_insights),
    }
