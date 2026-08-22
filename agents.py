"""ThoughtStash Agents — 3-agent swarm using Google ADK & Gemini.

Scribe:    Transcribes audio → structured thought with time & geo-location context
Connector: Autonomously finds patterns + connections across time & locations
Oracle:    Context-aware chat (RAG over thought history + spatio-temporal metadata)
"""

import json
import os

from google import genai
from google.genai import types

# ── Gemini client (shared) ──────────────────────────────────────────


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    return genai.Client(vertexai=True, project=project, location=location)


client = _get_client()
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
FALLBACK_MODELS = [DEFAULT_MODEL, "gemini-2.5-flash", "gemini-flash-latest"]
EMBEDDING_MODELS = ["gemini-embedding-001", "gemini-embedding-2"]


def _generate_with_fallback(contents, config=None):
    """Generate content trying primary and fallback models."""
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


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


# ── Agent 1: SCRIBE ─────────────────────────────────────────────────

SCRIBE_PROMPT = """You are the Scribe agent of ThoughtStash. Your ONLY job is to:

1. Transcribe the audio accurately, removing filler words (um, uh, like, you know)
2. Write a 1-2 sentence summary
3. Extract topics, named entities, mood, and key insights
4. Classify the thought TYPE: idea | reflection | decision | question | rant | observation
5. Detect urgency: low | medium | high
6. Extract implicit questions the user is wondering about
7. Infer a human-readable location tag if coordinates or context are provided (e.g., "Near Central Park", "Home/Office Area", or the coordinates)

Metadata provided:
- Recorded Timestamp: {timestamp}
- Coordinates / Location Context: {location_context}

Respond in this exact JSON format:
{{
    "transcript": "cleaned transcription...",
    "summary": "brief summary...",
    "topics": ["topic1", "topic2"],
    "entities": ["entity1", "entity2"],
    "mood": "mood description",
    "key_insights": ["insight1", "insight2"],
    "thought_type": "idea",
    "urgency": "low",
    "implicit_questions": ["question the user seems to be wondering about"],
    "location_name": "inferred or formatted location name"
}}

Return ONLY valid JSON, no markdown formatting."""


async def scribe_process(
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
    timestamp: str = "",
    location_context: str = "Unknown location",
) -> dict:
    """Scribe agent: transcribe audio and extract structured information with spatio-temporal context."""
    prompt = SCRIBE_PROMPT.format(
        timestamp=timestamp or "Just now",
        location_context=location_context or "Not provided",
    )
    response = _generate_with_fallback(
        contents=[
            prompt,
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
        ]
    )
    return json.loads(_clean_json(response.text))


# ── Agent 2: CONNECTOR ──────────────────────────────────────────────

CONNECTOR_PROMPT = """You are the Connector agent of ThoughtStash. You are an autonomous
pattern-finding agent. Given a NEW thought and the user's PAST thoughts (with timestamps and geo-locations), you MUST:

1. Find CONNECTIONS to past thoughts (similarities, contradictions, evolutions)
2. Identify RECURRING THEMES across all thoughts
3. Detect SPATIO-TEMPORAL PATTERNS (e.g. "you tend to brainstorm system architecture during evening walks", "location-specific insights")
4. Notice CONTRADICTIONS (things that conflict with past thoughts)
5. Track THOUGHT EVOLUTION (how thinking on a topic has changed over time)
6. Generate a PROACTIVE INSIGHT — something the user didn't ask for but should know

Be specific. Reference exact past thoughts by their date/time and location.

Respond in this exact JSON format:
{
    "connections": [
        {"past_thought_date": "date/time", "past_location": "location", "past_summary": "...", "connection_type": "similar|contradicts|evolves|inspires", "explanation": "how they connect"}
    ],
    "recurring_themes": [
        {"theme": "name", "count": 0, "trend": "growing|stable|declining"}
    ],
    "contradictions": [
        {"thought_a": "...", "thought_b": "...", "tension": "what's contradictory"}
    ],
    "spatio_temporal_insights": "Observations about when and where the user has their best ideas...",
    "proactive_insight": "Something the user should know based on their thinking patterns...",
    "thinking_evolution": "How the user's thinking has evolved recently..."
}

Return ONLY valid JSON. If there are no past thoughts, return minimal results."""


async def connector_analyze(
    new_thought: dict, past_thoughts: list[dict]
) -> dict:
    """Connector agent: autonomously find patterns after each new thought."""
    loc_str = new_thought.get("location_name") or (
        f"Lat: {new_thought.get('latitude')}, Lon:"
        f" {new_thought.get('longitude')}"
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

    context += "## PAST THOUGHTS\n"
    if not past_thoughts:
        context += "(No past thoughts yet — this is the first one)\n"
    else:
        for i, t in enumerate(past_thoughts[:20]):  # Last 20 thoughts
            t_loc = t.get("location_name") or (
                f"Lat: {t.get('latitude')}, Lon: {t.get('longitude')}"
                if t.get("latitude") is not None
                else "Unknown"
            )
            context += f"\n--- Thought {i+1} ({t.get('created_at', '?')} @ {t_loc}) ---\n"
            context += f"Summary: {t.get('summary', '')}\n"
            context += f"Topics: {', '.join(t.get('topics', []))}\n"
            context += f"Mood: {t.get('mood', '')}\n"
            context += f"Transcript: {t.get('transcript', '')}\n"

    response = _generate_with_fallback(
        contents=[CONNECTOR_PROMPT + "\n\n" + context]
    )
    try:
        return json.loads(_clean_json(response.text))
    except json.JSONDecodeError:
        return {
            "connections": [],
            "recurring_themes": [],
            "contradictions": [],
            "spatio_temporal_insights": "",
            "proactive_insight": response.text,
            "thinking_evolution": "",
        }


PATTERN_REPORT_PROMPT = """You are the Connector agent running a FULL PATTERN ANALYSIS.
Analyze ALL thoughts across time and locations to produce a comprehensive report.

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

Return ONLY valid JSON, no markdown formatting."""


async def connector_full_analysis(thoughts: list[dict]) -> dict:
    """Connector agent: full pattern analysis across all thoughts."""
    thoughts_text = ""
    for i, t in enumerate(thoughts):
        t_loc = t.get("location_name") or (
            f"{t.get('latitude')}, {t.get('longitude')}"
            if t.get("latitude") is not None
            else "Unknown location"
        )
        thoughts_text += f"\n--- Thought {i+1} ({t.get('created_at', '?')} @ {t_loc}) ---\n"
        thoughts_text += f"Summary: {t.get('summary', 'N/A')}\n"
        thoughts_text += f"Topics: {', '.join(t.get('topics', []))}\n"
        thoughts_text += f"Mood: {t.get('mood', 'N/A')}\n"
        thoughts_text += f"Key Insights: {', '.join(t.get('key_insights', []))}\n"
        thoughts_text += f"Transcript: {t.get('transcript', 'N/A')}\n"

    prompt = PATTERN_REPORT_PROMPT.format(thoughts_text=thoughts_text)
    response = _generate_with_fallback(contents=[prompt])
    return json.loads(_clean_json(response.text))


# ── Agent 3: ORACLE ─────────────────────────────────────────────────

ORACLE_SYSTEM = """You are the Oracle agent of ThoughtStash — a personal AI that KNOWS
what the user has been thinking about. You have access to their voice thought recordings
captured during walks, commutes, and moments of reflection, complete with TIMESTAMPS and GEOLOCATIONS.

KEY BEHAVIORS:
- Reference past thoughts naturally, including WHEN (e.g. "last Tuesday evening") and WHERE (e.g. "during your walk around...")
- Connect ideas across different sessions and locations
- Be proactive — suggest connections the user hasn't noticed
- If asked "what have I been thinking about?" give a rich, insightful answer grounded in time and place
- If the user's thinking has evolved on a topic, trace that evolution
- Be warm, conversational, and genuinely helpful — you're a thinking partner

CONTEXT — User's thought history:
{context}

CONNECTOR INSIGHTS — Auto-discovered patterns:
{connector_insights}"""


async def oracle_chat(
    query: str,
    relevant_thoughts: list[dict],
    connector_data: dict | None = None,
    chat_history: list[dict] | None = None,
) -> str:
    """Oracle agent: context-aware chat with thought history + connector insights."""
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

    connector_insights = "None available yet."
    if connector_data:
        connector_insights = json.dumps(connector_data, indent=2)

    system = ORACLE_SYSTEM.format(
        context=context, connector_insights=connector_insights
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

    response = _generate_with_fallback(
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return response.text


# ── Shared: Embeddings ──────────────────────────────────────────────


def get_embedding(text: str) -> list[float]:
    """Get embedding vector for semantic search."""
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
