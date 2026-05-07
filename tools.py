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
            "name": "subagent_create_task",
            "description": "Create a subagent task for a specific role.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "enum": ["research", "monitoring", "interaction"],
                        "description": "Subagent role assigned to the task",
                    },
                    "task": {
                        "type": "string",
                        "description": "Task instructions for the subagent",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional structured metadata for orchestration context",
                    },
                },
                "required": ["role", "task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subagent_start_task",
            "description": "Start a previously created subagent task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Unique task identifier returned by subagent_create_task",
                    }
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subagent_task_status",
            "description": "Get status for a specific subagent task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task identifier to inspect",
                    }
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subagent_list_tasks",
            "description": "List subagent tasks, optionally filtered by role and/or status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "enum": ["research", "monitoring", "interaction"],
                        "description": "Optional role filter",
                    },
                    "status": {
                        "type": "string",
                        "description": "Optional status filter (created|running|completed|failed|cancelled)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subagent_cancel_task",
            "description": "Cancel a subagent task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task identifier to cancel",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional cancellation reason",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subagent_collect_output",
            "description": "Collect output for a subagent task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task identifier to collect output from",
                    },
                    "clear": {
                        "type": "boolean",
                        "description": "Whether to clear stored output after collection (default: false)",
                    },
                },
                "required": ["task_id"],
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


_VALID_SUBAGENT_ROLES = {"research", "monitoring", "interaction"}
_ORCHESTRATION_HANDLERS = {}
_ORCHESTRATION_STATE = {"next_id": 1, "tasks": {}}


def register_orchestration_handlers(handlers: dict) -> str:
    """Register optional orchestrator callbacks from agent.py."""
    global _ORCHESTRATION_HANDLERS
    _ORCHESTRATION_HANDLERS = handlers or {}
    return "Registered orchestration handlers"


def _json_success(payload: dict) -> str:
    response = {"ok": True}
    response.update(payload)
    return json.dumps(response)


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "error": message})


def _validate_role(role: str) -> str:
    if role not in _VALID_SUBAGENT_ROLES:
        raise ValueError(
            f"Invalid role '{role}'. Expected one of {sorted(_VALID_SUBAGENT_ROLES)}"
        )
    return role


def _validate_task_id(task_id: str) -> str:
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")
    return task_id


def _call_orchestrator_handler(action: str, fallback, **kwargs) -> str:
    handler = _ORCHESTRATION_HANDLERS.get(action)
    if handler is not None:
        try:
            result = handler(**kwargs)
            if isinstance(result, str):
                return result
            if isinstance(result, dict):
                return json.dumps(result)
            return _json_error(f"Orchestrator handler '{action}' returned unsupported result")
        except Exception as e:
            return _json_error(f"Orchestrator handler '{action}' failed: {e}")
    return fallback(**kwargs)


def _subagent_create_task(role: str, task: str, metadata: dict | None = None) -> str:
    _validate_role(role)
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")

    task_id = f"task-{_ORCHESTRATION_STATE['next_id']}"
    _ORCHESTRATION_STATE["next_id"] += 1
    task_record = {
        "task_id": task_id,
        "role": role,
        "task": task,
        "metadata": metadata or {},
        "status": "created",
        "output": None,
        "error": None,
    }
    _ORCHESTRATION_STATE["tasks"][task_id] = task_record
    return _json_success({"task": task_record})


def _subagent_start_task(task_id: str) -> str:
    task_id = _validate_task_id(task_id)
    task_record = _ORCHESTRATION_STATE["tasks"].get(task_id)
    if task_record is None:
        return _json_error(f"Unknown task_id '{task_id}'")
    if task_record["status"] in {"completed", "failed", "cancelled"}:
        return _json_error(
            f"Cannot start task '{task_id}' from terminal status '{task_record['status']}'"
        )
    task_record["status"] = "running"
    return _json_success({"task": task_record})


def _subagent_task_status(task_id: str) -> str:
    task_id = _validate_task_id(task_id)
    task_record = _ORCHESTRATION_STATE["tasks"].get(task_id)
    if task_record is None:
        return _json_error(f"Unknown task_id '{task_id}'")
    return _json_success({"task": task_record})


def _subagent_list_tasks(role: str | None = None, status: str | None = None) -> str:
    if role is not None:
        _validate_role(role)

    tasks = list(_ORCHESTRATION_STATE["tasks"].values())
    if role is not None:
        tasks = [task for task in tasks if task["role"] == role]
    if status is not None:
        tasks = [task for task in tasks if task["status"] == status]

    return _json_success({"tasks": tasks, "count": len(tasks)})


def _subagent_cancel_task(task_id: str, reason: str | None = None) -> str:
    task_id = _validate_task_id(task_id)
    task_record = _ORCHESTRATION_STATE["tasks"].get(task_id)
    if task_record is None:
        return _json_error(f"Unknown task_id '{task_id}'")
    if task_record["status"] in {"completed", "failed", "cancelled"}:
        return _json_error(
            f"Cannot cancel task '{task_id}' from terminal status '{task_record['status']}'"
        )
    task_record["status"] = "cancelled"
    if reason:
        task_record["error"] = reason
    return _json_success({"task": task_record})


def _subagent_collect_output(task_id: str, clear: bool = False) -> str:
    task_id = _validate_task_id(task_id)
    task_record = _ORCHESTRATION_STATE["tasks"].get(task_id)
    if task_record is None:
        return _json_error(f"Unknown task_id '{task_id}'")

    output = task_record.get("output")
    response = {
        "task_id": task_id,
        "status": task_record.get("status"),
        "output": output,
        "error": task_record.get("error"),
    }

    if clear:
        task_record["output"] = None

    return _json_success(response)


# --- Dispatch ---

def dispatch(name: str, args_json: str) -> str:
    """Dispatch a tool call by name, parsing the JSON arguments."""
    try:
        args = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError:
        return f"Error: Invalid JSON arguments: {args_json}"

    if not isinstance(args, dict):
        return f"Error: Tool arguments must be a JSON object for tool '{name}'"

    try:
        return _dispatch(name, args)
    except KeyError as e:
        return f"Error: Missing required argument {e} for tool '{name}'"
    except ValueError as e:
        return f"Error: {e}"


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
    elif name == "subagent_create_task":
        return _call_orchestrator_handler(
            "create_task",
            _subagent_create_task,
            role=args["role"],
            task=args["task"],
            metadata=args.get("metadata"),
        )
    elif name == "subagent_start_task":
        return _call_orchestrator_handler(
            "start_task",
            _subagent_start_task,
            task_id=args["task_id"],
        )
    elif name == "subagent_task_status":
        return _call_orchestrator_handler(
            "task_status",
            _subagent_task_status,
            task_id=args["task_id"],
        )
    elif name == "subagent_list_tasks":
        return _call_orchestrator_handler(
            "list_tasks",
            _subagent_list_tasks,
            role=args.get("role"),
            status=args.get("status"),
        )
    elif name == "subagent_cancel_task":
        return _call_orchestrator_handler(
            "cancel_task",
            _subagent_cancel_task,
            task_id=args["task_id"],
            reason=args.get("reason"),
        )
    elif name == "subagent_collect_output":
        return _call_orchestrator_handler(
            "collect_output",
            _subagent_collect_output,
            task_id=args["task_id"],
            clear=args.get("clear", False),
        )
    else:
        return f"Error: Unknown tool '{name}'"