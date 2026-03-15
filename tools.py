"""Tool schemas and dispatch for the coding agent."""

import os
import json
from sandbox import run_command as sandbox_run

# --- Tool Schemas (OpenAI function-calling format) ---

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating or overwriting it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list (default: current directory)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a text pattern in files, like grep.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: current directory)",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]

# --- Tool Implementations ---


def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(path: str, content: str) -> str:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def _run_command(command: str, timeout: int = 30) -> str:
    result = sandbox_run(command, timeout)
    parts = []
    if result["stdout"]:
        parts.append(f"STDOUT:\n{result['stdout']}")
    if result["stderr"]:
        parts.append(f"STDERR:\n{result['stderr']}")
    parts.append(f"Return code: {result['returncode']}")
    return "\n".join(parts)


def list_directory(path: str = ".") -> str:
    try:
        entries = os.listdir(path)
        if not entries:
            return f"Directory '{path}' is empty."
        result = []
        for entry in sorted(entries):
            full = os.path.join(path, entry)
            kind = "dir" if os.path.isdir(full) else "file"
            result.append(f"  [{kind}] {entry}")
        return f"Contents of '{path}':\n" + "\n".join(result)
    except Exception as e:
        return f"Error listing directory: {e}"


def search_files(pattern: str, path: str = ".") -> str:
    cmd = f'grep -rn --include="*.py" --include="*.txt" --include="*.md" --include="*.json" --include="*.yaml" --include="*.yml" --include="*.toml" --include="*.cfg" --include="*.ini" --include="*.js" --include="*.ts" --include="*.html" --include="*.css" "{pattern}" "{path}"'
    result = sandbox_run(cmd, timeout=15)
    if result["returncode"] == 0 and result["stdout"]:
        lines = result["stdout"].strip().split("\n")
        if len(lines) > 50:
            return "\n".join(lines[:50]) + f"\n... ({len(lines) - 50} more matches)"
        return result["stdout"].strip()
    if result["returncode"] == 1:
        return f"No matches found for '{pattern}' in '{path}'."
    return f"Search error: {result['stderr']}"


# --- Dispatch ---

def dispatch(name: str, args_json: str) -> str:
    """Dispatch a tool call by name, parsing the JSON arguments."""
    try:
        args = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError:
        return f"Error: Invalid JSON arguments: {args_json}"

    try:
        return _dispatch(name, args)
    except KeyError as e:
        return f"Error: Missing required argument {e} for tool '{name}'"


def _dispatch(name: str, args: dict) -> str:
    if name == "read_file":
        return read_file(args["path"])
    elif name == "write_file":
        return write_file(args["path"], args["content"])
    elif name == "run_command":
        return _run_command(args["command"], args.get("timeout", 30))
    elif name == "list_directory":
        return list_directory(args.get("path", "."))
    elif name == "search_files":
        return search_files(args["pattern"], args.get("path", "."))
    else:
        return f"Error: Unknown tool '{name}'"
