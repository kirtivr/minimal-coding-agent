"""Easy tests — happy-path validation for each tool and core modules."""

import json
import os
import sys
import tempfile
import unittest

# Allow imports from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox import run_command
from tools import TOOL_SCHEMAS, dispatch
from prompts import SYSTEM_PROMPT


class TestSystemPrompt(unittest.TestCase):
    """Verify the system prompt is present and well-formed."""

    def test_prompt_not_empty(self):
        self.assertTrue(len(SYSTEM_PROMPT) > 100)

    def test_prompt_mentions_tools(self):
        for tool in ["read_file", "write_file", "run_command", "list_directory", "search_files"]:
            self.assertIn(tool, SYSTEM_PROMPT)


class TestToolSchemas(unittest.TestCase):
    """Verify tool schemas are valid OpenAI function-calling format."""

    def test_schema_count(self):
        self.assertEqual(len(TOOL_SCHEMAS), 5)

    def test_schema_structure(self):
        for schema in TOOL_SCHEMAS:
            self.assertEqual(schema["type"], "function")
            self.assertIn("name", schema["function"])
            self.assertIn("parameters", schema["function"])
            self.assertIn("description", schema["function"])

    def test_schema_names(self):
        names = {s["function"]["name"] for s in TOOL_SCHEMAS}
        expected = {"read_file", "write_file", "run_command", "list_directory", "search_files"}
        self.assertEqual(names, expected)


class TestSandbox(unittest.TestCase):
    """Basic sandbox command execution."""

    def test_echo(self):
        result = run_command("echo hello")
        self.assertEqual(result["returncode"], 0)
        self.assertIn("hello", result["stdout"])

    def test_return_keys(self):
        result = run_command("echo test")
        self.assertIn("stdout", result)
        self.assertIn("stderr", result)
        self.assertIn("returncode", result)

    def test_failing_command(self):
        result = run_command("python -c \"raise SystemExit(42)\"")
        self.assertEqual(result["returncode"], 42)


class TestReadFile(unittest.TestCase):
    """Test read_file tool."""

    def test_read_existing_file(self):
        result = dispatch("read_file", json.dumps({"path": "requirements.txt"}))
        self.assertIn("requests", result)

    def test_read_self(self):
        result = dispatch("read_file", json.dumps({"path": "agent.py"}))
        self.assertIn("def agent_loop", result)


class TestWriteFile(unittest.TestCase):
    """Test write_file tool."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_write_and_verify(self):
        result = dispatch("write_file", json.dumps({"path": self.tmp.name, "content": "test content"}))
        self.assertIn("Successfully wrote", result)
        with open(self.tmp.name) as f:
            self.assertEqual(f.read(), "test content")


class TestRunCommand(unittest.TestCase):
    """Test run_command tool."""

    def test_simple_command(self):
        result = dispatch("run_command", json.dumps({"command": "python --version"}))
        self.assertIn("Python", result)
        self.assertIn("Return code: 0", result)

    def test_multiline_output(self):
        result = dispatch("run_command", json.dumps({"command": "echo line1 && echo line2"}))
        self.assertIn("line1", result)
        self.assertIn("line2", result)


class TestListDirectory(unittest.TestCase):
    """Test list_directory tool."""

    def test_current_directory(self):
        result = dispatch("list_directory", "{}")
        self.assertIn("agent.py", result)
        self.assertIn("[file]", result)

    def test_shows_dirs(self):
        result = dispatch("list_directory", "{}")
        self.assertIn("[dir]", result)
        self.assertIn("tests", result)


class TestSearchFiles(unittest.TestCase):
    """Test search_files tool."""

    def test_search_finds_matches(self):
        result = dispatch("search_files", json.dumps({"pattern": "def dispatch"}))
        self.assertIn("tools.py", result)

    def test_search_no_matches(self):
        # Search in a temp dir so the pattern can't match itself in this test file
        tmpdir = tempfile.mkdtemp()
        try:
            result = dispatch("search_files", json.dumps({"pattern": "nothing_here", "path": tmpdir}))
            self.assertIn("No matches", result)
        finally:
            os.rmdir(tmpdir)


if __name__ == "__main__":
    unittest.main()
