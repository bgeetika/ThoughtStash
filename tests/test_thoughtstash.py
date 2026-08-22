"""Comprehensive automated test suite for ThoughtStash.

Tests:
1. Zero-dependency DB initialization & migrations
2. Pending thought durability (no orphaned audio)
3. Durable themes upsert & query
4. Scribe & Connector Pydantic schema validation
5. P0 Regression: connector_analyze theme upsert loop execution
6. Daily rollups computation and retrieval
7. Server-side conversation & message persistence
8. Canonical cosine safety against mismatched vector dimensions
9. Embedding model provenance return
"""

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Set isolated test database
temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
temp_db_path = temp_db.name
temp_db.close()

import db
db.DB_PATH = temp_db_path

os.environ["GEMINI_API_KEY"] = "fake_test_key_for_unit_tests"

import agents
from agents import ScribeOutputSchema, ConnectorOutputSchema, FullPatternReport


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
            created_at="2026-08-22T10:00:00Z",
        )
        data = {
            "id": t_id,
            "created_at": "2026-08-22T10:00:00Z",
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
        rollups = db.get_recent_daily_rollups(10)
        dates = [r["date"] for r in rollups]
        self.assertIn("2026-08-22", dates)

    def test_durable_themes(self):
        """Verify persistent themes table upserts and tracking."""
        db.upsert_theme(
            name="Episodic Memory",
            description="Focus on human voice thought capture",
            trend="growing",
            thought_id=101,
            timestamp="2026-08-22T12:00:00Z",
        )
        db.upsert_theme(
            name="Episodic Memory",
            description="Focus on human voice thought capture",
            trend="growing",
            thought_id=102,
            timestamp="2026-08-22T13:00:00Z",
        )
        themes = db.get_all_themes()
        theme_names = [t["name"] for t in themes]
        self.assertIn("Episodic Memory", theme_names)
        target = next(t for t in themes if t["name"] == "Episodic Memory")
        self.assertEqual(target["frequency"], 2)
        self.assertIn(101, target["associated_thought_ids"])
        self.assertIn(102, target["associated_thought_ids"])

    def test_chat_persistence(self):
        """Verify server-side conversations and message persistence."""
        conv = db.get_or_create_conversation("test-conv-123", "Test Chat")
        self.assertEqual(conv["id"], "test-conv-123")

        msg_id1 = db.save_message("test-conv-123", "user", "What was I thinking about?")
        msg_id2 = db.save_message("test-conv-123", "model", "You were thinking about AI.")
        self.assertTrue(msg_id1 > 0)
        self.assertTrue(msg_id2 > msg_id1)

        messages = db.get_conversation_messages("test-conv-123")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "What was I thinking about?")
        self.assertEqual(messages[1]["role"], "model")

        db.update_conversation_pinned_thoughts("test-conv-123", [1, 2, 3])
        updated_conv = db.get_or_create_conversation("test-conv-123")
        self.assertEqual(updated_conv["pinned_thought_ids"], [1, 2, 3])

    def test_safe_cosine_dimension_mismatch(self):
        """Verify cosine similarity never raises ValueError on mismatched dimensions."""
        vec3 = [1.0, 2.0, 3.0]
        vec5 = [1.0, 2.0, 3.0, 4.0, 5.0]
        empty = []
        
        # Mismatched lengths should return 0.0 without exception
        self.assertEqual(db.cosine(vec3, vec5), 0.0)
        self.assertEqual(db.cosine(vec3, empty), 0.0)
        self.assertEqual(db.cosine(empty, empty), 0.0)
        
        # Matching lengths compute valid similarity
        self.assertAlmostEqual(db.cosine([1.0, 0.0], [1.0, 0.0]), 1.0)


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
                    "theme": "Agent Autonomy",
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
            
            # Execute connector_analyze
            result = asyncio.run(agents.connector_analyze(thought_data, past_thoughts=[]))
            
            # Verify result returned
            self.assertIn("recurring_themes", result)
            self.assertEqual(len(result["recurring_themes"]), 1)
            
            # Verify theme was actually written into SQLite themes table
            themes = db.get_all_themes()
            theme_names = [th["name"] for th in themes]
            self.assertIn("Agent Autonomy", theme_names)
            
            saved_theme = next(th for th in themes if th["name"] == "Agent Autonomy")
            self.assertEqual(saved_theme["description"], "Exploration of long-horizon AI agent state")
            self.assertIn(999, saved_theme["associated_thought_ids"])

    def test_text_thought_persistence(self):
        """Verify text-based thought creation and retrieval in database."""
        thought_data = {
            "created_at": "2026-08-22T17:30:00Z",
            "audio_path": None,
            "transcript": "Minimal and clean UI design test",
            "summary": "Design test for minimal UI",
            "topics": ["Design", "UI"],
            "mood": "creative",
            "location_name": "San Francisco, CA",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "embedding": [0.1] * 768,
            "embedding_model": "test-model",
            "raw_response": "{}"
        }
        t_id = db.save_thought(thought_data)
        self.assertIsInstance(t_id, int)
        retrieved = db.get_thought_by_id(t_id)
        self.assertEqual(retrieved["summary"], "Design test for minimal UI")
        self.assertEqual(retrieved["location_name"], "San Francisco, CA")

    def test_geocoding_utilities(self):
        """Verify reverse geocoding and place searching."""
        import geocode
        known = geocode.search_place("Rancho San Antonio")
        self.assertIsNotNone(known)
        self.assertEqual(known["lat"], 37.3328)

        rev = geocode.reverse_geocode(37.4419, -122.1430)
        self.assertTrue(len(rev) > 0)
        self.assertIn("Palo Alto", rev)


if __name__ == "__main__":
    unittest.main()
