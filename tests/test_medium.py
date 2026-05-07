"""Medium tests — edge cases, error handling, and combined tool workflows."""

import json
import os
import sys
import tempfile
import shutil
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools
from sandbox import run_command
from tools import dispatch
from agent import (
    load_dotenv,
    get_config,
    setup_logging,
    LOGGER,
    process_tool_calls,
    SubagentOrchestrator,
)


# ---------------------------------------------------------------------------
# Dispatch edge cases
# ---------------------------------------------------------------------------

class TestDispatchErrors(unittest.TestCase):
    """Dispatch should handle bad inputs gracefully without raising."""

    def test_unknown_tool(self):
        result = dispatch("nonexistent_tool", "{}")
        self.assertIn("Unknown tool", result)

    def test_invalid_json(self):
        result = dispatch("read_file", "not json at all")
        self.assertIn("Error", result)

    def test_empty_json(self):
        result = dispatch("read_file", "")
        # Missing 'path' key — should error, not crash
        self.assertIsInstance(result, str)

    def test_extra_args_ignored(self):
        result = dispatch("list_directory", json.dumps({"path": ".", "extra": "ignored"}))
        self.assertIn("agent.py", result)


# ---------------------------------------------------------------------------
# read_file edge cases
# ---------------------------------------------------------------------------

class TestReadFileEdges(unittest.TestCase):

    def test_nonexistent_file(self):
        result = dispatch("read_file", json.dumps({"path": "/no/such/file.txt"}))
        self.assertIn("Error", result)

    def test_read_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            path = f.name
        try:
            result = dispatch("read_file", json.dumps({"path": path}))
            self.assertEqual(result, "")
        finally:
            os.unlink(path)

    def test_read_unicode_content(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as f:
            f.write("café résumé naïve")
            path = f.name
        try:
            result = dispatch("read_file", json.dumps({"path": path}))
            self.assertIn("café", result)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# write_file edge cases
# ---------------------------------------------------------------------------

class TestWriteFileEdges(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_creates_nested_directories(self):
        path = os.path.join(self.tmpdir, "a", "b", "c", "file.txt")
        result = dispatch("write_file", json.dumps({"path": path, "content": "deep"}))
        self.assertIn("Successfully wrote", result)
        with open(path) as f:
            self.assertEqual(f.read(), "deep")

    def test_overwrite_existing(self):
        path = os.path.join(self.tmpdir, "overwrite.txt")
        dispatch("write_file", json.dumps({"path": path, "content": "first"}))
        dispatch("write_file", json.dumps({"path": path, "content": "second"}))
        with open(path) as f:
            self.assertEqual(f.read(), "second")

    def test_write_empty_content(self):
        path = os.path.join(self.tmpdir, "empty.txt")
        result = dispatch("write_file", json.dumps({"path": path, "content": ""}))
        self.assertIn("Successfully wrote 0 bytes", result)


# ---------------------------------------------------------------------------
# run_command edge cases
# ---------------------------------------------------------------------------

class TestRunCommandEdges(unittest.TestCase):

    def test_timeout(self):
        result = run_command("sleep 10", timeout=1)
        self.assertEqual(result["returncode"], -1)
        self.assertIn("timed out", result["stderr"])

    def test_stderr_captured(self):
        result = dispatch("run_command", json.dumps({
            "command": "python -c \"import sys; sys.stderr.write('oops')\"",
        }))
        self.assertIn("oops", result)

    def test_custom_timeout_via_dispatch(self):
        result = dispatch("run_command", json.dumps({
            "command": "echo fast",
            "timeout": 5,
        }))
        self.assertIn("fast", result)
        self.assertIn("Return code: 0", result)

    def test_pipe_command(self):
        result = dispatch("run_command", json.dumps({
            "command": "echo hello world | grep hello",
        }))
        self.assertIn("hello world", result)

    def test_nonzero_exit_still_returns_output(self):
        result = dispatch("run_command", json.dumps({
            "command": "echo before_fail && python -c \"raise SystemExit(1)\"",
        }))
        self.assertIn("before_fail", result)
        self.assertIn("Return code: 1", result)


# ---------------------------------------------------------------------------
# list_directory edge cases
# ---------------------------------------------------------------------------

class TestListDirectoryEdges(unittest.TestCase):

    def test_nonexistent_directory(self):
        result = dispatch("list_directory", json.dumps({"path": "/no/such/dir"}))
        self.assertIn("Error", result)

    def test_empty_directory(self):
        tmpdir = tempfile.mkdtemp()
        try:
            result = dispatch("list_directory", json.dumps({"path": tmpdir}))
            self.assertIn("empty", result)
        finally:
            os.rmdir(tmpdir)

    def test_sorted_output(self):
        result = dispatch("list_directory", json.dumps({"path": "."}))
        lines = [l.strip() for l in result.split("\n") if l.strip().startswith("[")]
        names = [l.split("] ")[1] for l in lines]
        self.assertEqual(names, sorted(names))


# ---------------------------------------------------------------------------
# search_files edge cases
# ---------------------------------------------------------------------------

class TestSearchFilesEdges(unittest.TestCase):

    def test_search_specific_directory(self):
        result = dispatch("search_files", json.dumps({"pattern": "import", "path": "tests"}))
        self.assertIn("test_easy.py", result)

    def test_search_pattern_with_spaces(self):
        result = dispatch("search_files", json.dumps({"pattern": "def get_config"}))
        self.assertIn("agent.py", result)


# ---------------------------------------------------------------------------
# Combined tool workflows
# ---------------------------------------------------------------------------

class TestCombinedWorkflows(unittest.TestCase):
    """Test multi-tool sequences like an agent would use them."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_then_read_roundtrip(self):
        path = os.path.join(self.tmpdir, "roundtrip.py")
        content = "print('hello from test')\n"
        dispatch("write_file", json.dumps({"path": path, "content": content}))
        result = dispatch("read_file", json.dumps({"path": path}))
        self.assertEqual(result, content)

    def test_write_run_verify(self):
        """Write a script, execute it, verify output."""
        path = os.path.join(self.tmpdir, "script.py")
        dispatch("write_file", json.dumps({
            "path": path,
            "content": "print(2 + 2)",
        }))
        result = dispatch("run_command", json.dumps({
            "command": f"python \"{path}\"",
        }))
        self.assertIn("4", result)
        self.assertIn("Return code: 0", result)

    def test_write_list_search(self):
        """Write a file, list its directory, search for content in it."""
        path = os.path.join(self.tmpdir, "findme.py")
        dispatch("write_file", json.dumps({
            "path": path,
            "content": "def unique_marker_xyz(): pass\n",
        }))
        # List should show the file
        ls_result = dispatch("list_directory", json.dumps({"path": self.tmpdir}))
        self.assertIn("findme.py", ls_result)
        # Search should find the marker
        search_result = dispatch("search_files", json.dumps({
            "pattern": "unique_marker_xyz",
            "path": self.tmpdir,
        }))
        self.assertIn("findme.py", search_result)

    def test_write_modify_read(self):
        """Write, overwrite, verify only latest content remains."""
        path = os.path.join(self.tmpdir, "evolve.txt")
        dispatch("write_file", json.dumps({"path": path, "content": "version 1"}))
        dispatch("write_file", json.dumps({"path": path, "content": "version 2"}))
        result = dispatch("read_file", json.dumps({"path": path}))
        self.assertEqual(result, "version 2")
        self.assertNotIn("version 1", result)


class TestSubagentOrchestrationWorkflows(unittest.TestCase):
    """Validate subagent orchestration semantics in process_tool_calls."""

    def test_process_tool_calls_schedules_subagents_concurrently_and_returns_structured_messages(self):
        orchestrator = SubagentOrchestrator(max_workers=2, poll_interval=0.01)
        inflight = 0
        max_inflight = 0
        lock = threading.Lock()

        def fake_dispatch(name, args):
            nonlocal inflight, max_inflight
            with lock:
                inflight += 1
                max_inflight = max(max_inflight, inflight)
            try:
                time.sleep(0.15)
                return f"completed {name}"
            finally:
                with lock:
                    inflight -= 1

        tool_calls = [
            {
                "id": "call_a",
                "function": {
                    "name": "subagent_create_task",
                    "arguments": json.dumps({"role": "research", "task": "task A"}),
                },
            },
            {
                "id": "call_b",
                "function": {
                    "name": "subagent_create_task",
                    "arguments": json.dumps({"role": "monitoring", "task": "task B"}),
                },
            },
        ]

        try:
            with unittest.mock.patch("agent.dispatch", side_effect=fake_dispatch):
                first_results, has_pending = process_tool_calls(tool_calls, orchestrator)
                self.assertEqual(first_results, [])
                self.assertTrue(has_pending)

                time.sleep(0.2)
                final_results, has_pending = process_tool_calls([], orchestrator)

            self.assertFalse(has_pending)
            self.assertGreaterEqual(max_inflight, 2)
            self.assertEqual(len(final_results), 2)

            for message in final_results:
                self.assertEqual(message["role"], "tool")
                self.assertIn(message["tool_call_id"], {"call_a", "call_b"})

                payload = json.loads(message["content"])
                self.assertEqual(payload["status"], "completed")
                self.assertIn("subagent", payload)
                self.assertIn("task_id", payload["subagent"])
                self.assertIn("role", payload["subagent"])
                self.assertEqual(payload["error"], None)
                self.assertIn("completed subagent_create_task", payload["output"])
        finally:
            orchestrator.shutdown()


class TestSubagentCoordinationCommands(unittest.TestCase):
    """Validate dispatch integration for coordination commands."""

    def setUp(self):
        tools._ORCHESTRATION_STATE["tasks"].clear()
        tools._ORCHESTRATION_STATE["next_id"] = 1
        tools._ORCHESTRATION_HANDLERS = {}

    def test_status_list_cancel_collect_lifecycle(self):
        created = json.loads(
            dispatch(
                "subagent_create_task",
                json.dumps({"role": "research", "task": "gather data"}),
            )
        )
        self.assertTrue(created["ok"])
        task_id = created["task"]["task_id"]

        status = json.loads(dispatch("subagent_task_status", json.dumps({"task_id": task_id})))
        self.assertTrue(status["ok"])
        self.assertEqual(status["task"]["status"], "created")

        listed = json.loads(dispatch("subagent_list_tasks", json.dumps({"role": "research"})))
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["tasks"][0]["task_id"], task_id)

        cancelled = json.loads(
            dispatch(
                "subagent_cancel_task",
                json.dumps({"task_id": task_id, "reason": "no longer needed"}),
            )
        )
        self.assertTrue(cancelled["ok"])
        self.assertEqual(cancelled["task"]["status"], "cancelled")
        self.assertEqual(cancelled["task"]["error"], "no longer needed")

        collected = json.loads(
            dispatch("subagent_collect_output", json.dumps({"task_id": task_id, "clear": True}))
        )
        self.assertTrue(collected["ok"])
        self.assertEqual(collected["task_id"], task_id)
        self.assertEqual(collected["status"], "cancelled")
        self.assertEqual(collected["error"], "no longer needed")

    def test_invalid_arguments_and_unknown_task_paths(self):
        invalid_role_result = dispatch(
            "subagent_create_task",
            json.dumps({"role": "invalid", "task": "x"}),
        )
        self.assertIn("Error", invalid_role_result)
        self.assertIn("Invalid role", invalid_role_result)

        invalid_list_role = dispatch("subagent_list_tasks", json.dumps({"role": "invalid"}))
        self.assertIn("Error", invalid_list_role)
        self.assertIn("Invalid role", invalid_list_role)

        missing_arg = dispatch("subagent_task_status", json.dumps({}))
        self.assertIn("Missing required argument", missing_arg)

        unknown_status = json.loads(dispatch("subagent_task_status", json.dumps({"task_id": "task-999"})))
        self.assertFalse(unknown_status["ok"])
        self.assertIn("Unknown task_id", unknown_status["error"])

        unknown_cancel = json.loads(dispatch("subagent_cancel_task", json.dumps({"task_id": "task-999"})))
        self.assertFalse(unknown_cancel["ok"])
        self.assertIn("Unknown task_id", unknown_cancel["error"])

        unknown_collect = json.loads(dispatch("subagent_collect_output", json.dumps({"task_id": "task-999"})))
        self.assertFalse(unknown_collect["ok"])
        self.assertIn("Unknown task_id", unknown_collect["error"])


# ---------------------------------------------------------------------------
# Logging configuration / persistence
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Logging configuration / persistence
# ---------------------------------------------------------------------------

class TestLoggingConfig(unittest.TestCase):
    """Logging should support file persistence and logger-backed runtime paths."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._env_backup = {
            "AGENT_LOG_FILE": os.environ.get("AGENT_LOG_FILE"),
            "AGENT_LOG_LEVEL": os.environ.get("AGENT_LOG_LEVEL"),
            "AGENT_LOG_CONSOLE": os.environ.get("AGENT_LOG_CONSOLE"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY"),
            "OPENROUTER_MODEL": os.environ.get("OPENROUTER_MODEL"),
        }
        self._clear_logger_handlers()

    def tearDown(self):
        self._clear_logger_handlers()
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _clear_logger_handlers(self):
        for handler in list(LOGGER.handlers):
            handler.close()
            LOGGER.removeHandler(handler)

    def test_get_config_writes_logs_to_configured_file(self):
        log_path = os.path.join(self.tmpdir, "agent-test.log")
        os.environ["AGENT_LOG_FILE"] = log_path
        os.environ["AGENT_LOG_LEVEL"] = "INFO"
        os.environ["AGENT_LOG_CONSOLE"] = "false"
        os.environ["OPENROUTER_API_KEY"] = "test-api-key"

        api_key, model = get_config()

        self.assertEqual(api_key, "test-api-key")
        self.assertEqual(model, "minimax/minimax-m2.5")
        self.assertTrue(os.path.exists(log_path))
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Configuration loaded. Model", content)

    def test_process_tool_calls_logs_runtime_events(self):
        log_path = os.path.join(self.tmpdir, "agent-runtime.log")
        setup_logging(log_file=log_path, log_level="INFO", console_enabled=False)

        orchestrator = SubagentOrchestrator(max_workers=1, poll_interval=0.01)
        tool_calls = [{
            "id": "call_1",
            "function": {
                "name": "subagent_create_task",
                "arguments": json.dumps({"role": "research", "task": "scan sample.txt"}),
            },
        }]

        aggregated_results = []
        try:
            with unittest.mock.patch("agent.dispatch", return_value="tool output"):
                result, has_pending = process_tool_calls(tool_calls, orchestrator)
                aggregated_results.extend(result)

                if has_pending:
                    time.sleep(0.05)
                    result, _ = process_tool_calls([], orchestrator)
                    aggregated_results.extend(result)
        finally:
            orchestrator.shutdown()

        for handler in LOGGER.handlers:
            if hasattr(handler, "flush"):
                handler.flush()

        self.assertEqual(len(aggregated_results), 1)
        payload = json.loads(aggregated_results[0]["content"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["output"], "tool output")

        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("🔧 subagent_create_task", content)
        self.assertIn("Created subagent task subagent-call_1", content)
        self.assertIn("Scheduled subagent task subagent-call_1", content)
        self.assertIn("Subagent task subagent-call_1 completed", content)
        self.assertIn("Aggregated 1 completed subagent result(s).", content)


# ---------------------------------------------------------------------------
# Config / dotenv
# ---------------------------------------------------------------------------

class TestConfig(unittest.TestCase):

    def test_load_dotenv_sets_vars(self):
        load_dotenv()
        self.assertIsNotNone(os.environ.get("OPENROUTER_API_KEY"))

    def test_model_from_env(self):
        load_dotenv()
        _, model = get_config()
        self.assertEqual(model, "minimax/minimax-m2.5")
        self.assertGreaterEqual(len(LOGGER.handlers), 1)


if __name__ == "__main__":
    unittest.main()