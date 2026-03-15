"""Medium tests — edge cases, error handling, and combined tool workflows."""

import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox import run_command
from tools import dispatch
from agent import load_dotenv, get_config


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


if __name__ == "__main__":
    unittest.main()
