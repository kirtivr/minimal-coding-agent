"""Basic tests for the coding agent's tools — no API key needed."""

import json
import os
import tempfile
from tools import dispatch
from sandbox import run_command


def test_list_directory():
    result = dispatch("list_directory", json.dumps({"path": "."}))
    assert "agent.py" in result
    assert "tools.py" in result
    print("PASS: list_directory")


def test_read_file():
    result = dispatch("read_file", json.dumps({"path": "requirements.txt"}))
    assert "requests" in result
    print("PASS: read_file")


def test_write_and_read_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        path = f.name
    try:
        dispatch("write_file", json.dumps({"path": path, "content": "hello agent"}))
        result = dispatch("read_file", json.dumps({"path": path}))
        assert result == "hello agent"
        print("PASS: write_file + read_file roundtrip")
    finally:
        os.unlink(path)


def test_run_command():
    result = dispatch("run_command", json.dumps({"command": "echo test123"}))
    assert "test123" in result
    assert "Return code: 0" in result
    print("PASS: run_command")


def test_search_files():
    result = dispatch("search_files", json.dumps({"pattern": "def dispatch", "path": "."}))
    assert "tools.py" in result
    print("PASS: search_files")


def test_sandbox_timeout():
    result = run_command("sleep 10", timeout=1)
    assert result["returncode"] == -1
    assert "timed out" in result["stderr"]
    print("PASS: sandbox timeout")


def test_dispatch_unknown_tool():
    result = dispatch("nonexistent", "{}")
    assert "Unknown tool" in result
    print("PASS: unknown tool handling")


def test_dispatch_bad_json():
    result = dispatch("read_file", "not json")
    assert "Error" in result
    print("PASS: bad JSON handling")


if __name__ == "__main__":
    test_list_directory()
    test_read_file()
    test_write_and_read_file()
    test_run_command()
    test_search_files()
    test_sandbox_timeout()
    test_dispatch_unknown_tool()
    test_dispatch_bad_json()
    print("\nAll tests passed!")
