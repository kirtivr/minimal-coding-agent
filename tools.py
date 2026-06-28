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
            "description": "Search for a text pattern in files recursively using cross-platform text scanning.",
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
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "Spawn a subagent to handle a specialized task in parallel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Description of the task to delegate",
                    },
                    "role": {
                        "type": "string",
                        "description": "Role or persona for the subagent (e.g., researcher, monitor)",
                    },
                },
                "required": ["task_description", "role"],
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
    include_extensions = {
        ".py",
        ".txt",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".js",
        ".ts",
        ".html",
        ".css",
    }

    try:
        if not os.path.exists(path):
            return f"Search error: Path '{path}' does not exist."

        files_to_search = []
        if os.path.isfile(path):
            _, ext = os.path.splitext(path)
            if ext.lower() in include_extensions:
                files_to_search.append(path)
        else:
            for root, dirs, files in os.walk(path):
                dirs.sort()
                files.sort()
                for filename in files:
                    _, ext = os.path.splitext(filename)
                    if ext.lower() in include_extensions:
                        files_to_search.append(os.path.join(root, filename))
    except Exception as e:
        return f"Search error: {e}"

    matches = []
    for file_path in files_to_search:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_number, line in enumerate(f, start=1):
                    if pattern in line:
                        display_path = os.path.relpath(file_path, ".").replace(os.sep, "/")
                        matches.append(f"{display_path}:{line_number}:{line.rstrip()}")
        except (OSError, UnicodeError):
            continue

    if not matches:
        return f"No matches found for '{pattern}' in '{path}'."
    if len(matches) > 50:
        return "\n".join(matches[:50]) + f"\n... ({len(matches) - 50} more matches)"
    return "\n".join(matches)


def delegate_task(task_description: str, role: str) -> str:
    """Delegate a task to a subagent and return its result."""
    # Local import avoids circular dependency since agent.py imports from tools.py.
    from agent import Agent, get_config

    api_key, model = get_config()
    subagent = Agent(api_key=api_key, model=model)
    # Prepend a system-style role hint so the subagent knows its persona.
    role_prompt = f"You are acting as a '{role}' subagent. Focus on the following task."
    subagent.messages.append({"role": "user", "content": f"{role_prompt}\n\n{task_description}"})
    result = subagent._agent_turn()
    return result or "No response from subagent."


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
    elif name == "delegate_task":
        return delegate_task(args["task_description"], args["role"])
    else:
        return f"Error: Unknown tool '{name}'"