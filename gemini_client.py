"""Gemini API wrapper for ThoughtStash — transcription, structuring, patterns, chat."""

import json
import os

from google import genai
from google.genai import types


def _get_client():
    """Initialize Gemini client. Tries API key first, then Vertex AI ADC."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    # Vertex AI with Application Default Credentials (corp machines)
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    return genai.Client(vertexai=True, project=project, location=location)


client = _get_client()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
EMBEDDING_MODEL = "text-embedding-004"


def _clean_json(text: str) -> str:
    """Strip markdown code fences from LLM JSON output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


async def transcribe_and_structure(audio_bytes: bytes, mime_type: str = "audio/webm") -> dict:
    """Transcribe audio and extract structured thought information."""
    prompt = """You are a thought capture assistant. Listen to this audio recording and:

1. Transcribe the speech verbatim
2. Write a concise 1-2 sentence summary
3. Extract the main topics discussed (as a list)
4. Extract any named entities (people, places, projects, technologies, companies)
5. Detect the overall mood/energy (e.g., "excited", "reflective", "frustrated", "curious", "determined")
6. Extract key insights or ideas worth remembering

Respond in this exact JSON format:
{
    "transcript": "the full transcription...",
    "summary": "brief summary...",
    "topics": ["topic1", "topic2"],
    "entities": ["entity1", "entity2"],
    "mood": "mood description",
    "key_insights": ["insight1", "insight2"]
}

Return ONLY valid JSON, no markdown formatting."""

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            prompt,
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
        ],
    )
    return json.loads(_clean_json(response.text))


def get_embedding(text: str) -> list[float]:
    """Get embedding vector for semantic search."""
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    return list(result.embeddings[0].values)


async def analyze_patterns(thoughts: list[dict]) -> dict:
    """Analyze patterns and themes across multiple thoughts."""
    thoughts_text = ""
    for i, t in enumerate(thoughts):
        thoughts_text += f"\n--- Thought {i+1} ({t.get('created_at', '?')}) ---\n"
        thoughts_text += f"Summary: {t.get('summary', 'N/A')}\n"
        thoughts_text += f"Topics: {', '.join(t.get('topics', []))}\n"
        thoughts_text += f"Mood: {t.get('mood', 'N/A')}\n"
        thoughts_text += f"Key Insights: {', '.join(t.get('key_insights', []))}\n"
        thoughts_text += f"Transcript: {t.get('transcript', 'N/A')}\n"

    prompt = f"""You are a personal thought analyst. Analyze these thought recordings
captured over time and produce a pattern report.

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

    response = client.models.generate_content(model=MODEL, contents=prompt)
    return json.loads(_clean_json(response.text))


async def context_chat(
    query: str,
    relevant_thoughts: list[dict],
    chat_history: list[dict] | None = None,
) -> str:
    """Chat with context from past thoughts injected via RAG."""
    context = "## Your Thought History (captured via voice on walks)\n\n"
    for t in relevant_thoughts:
        context += f"**{t.get('created_at', '?')}** — {t.get('summary', '')}\n"
        context += f"Topics: {', '.join(t.get('topics', []))}\n"
        context += f"Mood: {t.get('mood', '')}\n"
        context += f"Full thought: {t.get('transcript', '')}\n\n"

    system_prompt = f"""You are MindTrail, a personal AI assistant that knows what the user
has been thinking about. You have access to their voice thought recordings captured
during walks, commutes, and moments of reflection.

Use this context naturally — reference their past thoughts, connect ideas across
different sessions, and help them build on their thinking. Be conversational,
warm, and insightful. When relevant, mention WHEN they had a thought.

If the user hasn't recorded thoughts about a topic, be honest about it.

{context}"""

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

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return response.text
