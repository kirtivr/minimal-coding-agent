"""Basic tests for the coding agent's tools — no API key needed."""

import json
import os
import sys
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
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "sample.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("alpha\nneedle-value\nomega\n")

        result = dispatch("search_files", json.dumps({"pattern": "needle-value", "path": tmpdir}))
        assert "sample.txt:2:needle-value" in result
    print("PASS: search_files")


def test_search_files_no_matches():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "sample.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("alpha\nbeta\ngamma\n")

        result = dispatch("search_files", json.dumps({"pattern": "does-not-exist", "path": tmpdir}))
        assert result == f"No matches found for 'does-not-exist' in '{tmpdir}'."
    print("PASS: search_files no matches")


def test_search_files_nested_paths_or_extension_filtering():
    with tempfile.TemporaryDirectory() as tmpdir:
        nested = os.path.join(tmpdir, "nested", "inner")
        os.makedirs(nested)

        py_file = os.path.join(nested, "keep.py")
        txt_file = os.path.join(tmpdir, "notes.txt")
        bin_file = os.path.join(nested, "skip.bin")

        with open(py_file, "w", encoding="utf-8") as f:
            f.write("TARGET_PATTERN = True\n")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("TARGET_PATTERN in text\n")
        with open(bin_file, "w", encoding="utf-8") as f:
            f.write("TARGET_PATTERN in excluded extension\n")

        result = dispatch("search_files", json.dumps({"pattern": "TARGET_PATTERN", "path": tmpdir}))
        assert "keep.py:1:TARGET_PATTERN = True" in result
        assert "notes.txt:1:TARGET_PATTERN in text" in result
        assert "skip.bin" not in result
    print("PASS: search_files nested paths + extension filtering")


def test_sandbox_timeout():
    command = f'"{sys.executable}" -c "import time; time.sleep(10)"'
    result = run_command(command, timeout=1)
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
    test_search_files_no_matches()
    test_search_files_nested_paths_or_extension_filtering()
    test_sandbox_timeout()
    test_dispatch_unknown_tool()
    test_dispatch_bad_json()
    print("\nAll tests passed!")