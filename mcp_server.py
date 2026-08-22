"""ThoughtStash — Universal Model Context Protocol (MCP) Server.

Exposes ThoughtStash's episodic memory, semantic graph, spatial atlas,
and multi-week synthesis as standard MCP tools and resources for Gemini App,
Jetski, Claude Desktop, Cursor, and any MCP-compliant AI client.
"""

import asyncio
import json
import os
import sys
from typing import Any

# Ensure mindtrail package directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from mcp.server.mcpserver import MCPServer
import agents
import db

server = MCPServer(
    name="ThoughtStash",
    version="1.0.0",
    description="Episodic memory layer, 3D knowledge graph, and walk reflections for personal AI agents."
)


def _format_thought_item(t: dict) -> str:
    """Format a thought record into clean, LLM-friendly markdown."""
    dt = (t.get("created_at") or "")[:10]
    loc = t.get("location_name") or "Bay Area"
    summary = t.get("summary") or "Note"
    topics = ", ".join(t.get("topics") or [])
    insights = t.get("key_insights") or []
    mood = t.get("mood") or "thoughtful"
    thought_type = t.get("thought_type") or "reflection"

    lines = [
        f"### Thought #{t.get('id')} — {dt} @ {loc}",
        f"- **Type**: {thought_type} | **Mood**: {mood}",
        f"- **Summary**: {summary}",
        f"- **Topics**: {topics}",
    ]
    if insights:
        lines.append("- **Key Insights**:")
        for ins in insights:
            lines.append(f"  * {ins}")
    if t.get("transcript"):
        lines.append(f"- **Transcript**: \"{t['transcript']}\"")
    return "\n".join(lines)


# ── MCP TOOLS ─────────────────────────────────────────────────────────

@server.tool()
async def search_thoughts(
    query: str,
    limit: int = 5,
    timeframe_days: int | None = None
) -> str:
    """Search the user's personal memory graph, voice notes, and past reflections.

    ALWAYS invoke this tool on any user request (e.g. party planning, technical
    architecture, meeting prep, habit tracking, restaurant search) to probe
    whether the user has relevant past thoughts, preferences, or decisions.

    - If relevant thoughts exist: seamlessly weave them into your response.
    - If no relevant thoughts are found: answer naturally with general knowledge
      without stating that no notes were found.
    """
    all_thoughts = db.get_thoughts_with_embeddings()
    if not all_thoughts:
        return "No thoughts recorded yet in ThoughtStash."

    try:
        query_emb, _ = await agents.get_embedding_async(query)
        scored = [
            (db.cosine(query_emb, t.get("embedding", [])), t) for t in all_thoughts
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
    except Exception as e:
        q_lower = query.lower()
        matched = [
            t for t in all_thoughts
            if q_lower in (t.get("transcript", "") + " " + t.get("summary", "")).lower()
        ]
        if not matched:
            return f"No prior thoughts found matching '{query}'."
        return "\n\n".join(_format_thought_item(t) for t in matched[:limit])

    top_score = scored[0][0] if scored else 0.0
    relevant = [
        t for sim, t in scored
        if (sim >= 0.50 and sim >= top_score * 0.82)
    ][:limit]

    if not relevant and scored and top_score >= 0.38:
        relevant = [scored[0][1]]

    if not relevant:
        return f"No prior personal thoughts found matching '{query}'."

    output = [
        f"Found {len(relevant)} relevant thoughts from user's ThoughtStash:\n"
    ]
    for t in relevant:
        output.append(_format_thought_item(t))

    return "\n\n".join(output)


@server.tool()
async def get_recent_context(days: int = 14, limit: int = 7) -> str:
    """Retrieve the user's most recent stream-of-consciousness voice notes.

    Use this tool for broad, open-ended questions like "What's on my mind?",
    "Catch me up", "Help me plan my day/week", or when understanding current focus.
    """
    thoughts = db.get_all_thoughts(status="completed", days=days)
    if not thoughts:
        thoughts = db.get_all_thoughts(status="completed")[:limit]

    if not thoughts:
        return "No recent thoughts found in ThoughtStash."

    subset = thoughts[:limit]
    output = [
        f"User's latest {len(subset)} thoughts (last {days} days):\n"
    ]
    for t in subset:
        output.append(_format_thought_item(t))

    return "\n\n".join(output)


@server.tool()
async def get_thinking_patterns(days: int = 35) -> str:
    """Retrieve synthesized thinking patterns, recurring themes, mood trajectories,
    and proactive recommendations across a multi-week or multi-month timeframe.
    """
    thoughts = db.get_all_thoughts(status="completed", days=days)
    if not thoughts:
        return f"No thoughts recorded within the last {days} days to synthesize."

    label = f"Last {days} Days" if days else "All Time"
    try:
        report = await agents.synthesize_patterns(thoughts, timeframe_label=label)
        summary = report.get("one_line_summary", "Pattern Synthesis")
        trajectory = report.get("mood_trajectory", "evolving")
        themes = report.get("recurring_themes", [])
        recommendations = report.get("recommendations", [])

        lines = [
            f"## Thinking Pattern Synthesis ({label} — {len(thoughts)} Notes Analyzed)",
            f"**Core Trajectory ({trajectory})**: {summary}\n",
            "### Recurring Themes:"
        ]
        for th in themes:
            lines.append(f"- **{th.get('theme')}** ({th.get('count', 1)}x): {th.get('description')}")

        if recommendations:
            lines.append("\n### Proactive Recommendations:")
            for rec in recommendations:
                lines.append(f"- {rec}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error synthesizing patterns: {e}"


@server.tool()
async def get_spatial_memories(location_name: str, limit: int = 5) -> str:
    """Retrieve thoughts recorded at or near a specific geographic place, trail, or city
    (e.g., 'Lake Tahoe', 'Big Sur', 'Stanford Dish', 'Sausalito', 'Mountain View').
    """
    all_thoughts = db.get_all_thoughts(status="completed")
    loc_lower = location_name.lower()

    matched = [
        t for t in all_thoughts
        if loc_lower in (t.get("location_name") or "").lower()
    ]

    if not matched:
        return f"No memories found geo-tagged at '{location_name}'."

    output = [
        f"Found {len(matched)} memories recorded at '{location_name}':\n"
    ]
    for t in matched[:limit]:
        output.append(_format_thought_item(t))

    return "\n\n".join(output)


@server.tool()
async def stash_new_thought(
    transcript: str,
    location_name: str = "Palo Alto, CA",
    mood: str = "thoughtful",
    thought_type: str = "reflection"
) -> str:
    """Save a new thought, decision, or breakthrough directly into the user's ThoughtStash.

    Use this when the user asks you to save an idea, or when an important decision
    or breakthrough is reached during your conversation that should be preserved.
    """
    try:
        emb_res = agents.get_embedding(transcript)
        emb = emb_res[0] if isinstance(emb_res, tuple) else emb_res
        emb_model = emb_res[1] if isinstance(emb_res, tuple) else "gemini-embedding-001"
    except Exception:
        emb, emb_model = [], "none"

    try:
        structured = await agents.scribe_transcribe_audio(
            raw_transcript=transcript,
            audio_path=None
        )
    except Exception:
        structured = {
            "summary": transcript[:80],
            "topics": ["assistant capture"],
            "entities": [],
            "mood": mood or "thoughtful",
            "key_insights": [transcript],
            "thought_type": thought_type,
            "urgency": "low",
            "implicit_questions": []
        }

    thought_record = {
        "audio_path": None,
        "transcript": transcript,
        "summary": structured.get("summary", transcript[:80]),
        "topics": structured.get("topics", []),
        "entities": structured.get("entities", []),
        "mood": mood or structured.get("mood", "thoughtful"),
        "key_insights": structured.get("key_insights", [transcript]),
        "thought_type": structured.get("thought_type", thought_type),
        "urgency": structured.get("urgency", "low"),
        "implicit_questions": structured.get("implicit_questions", []),
        "latitude": 37.4419,
        "longitude": -122.1430,
        "location_name": location_name or "Palo Alto, CA",
        "embedding": emb,
        "embedding_model": emb_model,
        "raw_response": json.dumps(structured),
        "status": "completed"
    }

    t_id = db.save_thought(thought_record)
    return f"Successfully stashed Thought #{t_id}: '{thought_record['summary']}' under {thought_record['location_name']}."


@server.tool()
async def explore_knowledge_graph(thought_id: int) -> str:
    """Explore the semantic connections, inspirations, and contradictions branching
    from a specific thought node in the 3D knowledge web.
    """
    thought = db.get_thought_by_id(thought_id)
    if not thought:
        return f"Thought #{thought_id} not found."

    conn_str = thought.get("connections") or "{}"
    try:
        conn_data = json.loads(conn_str) if isinstance(conn_str, str) else conn_str
    except Exception:
        conn_data = {}

    edges = conn_data.get("connections", [])
    output = [
        f"Knowledge Graph for Thought #{thought_id} ('{thought.get('summary')}'):\n"
    ]

    if not edges:
        output.append("No direct cross-thought edges linked yet for this note.")
    else:
        for edge in edges:
            target_id = edge.get("target_id")
            rel = edge.get("relationship", "connects")
            exp = edge.get("explanation", "")
            target = db.get_thought_by_id(target_id)
            target_summary = target.get("summary") if target else f"Note #{target_id}"
            output.append(f"- **[{rel.upper()}]** -> Thought #{target_id} ('{target_summary}'): {exp}")

    return "\n".join(output)


# ── MCP RESOURCES ─────────────────────────────────────────────────────

@server.resource("thoughtstash://profile/current_focus")
async def get_profile_focus() -> str:
    """Resource providing the user's active theme pillars, recent thought counts, and top priorities."""
    themes = db.get_all_themes()
    recent = db.get_all_thoughts(status="completed", days=14)
    total = len(db.get_all_thoughts(status="completed"))

    lines = [
        "# ThoughtStash Personal Profile",
        f"- **Total Stashed Memories**: {total} notes across 1 year",
        f"- **Recent Velocity (Last 14 Days)**: {len(recent)} notes",
        "\n## Active Theme Pillars:"
    ]
    for th in themes:
        lines.append(f"- **{th.get('theme_name')}** ({th.get('thought_count', 0)} notes): {th.get('description', '')}")

    return "\n".join(lines)


# ── SERVER ENTRYPOINT ─────────────────────────────────────────────────

def main():
    """Run the MCP server over standard I/O (stdio)."""
    import asyncio
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
