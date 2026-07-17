"""Tests for subagent architecture and tool dispatch."""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from subagents import SubagentManager
from tools import dispatch


def _fake_openrouter_response(messages, tools, api_key, model):
    """Return a simple completion response for testing."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Fake subagent result",
                }
            }
        ]
    }


class TestSubagentManager(unittest.TestCase):
    """Tests for SubagentManager spawning, retrieval, and parallel execution."""

    def setUp(self):
        SubagentManager.reset_instance()
        self.manager = SubagentManager(api_key="test-key", model="test-model")

    def tearDown(self):
        SubagentManager.reset_instance()

    def test_spawn_returns_valid_id(self):
        with patch("subagents.call_openrouter", side_effect=_fake_openrouter_response):
            agent_id = self.manager.spawn("research", "do some research")
            subagent = self.manager.get(agent_id)
            subagent.join(timeout=5)
            self.assertTrue(agent_id.startswith("research-"))
            self.assertIsNotNone(subagent)
            self.assertEqual(subagent.agent_type, "research")
            self.assertEqual(subagent.task, "do some research")

    def test_spawn_invalid_agent_type(self):
        with self.assertRaises(ValueError) as ctx:
            self.manager.spawn("invalid_type", "task")
        self.assertIn("Unknown agent type", str(ctx.exception))

    def test_spawn_requires_api_key_and_model(self):
        SubagentManager.reset_instance()
        manager = SubagentManager()
        with self.assertRaises(ValueError) as ctx:
            manager.spawn("research", "task")
        self.assertIn("api_key and model are required", str(ctx.exception))

    def test_get_missing_returns_none(self):
        result = self.manager.get("nonexistent-id")
        self.assertIsNone(result)

    def test_list_all_empty(self):
        result = self.manager.list_all()
        self.assertEqual(result, [])

    def test_list_all_with_subagents(self):
        with patch("subagents.call_openrouter", side_effect=_fake_openrouter_response):
            id1 = self.manager.spawn("research", "task1")
            id2 = self.manager.spawn("monitoring", "task2")
            self.manager.get(id1).join(timeout=5)
            self.manager.get(id2).join(timeout=5)
            result = self.manager.list_all()
            self.assertEqual(len(result), 2)
            ids = {r["agent_id"] for r in result}
            self.assertEqual(ids, {id1, id2})
            types = {r["agent_type"] for r in result}
            self.assertEqual(types, {"research", "monitoring"})

    def test_parallel_spawn(self):
        with patch("subagents.call_openrouter", side_effect=_fake_openrouter_response):
            ids = [self.manager.spawn("research", f"task {i}") for i in range(5)]
            for agent_id in ids:
                self.manager.get(agent_id).join(timeout=5)
            self.assertEqual(len(ids), 5)
            self.assertEqual(len(set(ids)), 5)
            for agent_id in ids:
                subagent = self.manager.get(agent_id)
                self.assertIsNotNone(subagent)
                self.assertEqual(subagent.agent_type, "research")

    def test_shutdown_clears_subagents(self):
        with patch("subagents.call_openrouter", side_effect=_fake_openrouter_response):
            agent_id = self.manager.spawn("research", "task")
            self.manager.get(agent_id).join(timeout=5)
        self.manager.shutdown(timeout=5)
        self.assertEqual(self.manager.list_all(), [])
        self.assertIsNone(self.manager.get(agent_id))


class TestSubagentTools(unittest.TestCase):
    """Tests for subagent-related tool dispatch functions."""

    def setUp(self):
        SubagentManager.reset_instance()
        self.manager = SubagentManager(api_key="test-key", model="test-model")

    def tearDown(self):
        SubagentManager.reset_instance()

    def test_spawn_subagent_tool(self):
        with patch("subagents.call_openrouter", side_effect=_fake_openrouter_response):
            result = dispatch("spawn_subagent", json.dumps({
                "agent_type": "research",
                "task": "research task",
                "api_key": "test-key",
                "model": "test-model",
            }))
            self.assertIn("Spawned subagent", result)
            agent_id = result.replace("Spawned subagent ", "").strip()
            subagent = self.manager.get(agent_id)
            self.assertIsNotNone(subagent)
            subagent.join(timeout=5)
            self.assertTrue(agent_id.startswith("research-"))

    def test_spawn_subagent_tool_invalid_type(self):
        result = dispatch("spawn_subagent", json.dumps({
            "agent_type": "unknown",
            "task": "task",
            "api_key": "test-key",
            "model": "test-model",
        }))
        self.assertIn("Error", result)
        self.assertIn("Unknown agent type", result)

    def test_get_subagent_status_tool(self):
        with patch("subagents.call_openrouter", side_effect=_fake_openrouter_response):
            agent_id = self.manager.spawn("interacting", "chat task")
            self.manager.get(agent_id).join(timeout=5)
        result = dispatch("get_subagent_status", json.dumps({
            "agent_id": agent_id,
        }))
        data = json.loads(result)
        self.assertEqual(data["agent_id"], agent_id)
        self.assertEqual(data["agent_type"], "interacting")
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["result"], "Fake subagent result")

    def test_get_subagent_status_tool_missing(self):
        result = dispatch("get_subagent_status", json.dumps({
            "agent_id": "missing-id",
        }))
        self.assertIn("Error", result)
        self.assertIn("not found", result)

    def test_list_subagents_tool(self):
        with patch("subagents.call_openrouter", side_effect=_fake_openrouter_response):
            id1 = self.manager.spawn("research", "task1")
            id2 = self.manager.spawn("monitoring", "task2")
            self.manager.get(id1).join(timeout=5)
            self.manager.get(id2).join(timeout=5)
        result = dispatch("list_subagents", "{}")
        data = json.loads(result)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        types = {item["agent_type"] for item in data}
        self.assertEqual(types, {"research", "monitoring"})

    def test_list_subagents_tool_empty(self):
        result = dispatch("list_subagents", "{}")
        data = json.loads(result)
        self.assertEqual(data, [])


if __name__ == "__main__":
    unittest.main()