"""ThoughtStash Agents — Long-Horizon Multi-Agent Memory Engine.

Scribe:    Transcribes audio → structured thought using Structured Outputs (Pydantic)
Connector: Autonomously searches & links thoughts via dynamic vector + temporal retrieval
Oracle:    Context-aware thinking partner grounded in hierarchical memory
"""

import asyncio
import json
import os
import time
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
import numpy as np
from pydantic import BaseModel, Field

import db

load_dotenv()

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
FALLBACK_MODELS = [DEFAULT_MODEL, "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
# Deduplicate while preserving order
FALLBACK_MODELS = list(dict.fromkeys(FALLBACK_MODELS))
EMBEDDING_MODELS = ["gemini-embedding-001", "gemini-embedding-2"]

_client = None


def get_client() -> genai.Client:
    """Lazy client initialization — never crashes at module import."""
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        _client = genai.Client(api_key=api_key)
        return _client

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        _client = genai.Client(
            vertexai=True, project=project, location=location
        )
        return _client

    raise ValueError(
        "No Gemini API key found. Please set the GEMINI_API_KEY environment"
        " variable or add GEMINI_API_KEY=your_key to a .env file."
    )


def _sync_generate_with_fallback(contents, config=None):
    """Synchronous generator with instantaneous model failover on 503/429/404."""
    client = get_client()
    last_err = None
    for model_name in FALLBACK_MODELS:
        try:
            if config:
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            return client.models.generate_content(
                model=model_name,
                contents=contents,
            )
        except Exception as e:
            last_err = e
            # Immediate failover to next model in fallback list
            continue
    raise last_err or RuntimeError("Failed to generate content with any model")


async def generate_with_fallback(contents, config=None):
    """Non-blocking async content generation."""
    return await asyncio.to_thread(_sync_generate_with_fallback, contents, config)


def _sync_get_embedding(text: str) -> list[float]:
    """Synchronous embedding computation."""
    client = get_client()
    last_err = None
    for emb_model in EMBEDDING_MODELS:
        try:
            result = client.models.embed_content(
                model=emb_model,
                contents=text,
            )
            return list(result.embeddings[0].values)
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("Failed to compute embedding")


async def get_embedding_async(text: str) -> list[float]:
    """Non-blocking async embedding computation."""
    return await asyncio.to_thread(_sync_get_embedding, text)


def get_embedding(text: str) -> list[float]:
    """Synchronous embedding helper."""
    return _sync_get_embedding(text)


# ── Pydantic Schemas for Structured Outputs ─────────────────────────


class ScribeOutputSchema(BaseModel):
    transcript: str = Field(description="Clean transcript without filler words (um, uh, like)")
    summary: str = Field(description="Crisp 1-2 sentence core summary of the thought")
    topics: list[str] = Field(default_factory=list, description="Categorized topic tags")
    entities: list[str] = Field(default_factory=list, description="Named entities mentioned")
    mood: str = Field(default="reflective", description="Detected emotional state or mood")
    key_insights: list[str] = Field(default_factory=list, description="Key insights or decisions")
    thought_type: Literal["idea", "reflection", "decision", "question", "rant", "observation"] = Field(
        default="reflection", description="Classification of the thought type"
    )
    urgency: Literal["low", "medium", "high"] = Field(default="low", description="Urgency level")
    implicit_questions: list[str] = Field(
        default_factory=list, description="Underlying or implicit questions the user is pondering"
    )
    location_name: str | None = Field(default=None, description="Inferred or formatted human-readable location")


class ConnectionItem(BaseModel):
    past_thought_date: str = Field(description="Date or timestamp of past thought")
    past_location: str | None = Field(default=None, description="Location of past thought")
    past_summary: str = Field(description="Summary of past thought")
    connection_type: Literal["similar", "contradicts", "evolves", "inspires"] = Field(description="Type of connection")
    explanation: str = Field(description="Deep explanation of how the two thoughts connect")


class ThemeItem(BaseModel):
    theme: str = Field(description="Theme name")
    count: int = Field(default=1, description="Observed frequency")
    trend: Literal["growing", "stable", "declining", "resolved"] = Field(default="growing", description="Trend direction")


class ContradictionItem(BaseModel):
    thought_a: str = Field(description="First thought")
    thought_b: str = Field(description="Contradicting thought")
    tension: str = Field(description="What is the conflict or contradiction")


class ConnectorOutputSchema(BaseModel):
    connections: list[ConnectionItem] = Field(default_factory=list)
    recurring_themes: list[ThemeItem] = Field(default_factory=list)
    contradictions: list[ContradictionItem] = Field(default_factory=list)
    spatio_temporal_insights: str = Field(default="", description="Observations on walk location & time routines")
    proactive_insight: str = Field(default="", description="Proactive synthesis the user did not explicitly ask for")
    thinking_evolution: str = Field(default="", description="How the user's thinking has progressed over time")


# ── Agent 1: SCRIBE ─────────────────────────────────────────────────

SCRIBE_PROMPT = """You are the Scribe agent of ThoughtStash. Your ONLY job is to:
1. Transcribe the audio accurately, removing filler words (um, uh, like, you know)
2. Write a 1-2 sentence summary
3. Extract topics, named entities, mood, and key insights
4. Classify the thought TYPE: idea | reflection | decision | question | rant | observation
5. Detect urgency: low | medium | high
6. Extract implicit questions the user is wondering about
7. Infer a human-readable location tag if coordinates or context are provided (e.g., "Near Central Park", "Mountain View, CA")

Metadata provided:
- Recorded Timestamp: {timestamp}
- Coordinates / Location Context: {location_context}
"""


async def scribe_process(
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
    timestamp: str = "",
    location_context: str = "Unknown location",
) -> dict:
    """Scribe agent: transcribe audio with strict JSON schema."""
    prompt = SCRIBE_PROMPT.format(
        timestamp=timestamp or "Just now",
        location_context=location_context or "Not provided",
    )
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ScribeOutputSchema,
    )
    
    response = await generate_with_fallback(
        contents=[
            prompt,
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
        ],
        config=config,
    )
    
    return json.loads(response.text)


# ── Agent 2: CONNECTOR (Dynamic Retrieval & Long Horizon) ───────────

CONNECTOR_PROMPT = """You are the Connector agent of ThoughtStash — an autonomous long-horizon memory engine.
Given a NEW thought and dynamically retrieved RELEVANT past thoughts (spanning days, weeks, or months) and DURABLE THEMES:

1. Find CONNECTIONS to past thoughts (similarities, contradictions, evolutions)
2. Update RECURRING THEMES
3. Detect SPATIO-TEMPORAL PATTERNS (location routines, time-of-day insights)
4. Notice CONTRADICTIONS (ideas conflicting with past conclusions)
5. Track THOUGHT EVOLUTION (how perspective has changed over time)
6. Generate a PROACTIVE INSIGHT
"""


def _retrieve_context_for_connector(new_thought: dict, max_items: int = 12) -> list[dict]:
    """Dynamic retrieval: finds semantically relevant + recent thoughts across infinite horizons."""
    all_thoughts = db.get_thoughts_with_embeddings()
    if not all_thoughts:
        return []

    # Exclude current thought
    candidates = [t for t in all_thoughts if t.get("id") != new_thought.get("id")]
    if not candidates:
        return []

    new_emb = new_thought.get("embedding")
    if not new_emb:
        return candidates[:max_items]

    def cosine(a, b):
        if not a or not b or len(a) != len(b):
            return 0.0
        a, b = np.array(a, dtype=float), np.array(b, dtype=float)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        if norm == 0:
            return 0.0
        return float(np.dot(a, b) / (norm + 1e-8))

    # Score by similarity
    scored = [(cosine(new_emb, t.get("embedding", [])), t) for t in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)

    # Top 8 semantically similar
    top_similar = [t for _, t in scored[:8]]
    similar_ids = {t["id"] for t in top_similar}

    # Plus top 4 most recent (to ensure recency awareness)
    recents = [t for t in candidates if t["id"] not in similar_ids][:4]

    combined = top_similar + recents
    combined.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return combined


async def connector_analyze(new_thought: dict, past_thoughts: list[dict] | None = None) -> dict:
    """Connector agent: autonomously finds patterns using dynamic memory retrieval."""
    if past_thoughts is None:
        retrieved_past = _retrieve_context_for_connector(new_thought)
    else:
        retrieved_past = past_thoughts

    # Fetch durable themes from DB
    durable_themes = db.get_all_themes()

    loc_str = new_thought.get("location_name") or (
        f"Lat: {new_thought.get('latitude')}, Lon: {new_thought.get('longitude')}"
        if new_thought.get("latitude") is not None
        else "Unknown location"
    )

    context = f"## NEW THOUGHT (just captured)\n"
    context += f"Timestamp: {new_thought.get('created_at', '?')}\n"
    context += f"Location: {loc_str}\n"
    context += f"Summary: {new_thought.get('summary', '')}\n"
    context += f"Topics: {', '.join(new_thought.get('topics', []))}\n"
    context += f"Type: {new_thought.get('thought_type', '?')}\n"
    context += f"Transcript: {new_thought.get('transcript', '')}\n\n"

    if durable_themes:
        context += "## EXISTING DURABLE THEMES (tracked across weeks/months):\n"
        for th in durable_themes[:6]:
            context += f"- **{th['name']}** (Trend: {th['trend']}, seen {th['frequency']}x): {th['description']}\n"
        context += "\n"

    context += "## RETRIEVED HISTORICAL THOUGHTS (Semantic + Temporal matches):\n"
    if not retrieved_past:
        context += "(No past thoughts yet)\n"
    else:
        for i, t in enumerate(retrieved_past):
            t_loc = t.get("location_name") or "Unknown"
            context += f"\n--- Past Thought {i+1} ({t.get('created_at', '?')} @ {t_loc}) ---\n"
            context += f"Summary: {t.get('summary', '')}\n"
            context += f"Topics: {', '.join(t.get('topics', []))}\n"
            context += f"Mood: {t.get('mood', '')}\n"
            context += f"Transcript: {t.get('transcript', '')}\n"

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ConnectorOutputSchema,
    )

    response = await generate_with_fallback(
        contents=[CONNECTOR_PROMPT + "\n\n" + context],
        config=config,
    )

    result = json.loads(response.text)

    # Incrementally update durable themes in SQLite
    if new_thought.get("id"):
        for th in result.get("recurring_themes", []):
            db.upsert_theme(
                name=th["theme"],
                description=f"Theme around {th['theme']}",
                trend=th.get("trend", "growing"),
                thought_id=new_thought["id"],
                timestamp=new_thought.get("created_at", datetime.now().isoformat()),
            )

    return result


# ── Hierarchical Full Pattern Analysis ──────────────────────────────


async def connector_full_analysis(thoughts: list[dict]) -> dict:
    """Full pattern analysis with hierarchical summarization to prevent context explosion."""
    durable_themes = db.get_all_themes()
    recent_rollups = db.get_recent_daily_rollups(14)

    # Use summaries instead of full transcripts if thought count > 15
    use_compact = len(thoughts) > 15
    thoughts_text = ""
    for i, t in enumerate(thoughts):
        t_loc = t.get("location_name") or "Unknown location"
        thoughts_text += f"\n--- Thought {i+1} ({t.get('created_at', '?')} @ {t_loc}) [{t.get('thought_type', 'thought')}] ---\n"
        thoughts_text += f"Summary: {t.get('summary', 'N/A')}\n"
        thoughts_text += f"Topics: {', '.join(t.get('topics', []))}\n"
        thoughts_text += f"Mood: {t.get('mood', 'N/A')}\n"
        if not use_compact:
            thoughts_text += f"Key Insights: {', '.join(t.get('key_insights', []))}\n"
            thoughts_text += f"Transcript: {t.get('transcript', 'N/A')}\n"

    prompt = f"""You are the Connector agent running a COMPREHENSIVE MULTI-WEEK SYNTHESIS.
Analyze the user's historical thoughts and durable themes:

Durable Themes in Memory:
{json.dumps(durable_themes, indent=2) if durable_themes else "None"}

Historical Thoughts Stream:
{thoughts_text}

Respond in this exact JSON format:
{{
    "recurring_themes": [
        {{"theme": "name", "frequency": 0, "description": "why this keeps coming up"}}
    ],
    "emerging_patterns": [
        {{"pattern": "description", "first_seen": "date", "evidence": "supporting thoughts"}}
    ],
    "connections": [
        {{"thought_a": "brief", "thought_b": "brief", "connection": "how they relate"}}
    ],
    "mood_trajectory": {{
        "trend": "improving/declining/stable/fluctuating",
        "summary": "description"
    }},
    "recommendations": ["recommendation1", "recommendation2"],
    "one_line_summary": "In one sentence, here is what has been on your mind..."
}}
"""
    response = await generate_with_fallback(contents=[prompt])
    
    # Strip backticks if any
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


# ── Agent 3: ORACLE (Context Chat with Hierarchical Memory) ─────────

ORACLE_SYSTEM = """You are the Oracle agent of ThoughtStash — a personal AI that KNOWS
what the user has been thinking about. You have access to their voice thought recordings
captured during walks, commutes, and moments of reflection, complete with TIMESTAMPS and GEOLOCATIONS.

KEY BEHAVIORS:
- Reference past thoughts naturally, including WHEN and WHERE
- Connect ideas across different sessions and locations
- Be proactive — suggest connections the user hasn't noticed
- If asked "what have I been thinking about?" give a rich, insightful answer grounded in time and place
- If the user's thinking has evolved on a topic, trace that evolution
- Be warm, conversational, and genuinely helpful — you're a true thinking partner

CONTEXT — User's thought history:
{context}

DURABLE THEMES — Tracked across time:
{durable_themes}

CONNECTOR INSIGHTS — Auto-discovered patterns:
{connector_insights}"""


async def oracle_chat(
    query: str,
    relevant_thoughts: list[dict],
    connector_data: dict | None = None,
    chat_history: list[dict] | None = None,
) -> str:
    """Oracle agent: chat with RAG over thought history, durable themes, and connector patterns."""
    context = ""
    for t in relevant_thoughts:
        loc = t.get("location_name") or (
            f"📍 {t.get('latitude'):.4f}, {t.get('longitude'):.4f}"
            if t.get("latitude") is not None
            else ""
        )
        context += f"📅 **{t.get('created_at', '?')}** {loc} [{t.get('thought_type', 'thought')}]\n"
        context += f"Summary: {t.get('summary', '')}\n"
        context += f"Topics: {', '.join(t.get('topics', []))}\n"
        context += f"Mood: {t.get('mood', '')}\n"
        context += f"Transcript: {t.get('transcript', '')}\n\n"

    durable_themes = db.get_all_themes()
    durable_themes_str = json.dumps(durable_themes[:8], indent=2) if durable_themes else "None yet."

    connector_insights = "None available yet."
    if connector_data:
        connector_insights = json.dumps(connector_data, indent=2)

    system = ORACLE_SYSTEM.format(
        context=context,
        durable_themes=durable_themes_str,
        connector_insights=connector_insights,
    )

    contents = []
    if chat_history:
        for msg in chat_history:
            contents.append(
                types.Content(
                    role=msg["role"],
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=query)])
    )

    response = await generate_with_fallback(
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return response.text
