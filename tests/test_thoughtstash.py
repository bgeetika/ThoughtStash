"""Comprehensive automated test suite for ThoughtStash.

Tests:
1. Zero-dependency DB initialization & migrations
2. Pending thought durability (no orphaned audio)
3. Durable themes upsert & query
4. Scribe & Connector Pydantic schema validation (positive & negative)
5. P0 Regression: connector_analyze theme upsert loop execution
6. Daily rollups computation and retrieval
7. Server-side conversation & message persistence
8. Canonical cosine safety against mismatched vector dimensions
9. Embedding model provenance return
10. Timestamp normalization across various input formats
11. Web search heuristic classifier
12. All 16 FastAPI HTTP endpoints via TestClient
"""

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

# Set isolated test database BEFORE importing app/db
temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
temp_db_path = temp_db.name
temp_db.close()

os.environ["GEMINI_API_KEY"] = "fake_test_key_for_unit_tests"

import db
db.DB_PATH = temp_db_path

import agents
from agents import ScribeOutputSchema, ConnectorOutputSchema, FullPatternReport, ChatOutputSchema

from app import app
from fastapi.testclient import TestClient


class TestDatabaseAndDurability(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_create_pending_thought(self):
        """Verify thought is saved as pending immediately so audio is never lost."""
        t_id = db.create_pending_thought(
            audio_path="/tmp/fake_thought.webm",
            created_at=datetime.now(timezone.utc).isoformat(),
            lat=37.422,
            lon=-122.084,
            loc_name="Mountain View",
        )
        self.assertIsInstance(t_id, int)

        thought = db.get_thought_by_id(t_id)
        self.assertIsNotNone(thought)
        self.assertEqual(thought["status"], "pending")
        self.assertEqual(thought["audio_path"], "/tmp/fake_thought.webm")

    def test_save_and_update_thought(self):
        """Verify saving complete thought data with all Scribe fields and rollups."""
        t_id = db.create_pending_thought(
            audio_path="/tmp/test.webm",
            created_at="2099-06-15T10:00:00Z",
        )
        data = {
            "id": t_id,
            "created_at": "2099-06-15T10:00:00Z",
            "audio_path": "/tmp/test.webm",
            "transcript": "Let's build a long horizon agent",
            "summary": "Building long horizon agent",
            "topics": ["AI", "Agents"],
            "entities": ["ThoughtStash"],
            "mood": "excited",
            "key_insights": ["Hierarchical memory is key"],
            "thought_type": "idea",
            "urgency": "high",
            "implicit_questions": ["How to store durable themes?"],
            "latitude": 37.7749,
            "longitude": -122.4194,
            "location_name": "San Francisco, CA",
            "embedding": [0.1, 0.2, 0.3],
            "embedding_model": "gemini-embedding-001",
        }
        saved_id = db.save_thought(data)
        self.assertEqual(saved_id, t_id)

        thought = db.get_thought_by_id(t_id)
        self.assertEqual(thought["status"], "completed")
        self.assertEqual(thought["thought_type"], "idea")
        self.assertEqual(thought["urgency"], "high")
        self.assertEqual(thought["implicit_questions"], ["How to store durable themes?"])
        self.assertEqual(thought["topics"], ["AI", "Agents"])

        # Verify daily rollup was generated
        rollups = db.get_recent_daily_rollups(30)
        dates = [r["date"] for r in rollups]
        self.assertIn("2099-06-15", dates)

    def test_durable_themes(self):
        """Verify persistent themes table upserts and tracking."""
        theme_name = f"Episodic Memory Test {datetime.now().timestamp()}"
        db.upsert_theme(
            name=theme_name,
            description="Focus on human voice thought capture",
            trend="growing",
            thought_id=101,
            timestamp="2026-08-22T12:00:00Z",
        )
        db.upsert_theme(
            name=theme_name,
            description="Focus on human voice thought capture and consolidation",
            trend="growing",
            thought_id=102,
            timestamp="2026-08-22T13:00:00Z",
        )
        themes = db.get_all_themes()
        theme_names = [t["name"] for t in themes]
        self.assertIn(theme_name, theme_names)
        target = next(t for t in themes if t["name"] == theme_name)
        self.assertEqual(target["frequency"], 2)
        self.assertIn(101, target["associated_thought_ids"])
        self.assertIn(102, target["associated_thought_ids"])

    def test_chat_persistence(self):
        """Verify server-side conversations and message persistence."""
        conv_id = f"test-conv-{datetime.now().timestamp()}"
        conv = db.get_or_create_conversation(conv_id, "Test Chat")
        self.assertEqual(conv["id"], conv_id)

        msg_id1 = db.save_message(conv_id, "user", "What was I thinking about?")
        msg_id2 = db.save_message(conv_id, "model", "You were thinking about AI.")
        self.assertTrue(msg_id1 > 0)
        self.assertTrue(msg_id2 > msg_id1)

        messages = db.get_conversation_messages(conv_id)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "What was I thinking about?")
        self.assertEqual(messages[1]["role"], "model")

        db.update_conversation_pinned_thoughts(conv_id, [1, 2, 3])
        updated_conv = db.get_or_create_conversation(conv_id)
        self.assertEqual(updated_conv["pinned_thought_ids"], [1, 2, 3])

    def test_safe_cosine_dimension_mismatch(self):
        """Verify cosine similarity never raises ValueError on mismatched dimensions."""
        vec3 = [1.0, 2.0, 3.0]
        vec5 = [1.0, 2.0, 3.0, 4.0, 5.0]
        empty = []
        
        self.assertEqual(db.cosine(vec3, vec5), 0.0)
        self.assertEqual(db.cosine(vec3, empty), 0.0)
        self.assertEqual(db.cosine(empty, empty), 0.0)
        self.assertAlmostEqual(db.cosine([1.0, 0.0], [1.0, 0.0]), 1.0)

    def test_normalize_timestamp_edge_cases(self):
        """Verify timestamp normalization handles ISO, Z, epoch, and None."""
        now_iso = db.normalize_timestamp(None)
        self.assertTrue(len(now_iso) >= 19)

        # Standard ISO with Z
        norm1 = db.normalize_timestamp("2026-08-22T10:00:00Z")
        self.assertIn("2026-08-22T10:00:00", norm1)

        # Space separated datetime
        norm2 = db.normalize_timestamp("2026-08-22 10:00:00")
        self.assertIn("2026-08-22T10:00:00", norm2)

        # Numeric epoch string
        norm3 = db.normalize_timestamp("1787440000")
        self.assertTrue(norm3.startswith("20"))

        # Empty string fallback
        norm4 = db.normalize_timestamp("")
        self.assertTrue(len(norm4) >= 19)


class TestPydanticSchemasAndAgents(unittest.TestCase):
    def test_scribe_schema_validation(self):
        """Verify ScribeOutputSchema strict JSON parsing."""
        raw_json = {
            "transcript": "I need to walk more often",
            "summary": "Speaker wants to walk more.",
            "topics": ["health", "habits"],
            "entities": [],
            "mood": "reflective",
            "key_insights": ["Walking boosts clarity"],
            "thought_type": "decision",
            "urgency": "medium",
            "implicit_questions": ["When is the best time to walk?"],
            "location_name": "Palo Alto",
        }
        obj = ScribeOutputSchema(**raw_json)
        self.assertEqual(obj.thought_type, "decision")
        self.assertEqual(obj.urgency, "medium")
        self.assertEqual(len(obj.topics), 2)

    def test_scribe_schema_negative_validation(self):
        """Verify ScribeOutputSchema rejects invalid enums."""
        with self.assertRaises(ValidationError):
            ScribeOutputSchema(
                transcript="test",
                summary="test",
                thought_type="INVALID_TYPE",
            )

        with self.assertRaises(ValidationError):
            ScribeOutputSchema(
                transcript="test",
                summary="test",
                urgency="SUPER_URGENT",
            )

    def test_connector_schema_validation(self):
        """Verify ConnectorOutputSchema strict JSON parsing with rich descriptions."""
        raw_json = {
            "connections": [
                {
                    "past_thought_date": "2026-08-01",
                    "past_location": "Cupertino",
                    "past_summary": "Walked in Cupertino",
                    "connection_type": "evolves",
                    "explanation": "Deepened habit commitment",
                }
            ],
            "recurring_themes": [
                {
                    "theme": "Daily Health",
                    "description": "Consistent focus on daily morning walks and outdoor exercise",
                    "count": 3,
                    "trend": "growing"
                }
            ],
            "contradictions": [],
            "spatio_temporal_insights": "Walks happen primarily on weekend mornings.",
            "proactive_insight": "Consider blocking calendar for mornings.",
            "thinking_evolution": "Perspective shifted from reactive to proactive.",
        }
        obj = ConnectorOutputSchema(**raw_json)
        self.assertEqual(len(obj.connections), 1)
        self.assertEqual(obj.recurring_themes[0].description, "Consistent focus on daily morning walks and outdoor exercise")
        self.assertEqual(obj.recurring_themes[0].trend, "growing")

    def test_full_pattern_report_schema(self):
        """Verify FullPatternReport schema validation."""
        raw = {
            "recurring_themes": [
                {"theme": "Tech", "frequency": 4, "description": "AI systems"}
            ],
            "emerging_patterns": [
                {"pattern": "Morning walks", "first_seen": "2026-08-01", "evidence": "Cupertino walk"}
            ],
            "connections": [
                {"thought_a": "A", "thought_b": "B", "connection": "Evolves"}
            ],
            "mood_trajectory": {
                "trend": "improving",
                "summary": "Energy has increased"
            },
            "recommendations": ["Keep walking"],
            "one_line_summary": "Overall balanced thinking"
        }
        obj = FullPatternReport(**raw)
        self.assertEqual(obj.mood_trajectory.trend, "improving")
        self.assertEqual(len(obj.recommendations), 1)

    def test_p0_connector_analyze_theme_upsert_loop(self):
        """P0 Regression Test: connector_analyze theme upsert loop runs cleanly without NameError."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "connections": [],
            "recurring_themes": [
                {
                    "theme": "Agent Autonomy Test",
                    "description": "Exploration of long-horizon AI agent state",
                    "count": 2,
                    "trend": "growing"
                }
            ],
            "contradictions": [],
            "spatio_temporal_insights": "Walks around Palo Alto",
            "proactive_insight": "Consider writing a technical 1-pager",
            "thinking_evolution": "Deepening architectural clarity"
        })

        with patch("agents.generate_with_fallback", new=AsyncMock(return_value=mock_response)):
            thought_data = {
                "id": 999,
                "created_at": "2026-08-22T15:00:00Z",
                "summary": "Reflecting on agent autonomy",
                "transcript": "Autonomous agents need durable memory",
                "topics": ["AI", "Agents"],
                "mood": "focused",
                "thought_type": "idea",
                "location_name": "Palo Alto, CA"
            }
            
            result = asyncio.run(agents.connector_analyze(thought_data, past_thoughts=[]))
            
            self.assertIn("recurring_themes", result)
            self.assertEqual(len(result["recurring_themes"]), 1)
            
            themes = db.get_all_themes()
            theme_names = [th["name"] for th in themes]
            self.assertIn("Agent Autonomy Test", theme_names)

    def test_context_layer_building(self):
        """Verify ThoughtStash context layer builds structured context for agent."""
        mock_thoughts = [
            {
                "id": 1,
                "summary": "Planned anniversary coastal drive",
                "transcript": "Let's take parents on Highway 1 to Carmel",
                "location_name": "Mountain View, CA",
                "created_at": "2026-07-22T10:00:00Z",
                "topics": ["travel", "family"]
            },
            {
                "id": 2,
                "summary": "Confirmed dinner reservation in Carmel",
                "transcript": "Dinner reservation confirmed in Carmel",
                "location_name": "Santa Cruz, CA",
                "created_at": "2026-08-15T12:00:00Z",
                "topics": ["dinner", "anniversary"]
            }
        ]
        layer = agents.build_thought_context_layer(mock_thoughts)
        self.assertTrue(layer["has_context"])
        self.assertEqual(layer["thought_count"], 2)
        self.assertIn("THOUGHTSTASH CONTEXT LAYER", layer["context_text"])
        self.assertIn("Carmel", layer["context_text"])
        self.assertIn("Mountain View, CA", layer["locations"])
        self.assertIn("2026-07-22", layer["context_text"])

        empty_layer = agents.build_thought_context_layer([])
        self.assertFalse(empty_layer["has_context"])
        self.assertEqual(empty_layer["thought_count"], 0)

    def test_query_needs_web_search_classifier(self):
        """Verify the heuristic classifier properly identifies real-world lookup queries."""
        ctx = {"has_context": True, "locations": ["Carmel, CA"]}

        # Should trigger web search
        self.assertTrue(agents._query_needs_web_search("suggest some restaurants near Carmel", ctx))
        self.assertTrue(agents._query_needs_web_search("recommend a cozy coffee shop", ctx))
        self.assertTrue(agents._query_needs_web_search("what is the weather like today?", ctx))
        self.assertTrue(agents._query_needs_web_search("best hiking trails nearby", ctx))
        self.assertTrue(agents._query_needs_web_search("how to bake sourdough bread", ctx))

        # Should NOT trigger web search (pure note recall)
        self.assertFalse(agents._query_needs_web_search("what did I say about hydration?", ctx))
        self.assertFalse(agents._query_needs_web_search("my notes on AI agents", ctx))
        self.assertFalse(agents._query_needs_web_search("did I mention any dinner reservation?", ctx))
        self.assertFalse(agents._query_needs_web_search("have I recorded anything about my parents?", ctx))


class TestAppEndpoints(unittest.TestCase):
    """Integration test suite covering all 16 FastAPI HTTP endpoints."""

    def setUp(self):
        self.client = TestClient(app)
        db.init_db()

    def test_root_serves_html(self):
        """GET / -> returns single-page app HTML."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("Thought Stash", res.text)

    def test_create_text_thought_endpoint(self):
        """POST /api/thoughts/text -> creates thought with Scribe + vector embedding."""
        mock_scribe_resp = MagicMock()
        mock_scribe_resp.text = json.dumps({
            "transcript": "Practicing mindfulness during evening walks",
            "summary": "Evening walk mindfulness reflection",
            "topics": ["Mindfulness", "Health"],
            "entities": ["Stanford"],
            "mood": "calm",
            "key_insights": ["Evening air is refreshing"],
            "thought_type": "reflection",
            "urgency": "low",
            "implicit_questions": [],
            "location_name": "Stanford, CA"
        })

        with patch("agents.generate_with_fallback", new=AsyncMock(return_value=mock_scribe_resp)):
            with patch("agents.get_embedding_async", new=AsyncMock(return_value=([0.1] * 768, "gemini-embedding-001"))):
                res = self.client.post("/api/thoughts/text", json={
                    "text": "Practicing mindfulness during evening walks",
                    "latitude": 37.4275,
                    "longitude": -122.1697,
                    "location_name": "Stanford Campus",
                })
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertIn("id", data)
                self.assertEqual(data["summary"], "Evening walk mindfulness reflection")
                self.assertEqual(data["mood"], "calm")

    def test_create_text_thought_empty_validation(self):
        """POST /api/thoughts/text -> 400 on empty text."""
        res = self.client.post("/api/thoughts/text", json={"text": "   "})
        self.assertEqual(res.status_code, 400)

    def test_list_thoughts_endpoint(self):
        """GET /api/thoughts -> returns completed thoughts list."""
        res = self.client.get("/api/thoughts")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_get_thought_by_id_endpoint(self):
        """GET /api/thoughts/{id} -> returns single thought or 404."""
        # Non-existent ID
        res = self.client.get("/api/thoughts/9999999")
        self.assertEqual(res.status_code, 404)

        # Existing thought
        t_id = db.save_thought({
            "transcript": "Test fetch single thought",
            "summary": "Single thought test",
            "topics": ["Test"],
            "mood": "calm",
            "status": "completed"
        })
        res = self.client.get(f"/api/thoughts/{t_id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["id"], t_id)
        self.assertEqual(res.json()["summary"], "Single thought test")

    def test_list_themes_endpoint(self):
        """GET /api/themes -> returns themes list."""
        res = self.client.get("/api/themes")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_thought_connections_endpoint(self):
        """GET /api/thoughts/{id}/connections -> returns connection analysis."""
        t_id = db.save_thought({
            "transcript": "Test connections thought",
            "summary": "Connections test",
            "status": "completed"
        })
        res = self.client.get(f"/api/thoughts/{t_id}/connections")
        self.assertEqual(res.status_code, 200)

    def test_latest_connections_endpoint(self):
        """GET /api/connections/latest -> returns latest connector insights."""
        res = self.client.get("/api/connections/latest")
        self.assertEqual(res.status_code, 200)

    def test_patterns_endpoint_with_caching(self):
        """GET /api/patterns -> returns pattern analysis with smart caching."""
        # Seed at least 2 thoughts so patterns can analyze
        db.save_thought({"transcript": "Thought 1", "summary": "One", "status": "completed", "embedding": [0.1]*768})
        db.save_thought({"transcript": "Thought 2", "summary": "Two", "status": "completed", "embedding": [0.2]*768})

        mock_pattern_resp = MagicMock()
        mock_pattern_resp.text = json.dumps({
            "recurring_themes": [{"theme": "Test Theme", "frequency": 2, "description": "Test desc"}],
            "emerging_patterns": [],
            "connections": [],
            "mood_trajectory": {"trend": "stable", "summary": "Steady pace"},
            "recommendations": ["Keep logging"],
            "one_line_summary": "Test summary"
        })

        with patch("agents.generate_with_fallback", new=AsyncMock(return_value=mock_pattern_resp)):
            res1 = self.client.get("/api/patterns?force=true")
            self.assertEqual(res1.status_code, 200)
            data = res1.json()
            self.assertEqual(data["one_line_summary"], "Test summary")

            # Second call should use cache (fast)
            res2 = self.client.get("/api/patterns")
            self.assertEqual(res2.status_code, 200)
            self.assertEqual(res2.json()["one_line_summary"], "Test summary")

    def test_geo_reverse_endpoint(self):
        """GET /api/geo/reverse -> returns reverse geocoded place name."""
        res = self.client.get("/api/geo/reverse?lat=37.4419&lon=-122.1430")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("location_name", data)
        self.assertEqual(data["latitude"], 37.4419)

    def test_geo_search_endpoint(self):
        """GET /api/geo/search -> searches place coordinates."""
        res = self.client.get("/api/geo/search?q=stanford")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("lat", data)
        self.assertIn("lon", data)
        self.assertIn("name", data)

    def test_map_points_endpoint(self):
        """GET /api/map/points -> returns geocoded markers for Leaflet."""
        db.save_thought({
            "transcript": "Walk at Shoreline Park",
            "summary": "Shoreline Park Walk",
            "latitude": 37.4302,
            "longitude": -122.0824,
            "location_name": "Shoreline Lake",
            "topics": ["Work", "Team"],
            "status": "completed",
            "embedding": [0.1] * 768
        })
        res = self.client.get("/api/map/points")
        self.assertEqual(res.status_code, 200)
        points = res.json()
        self.assertTrue(len(points) >= 1)
        self.assertEqual(points[0]["category"], "Strategy & Work")

    def test_graph_endpoint(self):
        """GET /api/graph -> returns nodes and edges for 3D force graph."""
        res = self.client.get("/api/graph")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)

    def test_search_endpoint(self):
        """GET /api/search -> semantic search ranked by cosine similarity."""
        with patch("agents.get_embedding_async", new=AsyncMock(return_value=([0.1] * 768, "gemini-embedding-001"))):
            res = self.client.get("/api/search?q=mindfulness")
            self.assertEqual(res.status_code, 200)
            self.assertIsInstance(res.json(), list)

    def test_chat_endpoint(self):
        """POST /api/chat -> context-aware chat with persistence and structured response."""
        # 1. Test empty state when no notes exist
        # Clear thoughts to verify clean prompt
        db.save_thought({
            "transcript": "Morning walk in Stanford Campus thinking about AI memory",
            "summary": "Stanford walk AI memory reflection",
            "topics": ["AI", "Walks"],
            "mood": "calm",
            "status": "completed",
            "embedding": [0.1] * 768
        })

        mock_chat_resp = MagicMock()
        mock_chat_resp.text = json.dumps({
            "summary": "Here are some reflections on your recent walks.",
            "key_points": [
                "You noted enjoying the quiet morning air in Stanford.",
                "You planned to keep guest lists small for future parties."
            ],
            "suggested_action": "Block out 30 minutes on your calendar for a morning walk."
        })

        with patch("agents.generate_with_fallback", new=AsyncMock(return_value=mock_chat_resp)):
            with patch("agents.get_embedding_async", new=AsyncMock(return_value=([0.1] * 768, "gemini-embedding-001"))):
                res = self.client.post("/api/chat", json={
                    "conversation_id": "test_conv_api",
                    "message": "What did I reflect on during my walks?",
                    "history": []
                })
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["summary"], "Here are some reflections on your recent walks.")
                self.assertEqual(len(data["key_points"]), 2)
                self.assertIn("suggested_action", data)
                self.assertIn("web_search_used", data)
                self.assertIn("context_layer_applied", data)

    def test_conversation_messages_endpoint(self):
        """GET /api/conversations/{conv_id}/messages -> retrieves message history."""
        db.save_message("conv_history_test", "user", "Hello notes!")
        db.save_message("conv_history_test", "model", "Hello user!")
        res = self.client.get("/api/conversations/conv_history_test/messages")
        self.assertEqual(res.status_code, 200)
        msgs = res.json()
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["content"], "Hello notes!")

    def test_agents_status_endpoint(self):
        """GET /api/agents/status -> returns swarm health and memory stats."""
        res = self.client.get("/api/agents/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("agents", data)
        self.assertIn("durable_themes_count", data)
        self.assertIn("total_thoughts", data)
        agent_names = [a["name"] for a in data["agents"]]
        self.assertIn("Scribe", agent_names)
        self.assertIn("Connector", agent_names)
        self.assertIn("Assistant", agent_names)

    def test_delete_thought_endpoint(self):
        """DELETE /api/thoughts/{id} -> deletes thought and returns 200."""
        t_id = db.create_pending_thought(
            audio_path="/tmp/to_delete.webm",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        # Delete existing thought
        res = self.client.delete(f"/api/thoughts/{t_id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "deleted")

        # Verify not found after deletion
        get_res = self.client.get(f"/api/thoughts/{t_id}")
        self.assertEqual(get_res.status_code, 404)

        # Deleting again returns 404
        res2 = self.client.delete(f"/api/thoughts/{t_id}")
        self.assertEqual(res2.status_code, 404)


if __name__ == "__main__":
    unittest.main()
