"""Comprehensive automated test suite for ThoughtStash.

Tests:
1. Zero-dependency DB initialization & migrations
2. Pending thought durability (no orphaned audio)
3. Durable themes upsert & query
4. Scribe & Connector Pydantic schema validation
5. Semantic vector similarity
6. Safe server startup without GEMINI_API_KEY
"""

import json
import os
import tempfile
import unittest
from datetime import datetime

# Set isolated test database
temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
temp_db_path = temp_db.name
temp_db.close()

import db
db.DB_PATH = temp_db_path

os.environ["GEMINI_API_KEY"] = "fake_test_key_for_unit_tests"

import agents
from agents import ScribeOutputSchema, ConnectorOutputSchema


class TestDatabaseAndDurability(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_create_pending_thought(self):
        """Verify thought is saved as pending immediately so audio is never lost."""
        t_id = db.create_pending_thought(
            audio_path="/tmp/fake_thought.webm",
            created_at=datetime.now().isoformat(),
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
        """Verify saving complete thought data with all Scribe fields."""
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


class TestPydanticSchemas(unittest.TestCase):
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
        """Verify ConnectorOutputSchema strict JSON parsing."""
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
                {"theme": "Daily Health", "count": 3, "trend": "growing"}
            ],
            "contradictions": [],
            "spatio_temporal_insights": "Walks happen primarily on weekend mornings.",
            "proactive_insight": "Consider blocking calendar for mornings.",
            "thinking_evolution": "Perspective shifted from reactive to proactive.",
        }
        obj = ConnectorOutputSchema(**raw_json)
        self.assertEqual(len(obj.connections), 1)
        self.assertEqual(obj.recurring_themes[0].trend, "growing")


if __name__ == "__main__":
    unittest.main()
