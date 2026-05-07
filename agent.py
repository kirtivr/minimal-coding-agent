"""Minimal coding agent using OpenRouter API."""

import os
import sys
import json
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import requests

from prompts import SYSTEM_PROMPT
from tools import TOOL_SCHEMAS, dispatch


LOGGER = logging.getLogger("coding_agent")


def load_dotenv():
    """Load variables from .env file if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            os.environ.setdefault(key, value)


def setup_logging(log_file: str, log_level: str = "INFO", console_enabled: bool = True) -> logging.Logger:
    """Configure centralized logging with file persistence and optional console output."""
    logger = LOGGER
    level = getattr(logging, (log_level or "INFO").upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    # Prevent duplicate handlers if setup is called multiple times.
    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console_enabled:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


def get_config():
    """Load configuration from .env file and environment variables."""
    load_dotenv()

    log_file = os.environ.get("AGENT_LOG_FILE", "agent.log")
    log_level = os.environ.get("AGENT_LOG_LEVEL", "INFO")
    console_setting = os.environ.get("AGENT_LOG_CONSOLE", "true").strip().lower()
    console_enabled = console_setting in ("1", "true", "yes", "on")
    setup_logging(log_file=log_file, log_level=log_level, console_enabled=console_enabled)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        LOGGER.error("OPENROUTER_API_KEY not set.")
        print("Error: OPENROUTER_API_KEY not set.")
        print("Create a .env file with:  OPENROUTER_API_KEY=your_key")
        print("Get a key at https://openrouter.ai/keys")
        sys.exit(1)
    model = os.environ.get("OPENROUTER_MODEL", "minimax/minimax-m2.5")
    LOGGER.info("Configuration loaded. Model: %s", model)
    return api_key, model


def call_openrouter(messages: list, tools: list, api_key: str, model: str) -> dict:
    """Call the OpenRouter chat completions API with retry on 5xx errors."""
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(3):
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        if response.status_code >= 500 and attempt < 2:
            backoff_seconds = 2 ** attempt
            LOGGER.warning(
                "Server error (%s), retrying attempt %s/3 in %ss",
                response.status_code,
                attempt + 1,
                backoff_seconds,
            )
            time.sleep(backoff_seconds)
            continue
        break

    if response.status_code != 200:
        raise Exception(
            f"API error {response.status_code}: {response.text[:500]}"
        )
    data = response.json()
    if "error" in data:
        raise Exception(f"API error: {data['error']}")
    return data


class SubagentTaskState(str, Enum):
    """Lifecycle states for managed subagent tasks."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubagentTask:
    """Tracks a single subagent-backed tool call."""

    task_id: str
    tool_call_id: str
    name: str
    args: str
    role: str = "worker"
    state: SubagentTaskState = SubagentTaskState.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None
    future: Optional[object] = None
    emitted: bool = False


class SubagentOrchestrator:
    """Schedules and tracks concurrent subagent workflows."""

    def __init__(self, max_workers: int = 4, poll_interval: float = 0.2):
        self.poll_interval = poll_interval
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks = {}
        self.task_order = []

    def parse_args(self, args: str) -> dict:
        """Best-effort JSON argument parsing for routing metadata."""
        if not isinstance(args, str):
            return args if isinstance(args, dict) else {}
        try:
            payload = json.loads(args)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    def should_schedule_subagent(self, name: str, args: str) -> bool:
        """Determine whether a tool call should be executed as a subagent workflow."""
        payload = self.parse_args(args)
        return (
            name.startswith("subagent_")
            or payload.get("subagent") is True
            or payload.get("workflow") == "subagent"
            or "subagent_role" in payload
        )

    def create_task(self, tool_call: dict) -> SubagentTask:
        """Create subagent task record from a tool call."""
        name = tool_call["function"]["name"]
        args = tool_call["function"].get("arguments", "{}")
        payload = self.parse_args(args)
        role = str(payload.get("subagent_role") or payload.get("role") or "worker")
        task = SubagentTask(
            task_id=f"subagent-{tool_call['id']}",
            tool_call_id=tool_call["id"],
            name=name,
            args=args,
            role=role,
        )
        self.tasks[task.task_id] = task
        self.task_order.append(task.task_id)
        LOGGER.info("Created subagent task %s (role=%s, tool=%s)", task.task_id, task.role, task.name)
        return task

    def start_task(self, task: SubagentTask):
        """Start task asynchronously."""
        task.state = SubagentTaskState.RUNNING
        task.started_at = time.time()
        task.future = self.executor.submit(dispatch, task.name, task.args)
        LOGGER.info("Scheduled subagent task %s", task.task_id)

    def schedule_tool_call(self, tool_call: dict) -> SubagentTask:
        """Create and start a subagent task for a tool call."""
        task = self.create_task(tool_call)
        self.start_task(task)
        return task

    def _refresh_task(self, task: SubagentTask):
        """Update task state from its future if complete."""
        if task.state != SubagentTaskState.RUNNING or task.future is None or not task.future.done():
            return

        try:
            task.result = task.future.result()
            task.state = SubagentTaskState.COMPLETED
            LOGGER.info("Subagent task %s completed", task.task_id)
        except Exception as exc:
            task.error = str(exc)
            task.state = SubagentTaskState.FAILED
            LOGGER.exception("Subagent task %s failed", task.task_id)
        finally:
            task.completed_at = time.time()

    def has_pending_tasks(self) -> bool:
        """True if any task is pending or running."""
        for task in self.tasks.values():
            if task.state in (SubagentTaskState.PENDING, SubagentTaskState.RUNNING):
                return True
        return False

    def pending_count(self) -> int:
        """Return number of pending/running tasks."""
        count = 0
        for task in self.tasks.values():
            if task.state in (SubagentTaskState.PENDING, SubagentTaskState.RUNNING):
                count += 1
        return count

    def collect_finished_messages(self) -> list:
        """Collect newly finished subagent tasks as tool messages in creation order."""
        messages = []
        for task_id in self.task_order:
            task = self.tasks[task_id]
            self._refresh_task(task)
            if task.emitted:
                continue
            if task.state not in (
                SubagentTaskState.COMPLETED,
                SubagentTaskState.FAILED,
                SubagentTaskState.CANCELLED,
            ):
                continue

            payload = {
                "status": task.state.value,
                "subagent": {
                    "task_id": task.task_id,
                    "role": task.role,
                    "tool_name": task.name,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                },
                "output": task.result,
                "error": task.error,
            }
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": task.tool_call_id,
                    "content": json.dumps(payload),
                }
            )
            task.emitted = True

        if messages:
            LOGGER.info("Aggregated %d completed subagent result(s).", len(messages))
        return messages

    def cancel_all(self):
        """Cancel all non-terminal tasks."""
        for task in self.tasks.values():
            if task.state not in (SubagentTaskState.PENDING, SubagentTaskState.RUNNING):
                continue
            if task.future and not task.future.done():
                task.future.cancel()
            task.state = SubagentTaskState.CANCELLED
            task.completed_at = time.time()
            LOGGER.warning("Cancelled subagent task %s", task.task_id)

    def shutdown(self):
        """Stop orchestration resources."""
        self.cancel_all()
        self.executor.shutdown(wait=False, cancel_futures=True)


def process_tool_calls(tool_calls: list, orchestrator: SubagentOrchestrator) -> tuple[list, bool]:
    """Execute tool calls via sync dispatch or subagent orchestration."""
    results = []
    for tc in tool_calls:
        name = tc["function"]["name"]
        args = tc["function"].get("arguments", "{}")
        LOGGER.info("🔧 %s(%s%s)", name, args[:80], "..." if len(args) > 80 else "")

        if orchestrator.should_schedule_subagent(name, args):
            orchestrator.schedule_tool_call(tc)
            continue

        try:
            output = dispatch(name, args)
            payload = {
                "status": "completed",
                "tool": {"name": name, "mode": "synchronous"},
                "output": output,
                "error": None,
            }
        except Exception as exc:
            LOGGER.exception("Tool call failed: %s", name)
            payload = {
                "status": "failed",
                "tool": {"name": name, "mode": "synchronous"},
                "output": None,
                "error": str(exc),
            }

        results.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(payload),
            }
        )

    results.extend(orchestrator.collect_finished_messages())
    has_pending = orchestrator.has_pending_tasks()
    if has_pending:
        LOGGER.info("Subagent tasks still running (%d pending).", orchestrator.pending_count())
    return results, has_pending


def agent_loop():
    """Main agent loop with subagent orchestration-aware tool handling."""
    api_key, model = get_config()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    max_workers = int(os.environ.get("AGENT_SUBAGENT_MAX_WORKERS", "4"))
    poll_interval = float(os.environ.get("AGENT_SUBAGENT_POLL_INTERVAL", "0.2"))
    orchestrator = SubagentOrchestrator(max_workers=max_workers, poll_interval=poll_interval)

    LOGGER.info("Coding Agent started (model: %s)", model)
    LOGGER.info("Subagent orchestrator initialized (max_workers=%d, poll_interval=%.2fs)", max_workers, poll_interval)
    print(f"Coding Agent (model: {model})")
    print("Type /quit to exit, Ctrl+C to interrupt.\n")

    try:
        while True:
            # Get user input
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                LOGGER.info("Session interrupted by user.")
                print("\nGoodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                LOGGER.info("Session ended by user command.")
                print("Goodbye!")
                break

            messages.append({"role": "user", "content": user_input})

            # Agent turn: may loop if there are tool calls or pending subagent work
            while True:
                if orchestrator.has_pending_tasks():
                    completed_messages = orchestrator.collect_finished_messages()
                    if completed_messages:
                        messages.extend(completed_messages)
                    if orchestrator.has_pending_tasks():
                        LOGGER.info("Waiting on %d subagent task(s)...", orchestrator.pending_count())
                        time.sleep(orchestrator.poll_interval)
                        continue

                try:
                    data = call_openrouter(messages, TOOL_SCHEMAS, api_key, model)
                except Exception as e:
                    LOGGER.exception("OpenRouter call failed")
                    print(f"\nError: {e}")
                    break

                choice = data["choices"][0]
                msg = choice["message"]

                # Add assistant message to history
                messages.append(msg)

                # Check for tool calls
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    LOGGER.info("Processing %d tool call(s).", len(tool_calls))
                    tool_results, has_pending = process_tool_calls(tool_calls, orchestrator)
                    if tool_results:
                        messages.extend(tool_results)
                    if has_pending:
                        LOGGER.info("Subagent workflow in progress; continuing orchestration polling.")
                    continue  # Continue until all tool outputs are available

                # Text response — print and break to get next user input
                if msg.get("content"):
                    LOGGER.info("Agent response sent to user.")
                    print(f"\nAgent: {msg['content']}\n")
                break
    finally:
        orchestrator.shutdown()


if __name__ == "__main__":
    agent_loop()