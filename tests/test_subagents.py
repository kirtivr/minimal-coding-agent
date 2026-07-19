"""Tests for subagent architecture and tool dispatch integration."""

import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from subagents import SubagentManager
from tools import (
    dispatch,
    set_subagent_manager,
    SUBAGENT_MANAGER,
)


def mock_agent_function(task_description: str) -> str:
    """Mock agent function for testing subagent tasks without API calls."""
    return f"Mock result for: {task_description}"


def slow_mock_agent_function(task_description: str) -> str:
    """Slow mock agent function to test timeouts and waiting."""
    time.sleep(0.5)
    return f"Slow result for: {task_description}"


class TestSubagentManager(unittest.TestCase):
    """Test SubagentManager spawning, lifecycle, and result tracking."""

    def setUp(self):
        self.manager = SubagentManager(task_runner=mock_agent_function)

    def test_spawn_returns_valid_id(self):
        subagent_id = self.manager.spawn(lambda: "test", "test task")
        self.assertIsInstance(subagent_id, str)
        self.assertTrue(len(subagent_id) > 0)

    def test_spawn_status_lifecycle(self):
        subagent_id = self.manager.spawn(lambda: "result", "lifecycle test")
        # Immediately after spawn, status should be pending or running
        status = self.manager.get_status(subagent_id)
        self.assertIn(status, ["pending", "running"])

        # Wait for completion
        finished = self.manager.wait_for(subagent_id, timeout=5.0)
        self.assertTrue(finished)

        status = self.manager.get_status(subagent_id)
        self.assertEqual(status, "completed")

    def test_parallel_execution(self):
        # Spawn multiple subagents that sleep briefly
        ids = []
        for i in range(3):
            def make_task(idx):
                def task():
                    time.sleep(0.1)
                    return f"task {idx}"
                return task

            sid = self.manager.spawn(make_task(i), f"parallel {i}")
            ids.append(sid)

        # All should exist
        self.assertEqual(len(self.manager.list_subagents()), 3)

        # Wait for all
        for sid in ids:
            finished = self.manager.wait_for(sid, timeout=5.0)
            self.assertTrue(finished)
            result = self.manager.get_result(sid)
            self.assertEqual(result["status"], "completed")

    def test_wait_for_completion(self):
        subagent_id = self.manager.spawn(lambda: "done", "wait test")
        finished = self.manager.wait_for(subagent_id, timeout=5.0)
        self.assertTrue(finished)

    def test_wait_for_timeout(self):
        subagent_id = self.manager.spawn(lambda: time.sleep(10), "slow task")
        finished = self.manager.wait_for(subagent_id, timeout=0.1)
        self.assertFalse(finished)
        # Clean up by waiting properly
        self.manager.wait_for(subagent_id, timeout=15.0)

    def test_wait_for_unknown(self):
        finished = self.manager.wait_for("nonexistent-id", timeout=1.0)
        self.assertFalse(finished)

    def test_list_subagents(self):
        self.assertEqual(self.manager.list_subagents(), [])
        sid1 = self.manager.spawn(lambda: "a", "task a")
        sid2 = self.manager.spawn(lambda: "b", "task b")
        ids = self.manager.list_subagents()
        self.assertEqual(len(ids), 2)
        self.assertIn(sid1, ids)
        self.assertIn(sid2, ids)

    def test_get_result_success(self):
        subagent_id = self.manager.spawn(lambda: "success", "success task")
        self.manager.wait_for(subagent_id, timeout=5.0)
        result = self.manager.get_result(subagent_id)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["result"], "success")
        self.assertIsNone(result["error"])

    def test_get_result_failure(self):
        def fail_task():
            raise ValueError("boom")

        subagent_id = self.manager.spawn(fail_task, "fail task")
        self.manager.wait_for(subagent_id, timeout=5.0)
        result = self.manager.get_result(subagent_id)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["result"])
        self.assertIn("boom", result["error"])

    def test_get_result_unknown(self):
        result = self.manager.get_result("nonexistent-id")
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["result"])
        self.assertIn("not found", result["error"])

    def test_get_status_unknown(self):
        status = self.manager.get_status("nonexistent-id")
        self.assertIsNone(status)

    def test_task_runner_mock_integration(self):
        manager = SubagentManager(task_runner=mock_agent_function)
        subagent_id = manager.spawn(lambda: manager.task_runner("test desc"), "runner test")
        manager.wait_for(subagent_id, timeout=5.0)
        result = manager.get_result(subagent_id)
        self.assertEqual(result["status"], "completed")
        self.assertIn("Mock result for: test desc", result["result"])


class TestSubagentTools(unittest.TestCase):
    """Test tool dispatch integration for subagent operations."""

    def setUp(self):
        self.manager = SubagentManager(task_runner=mock_agent_function)
        set_subagent_manager(self.manager)

    def tearDown(self):
        set_subagent_manager(None)

    def _extract_subagent_id(self, spawn_result: str) -> str:
        """Helper to extract subagent id from spawn dispatch result."""
        self.assertIn("Spawned subagent", spawn_result)
        return spawn_result.split("Spawned subagent ")[1]

    def test_spawn_subagent_tool(self):
        result = dispatch("spawn_subagent", json.dumps({"task_description": "research task"}))
        subagent_id = self._extract_subagent_id(result)
        self.assertTrue(len(subagent_id) > 0)

    def test_spawn_subagent_tool_uses_task_runner(self):
        result = dispatch("spawn_subagent", json.dumps({"task_description": "runner task"}))
        subagent_id = self._extract_subagent_id(result)

        dispatch("wait_for_subagent", json.dumps({"subagent_id": subagent_id, "timeout": 5}))
        result = dispatch("get_subagent_result", json.dumps({"subagent_id": subagent_id}))
        data = json.loads(result)
        self.assertEqual(data["status"], "completed")
        self.assertIn("Mock result for: runner task", data["result"])

    def test_get_subagent_status_tool(self):
        result = dispatch("spawn_subagent", json.dumps({"task_description": "status test"}))
        subagent_id = self._extract_subagent_id(result)

        status = dispatch("get_subagent_status", json.dumps({"subagent_id": subagent_id}))
        self.assertIn(status, ["pending", "running", "completed"])

    def test_wait_for_subagent_tool(self):
        result = dispatch("spawn_subagent", json.dumps({"task_description": "wait test"}))
        subagent_id = self._extract_subagent_id(result)

        wait_result = dispatch("wait_for_subagent", json.dumps({"subagent_id": subagent_id, "timeout": 5}))
        self.assertIn(wait_result, ["Finished", "Timeout"])

    def test_list_subagents_tool(self):
        # Ensure at least one subagent exists
        dispatch("spawn_subagent", json.dumps({"task_description": "list test"}))
        result = dispatch("list_subagents", "{}")
        ids = json.loads(result)
        self.assertIsInstance(ids, list)
        self.assertGreaterEqual(len(ids), 1)

    def test_get_subagent_result_tool(self):
        result = dispatch("spawn_subagent", json.dumps({"task_description": "result test"}))
        subagent_id = self._extract_subagent_id(result)

        # Wait for it to finish
        dispatch("wait_for_subagent", json.dumps({"subagent_id": subagent_id, "timeout": 5}))

        result = dispatch("get_subagent_result", json.dumps({"subagent_id": subagent_id}))
        data = json.loads(result)
        self.assertEqual(data["status"], "completed")
        self.assertIn("Mock result for: result test", data["result"])

    def test_spawn_with_command(self):
        result = dispatch("spawn_subagent", json.dumps({
            "task_description": "echo test",
            "command": "echo hello_from_subagent",
        }))
        subagent_id = self._extract_subagent_id(result)

        dispatch("wait_for_subagent", json.dumps({"subagent_id": subagent_id, "timeout": 5}))
        result = dispatch("get_subagent_result", json.dumps({"subagent_id": subagent_id}))
        data = json.loads(result)
        self.assertEqual(data["status"], "completed")
        self.assertIn("hello_from_subagent", str(data["result"]))

    def test_tools_without_manager(self):
        set_subagent_manager(None)

        spawn_result = dispatch("spawn_subagent", json.dumps({"task_description": "test"}))
        self.assertIn("Subagent manager not initialized", spawn_result)

        status_result = dispatch("get_subagent_status", json.dumps({"subagent_id": "123"}))
        self.assertIn("Subagent manager not initialized", status_result)

        wait_result = dispatch("wait_for_subagent", json.dumps({"subagent_id": "123"}))
        self.assertIn("Subagent manager not initialized", wait_result)

        list_result = dispatch("list_subagents", "{}")
        self.assertIn("Subagent manager not initialized", list_result)

        result_result = dispatch("get_subagent_result", json.dumps({"subagent_id": "123"}))
        self.assertIn("Subagent manager not initialized", result_result)


if __name__ == "__main__":
    unittest.main()