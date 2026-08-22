"""ThoughtStash Agents — Long-Horizon Multi-Agent Memory Engine.

Scribe:    Transcribes audio → structured thought using Structured Outputs (Pydantic)
Connector: Autonomously searches & links thoughts via dynamic vector + temporal retrieval
Oracle:    Context-aware thinking partner grounded in hierarchical memory
"""

import asyncio
from datetime import datetime, timezone
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

load_dotenv(override=True)

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
]
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
            continue
    raise last_err or RuntimeError("Failed to generate content with any model")


async def generate_with_fallback(contents, config=None):
    """Non-blocking async content generation."""
    return await asyncio.to_thread(_sync_generate_with_fallback, contents, config)


def _sync_get_embedding(text: str) -> tuple[list[float], str]:
    """Synchronous embedding computation returning (vector, model_name)."""
    client = get_client()
    last_err = None
    for emb_model in EMBEDDING_MODELS:
        try:
            result = client.models.embed_content(
                model=emb_model,
                contents=text,
            )
            return list(result.embeddings[0].values), emb_model
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("Failed to compute embedding")


async def get_embedding_async(text: str) -> tuple[list[float], str]:
    """Non-blocking async embedding computation returning (vector, model_name)."""
    return await asyncio.to_thread(_sync_get_embedding, text)


def get_embedding(text: str) -> tuple[list[float], str]:
    """Synchronous embedding helper returning (vector, model_name)."""
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
    description: str = Field(description="Clear, informative description of why this theme recurs across thoughts")
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


# Full Pattern Report Pydantic Schema
class RecurringThemeReport(BaseModel):
    theme: str
    frequency: int
    description: str


class EmergingPatternReport(BaseModel):
    pattern: str
    first_seen: str
    evidence: str


class ConnectionReport(BaseModel):
    thought_a: str
    thought_b: str
    connection: str


class MoodTrajectoryReport(BaseModel):
    trend: Literal["improving", "declining", "stable", "fluctuating"]
    summary: str


class FullPatternReport(BaseModel):
    recurring_themes: list[RecurringThemeReport] = Field(default_factory=list)
    emerging_patterns: list[EmergingPatternReport] = Field(default_factory=list)
    connections: list[ConnectionReport] = Field(default_factory=list)
    mood_trajectory: MoodTrajectoryReport
    recommendations: list[str] = Field(default_factory=list)
    one_line_summary: str


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
2. Update RECURRING THEMES with rich, informative descriptions explaining why the theme recurs
3. Detect SPATIO-TEMPORAL PATTERNS (location routines, time-of-day insights)
4. Notice CONTRADICTIONS (ideas conflicting with past conclusions)
5. Track THOUGHT EVOLUTION (how perspective has changed over time)
6. Generate a PROACTIVE INSIGHT
"""


def _sync_retrieve_context(new_thought: dict, max_items: int = 12) -> list[dict]:
    """Retrieve semantically relevant + temporal thoughts across infinite horizons."""
    all_thoughts = db.get_thoughts_with_embeddings()
    if not all_thoughts:
        return []

    candidates = [t for t in all_thoughts if t.get("id") != new_thought.get("id")]
    if not candidates:
        return []

    new_emb = new_thought.get("embedding")
    if not new_emb:
        return candidates[:max_items]

    # Score by similarity using canonical db.cosine
    scored = [(db.cosine(new_emb, t.get("embedding", [])), t) for t in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)

    # Top 8 semantically similar
    top_similar = [t for _, t in scored[:8]]
    similar_ids = {t["id"] for t in top_similar}

    # Plus top 4 most recent (to ensure recency awareness)
    recents = [t for t in candidates if t["id"] not in similar_ids][:4]

    combined = top_similar + recents
    combined.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return combined


async def retrieve_context_for_connector(new_thought: dict, max_items: int = 12) -> list[dict]:
    """Non-blocking async retrieval for Connector."""
    return await asyncio.to_thread(_sync_retrieve_context, new_thought, max_items)


async def connector_analyze(new_thought: dict, past_thoughts: list[dict] | None = None) -> dict:
    """Connector agent: autonomously finds patterns using dynamic memory retrieval."""
    if past_thoughts is None:
        retrieved_past = await retrieve_context_for_connector(new_thought)
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

    # Incrementally update durable themes in SQLite with real description
    if new_thought.get("id"):
        for th in result.get("recurring_themes", []):
            db.upsert_theme(
                name=th["theme"],
                description=th.get("description") or f"Recurring observations around {th['theme']}",
                trend=th.get("trend", "growing"),
                thought_id=new_thought["id"],
                timestamp=new_thought.get("created_at") or datetime.now(timezone.utc).isoformat(),
            )

    return result


# ── Hierarchical Full Pattern Analysis ──────────────────────────────


async def connector_full_analysis(thoughts: list[dict]) -> dict:
    """Full pattern analysis with hierarchical summarization and strict response_schema."""
    durable_themes = db.get_all_themes()
    recent_rollups = db.get_recent_daily_rollups(10)

    # Bound thoughts to latest 15 to ensure sub-2s response time
    bounded_thoughts = thoughts[:15]

    thoughts_text = ""
    for i, t in enumerate(bounded_thoughts):
        t_loc = t.get("location_name") or "Bay Area"
        thoughts_text += f"- [{t.get('created_at', '')[:10]} @ {t_loc}] ({t.get('mood', 'reflective')}) {t.get('summary', '')}\n"

    rollup_text = ""
    if recent_rollups:
        rollup_text = "## RECENT DAILY ROLLUPS:\n"
        for r in recent_rollups[:5]:
            rollup_text += f"- {r['date']} ({r['thought_count']} thoughts, {r['mood_summary']}): {r['summary']}\n"

    prompt = f"""You are the Connector agent running high-speed multi-week thought synthesis.
Analyze these episodic thoughts, rollups, and themes to detect patterns:

Durable Themes:
{json.dumps(durable_themes[:4], indent=2) if durable_themes else "None"}

{rollup_text}

Thought Stream:
{thoughts_text}
"""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=FullPatternReport,
    )

    response = await generate_with_fallback(
        contents=[prompt],
        config=config,
    )
    
    return json.loads(response.text)


# ── Agent 3: ASSISTANT (Concise Grounded Search Chat) ───────────────


class ChatOutputSchema(BaseModel):
    summary: str = Field(
        description="A direct, helpful 1-2 sentence response addressing the user's query (max 40 words)."
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="2 to 4 concise bullet points. If the user is recalling past notes, cite exact dates/locations from their notes. If the user asks for suggestions, recommendations, advice, or ideas relating to their notes, provide real, high-quality, practical recommendations."
    )
    suggested_action: str | None = Field(
        default=None,
        description="Optional helpful takeaway, tip, or next step for the user."
    )


def build_thought_context_layer(
    relevant_thoughts: list[dict],
    durable_themes: list[dict] | None = None,
) -> dict:
    """Builds a structured personal context layer from the user's thought stash.
    
    Returns a dictionary with:
      - has_context: bool
      - context_text: formatted string representing matching notes, locations & themes
      - thought_count: int
      - locations: list of unique locations
    """
    if not relevant_thoughts:
        return {
            "has_context": False,
            "context_text": "[THOUGHTSTASH CONTEXT LAYER: No directly related notes found in stash]",
            "thought_count": 0,
            "locations": [],
        }

    lines = []
    locations = set()
    for t in relevant_thoughts:
        loc = t.get("location_name") or "Unspecified location"
        if loc and loc != "Unspecified location":
            locations.add(loc)
        date_str = t.get("created_at", "?")[:10] if t.get("created_at") else "Unknown date"
        summary = t.get("summary") or t.get("transcript") or ""
        topics = t.get("topics") or []
        topic_str = f" [Topics: {', '.join(topics)}]" if topics else ""
        lines.append(f"• [{date_str} @ {loc}]: {summary}{topic_str}")

    theme_lines = []
    if durable_themes:
        for th in durable_themes[:4]:
            desc = th.get("summary") or th.get("description") or ""
            theme_lines.append(f"• {th.get('name', '')}: {desc}")

    formatted = "[THOUGHTSTASH CONTEXT LAYER]\n"
    formatted += f"Relevant Recorded Notes ({len(lines)}):\n"
    formatted += "\n".join(lines)

    if theme_lines:
        formatted += "\n\nActive Durable Themes & Long-Term Patterns:\n" + "\n".join(theme_lines)

    formatted += "\n[END CONTEXT LAYER]"

    return {
        "has_context": True,
        "context_text": formatted,
        "thought_count": len(lines),
        "locations": list(locations),
    }


async def oracle_chat(
    query: str,
    relevant_thoughts: list[dict],
    connector_data: dict | None = None,
    chat_history: list[dict] | None = None,
) -> dict:
    """Two-step assistant chat:
    1. Always query our DB and build a personal context layer.
    2. If the query needs real-world info (restaurants, directions, facts),
       call Gemini with GoogleSearch grounding first, then format.
       Otherwise, answer purely from the context layer.
    """
    durable_themes = db.get_all_themes()
    context_layer = build_thought_context_layer(relevant_thoughts, durable_themes)

    history_str = ""
    if chat_history:
        for msg in chat_history[-4:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_str += f"{role}: {msg['content']}\n"

    # ── Step 1: Classify if the query needs web lookup ──────────────
    needs_web = _query_needs_web_search(query, context_layer)

    # ── Step 2a: Web-grounded path ──────────────────────────────────
    web_context = ""
    if needs_web:
        try:
            print(f"[oracle_chat] Web search triggered for: {query[:80]}")
            web_context = await _google_search_lookup(
                query, context_layer, history_str
            )
            print(f"[oracle_chat] Web search returned {len(web_context)} chars")
        except Exception as e:
            print(f"[oracle_chat] Web search failed: {e}")
            web_context = ""  # Graceful fallback: answer without web

    # ── Step 2b: Build the final prompt ─────────────────────────────
    augmented_user_input = f"""{query}

{context_layer['context_text']}"""

    web_section = ""
    if web_context:
        web_section = f"""

WEB SEARCH RESULTS (use these for real-world recommendations, facts, and details):
{web_context}
"""

    prompt = f"""You are the Thought Stash assistant — a thinking partner grounded in the user's personal notes.

HOW THIS WORKS:
Every request comes with two possible sources of information:
1. [THOUGHTSTASH CONTEXT LAYER] — the user's own recorded voice notes, ideas, and themes from their stash.
2. [WEB SEARCH RESULTS] — real-world information from Google Search (only when the query needs it).

OPERATING RULES:
1. RECALL questions ("what did I say about X?", "what did I plan?"):
   - Answer strictly from the Context Layer. Never invent notes or dates.
   - If no notes exist on the topic, say so.

2. RECOMMENDATION / REAL-WORLD questions ("suggest restaurants", "what's the weather", "give me ideas"):
   - Use the Context Layer as background (locations, preferences, trip plans).
   - Use the Web Search Results for concrete, accurate, real-world answers.
   - Provide specific names, ratings, addresses when available.

3. MIXED questions ("what restaurants are near the place I mentioned?"):
   - First ground the location/context from the Context Layer.
   - Then use the Web Search Results for the actual recommendations.

4. PROACTIVE INSIGHTS — this is critical:
   - When the Context Layer contains notes that are directly relevant to what the user is planning or asking about, SURFACE those insights even if the user did not explicitly ask.
   - Example: if the user asks to plan a birthday party, and their notes mention they preferred smaller guest lists after a previous overcrowded party, mention that preference upfront (e.g. "Based on your note about Manya's party, you may want to keep the guest list small").
   - This is the core value of Thought Stash — connecting past reflections to present decisions.
   - Weave these personal insights naturally into your answer, do not list them as a separate section.

FORMAT:
- summary: 1-2 clear sentences (max 40 words).
- key_points: 2-4 concise bullets with specific details. At least one bullet should surface a proactive insight from the context layer if one exists.
- suggested_action: optional next step.
- No markdown headers, no asterisks, no hashtags.

Recent Conversation:
{history_str or "New conversation"}
{web_section}
User Request with Context Layer:
{augmented_user_input}
"""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ChatOutputSchema,
    )

    response = await generate_with_fallback(
        contents=[prompt],
        config=config,
    )

    try:
        data = json.loads(response.text)
        data["context_layer_applied"] = context_layer["has_context"]
        data["matched_thought_count"] = context_layer["thought_count"]
        data["web_search_used"] = bool(web_context)
        return data
    except Exception:
        return {
            "summary": response.text,
            "key_points": [],
            "suggested_action": None,
            "context_layer_applied": context_layer["has_context"],
            "matched_thought_count": context_layer["thought_count"],
            "web_search_used": bool(web_context),
        }


def _query_needs_web_search(query: str, context_layer: dict) -> bool:
    """Lightweight heuristic: does this query need real-world info beyond the user's notes?"""
    q = query.lower()

    # Strong recommendation/lookup signals
    web_keywords = [
        "suggest", "recommend", "restaurant", "hotel", "cafe", "coffee",
        "directions", "weather", "best", "top", "nearby", "near",
        "price", "cost", "hours", "open", "book a", "reserve",
        "flight", "train", "bus route",
        "review", "rating", "menu", "recipe",
        "how to", "what is", "where is", "when is",
        "compare", "alternative", "option",
        "buy", "shop", "store", "deal",
        "concert", "movie", "ticket",
        "news", "latest", "current", "today",
    ]

    if any(kw in q for kw in web_keywords):
        return True

    # Question patterns that likely need external info
    if q.endswith("?") and not any(
        recall in q for recall in ["did i", "have i", "what did i", "my notes", "my thought"]
    ):
        return True

    return False


async def _google_search_lookup(
    query: str, context_layer: dict, history_str: str
) -> str:
    """Call Gemini with GoogleSearch grounding to get real-world info.
    Returns a plain-text summary of web results.
    """
    # Build a search-optimized prompt that includes location context from notes
    locations = context_layer.get("locations", [])
    location_hint = f" (near {', '.join(locations[:2])})" if locations else ""

    search_prompt = f"""Based on the user's question, search the web and return useful, specific, factual information.

User's question: {query}{location_hint}

Recent conversation context:
{history_str or "None"}

Return a concise factual summary with specific names, addresses, ratings, or details.
Keep it under 300 words. Focus on actionable, real information."""

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )

    response = await generate_with_fallback(
        contents=[search_prompt],
        config=config,
    )

    return response.text or ""

