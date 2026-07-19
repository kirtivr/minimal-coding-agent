"""Subagent architecture for parallel task execution."""

import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Subagent:
    """Represents a running or completed subagent task."""
    id: str
    task: str
    status: str = "pending"
    result: Any = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None


class SubagentManager:
    """Manages spawning and lifecycle of subagents."""

    def __init__(self, task_runner: Optional[Callable[[str], Any]] = None):
        self._subagents: Dict[str, Subagent] = {}
        self._lock = threading.Lock()
        self.task_runner = task_runner

    def spawn(self, task: Callable[[], Any], task_description: str = "") -> str:
        """Spawn a new subagent to execute *task* in a background thread.

        Returns the subagent's unique id.
        """
        subagent_id = str(uuid.uuid4())
        subagent = Subagent(
            id=subagent_id,
            task=task_description or getattr(task, "__name__", repr(task)),
        )

        def _run() -> None:
            with self._lock:
                subagent.status = "running"
            try:
                result = task()
                with self._lock:
                    subagent.result = result
                    subagent.status = "completed"
            except Exception as exc:
                with self._lock:
                    subagent.error = str(exc)
                    subagent.status = "failed"

        thread = threading.Thread(target=_run, daemon=True)
        subagent.thread = thread

        with self._lock:
            self._subagents[subagent_id] = subagent

        thread.start()
        return subagent_id

    def get_status(self, subagent_id: str) -> Optional[str]:
        """Return the status of the subagent, or None if unknown."""
        with self._lock:
            subagent = self._subagents.get(subagent_id)
            return subagent.status if subagent else None

    def wait_for(self, subagent_id: str, timeout: Optional[float] = None) -> bool:
        """Wait for the subagent to finish.

        Returns True if the subagent finished within the timeout, False otherwise.
        """
        with self._lock:
            subagent = self._subagents.get(subagent_id)
        if subagent is None or subagent.thread is None:
            return False
        subagent.thread.join(timeout=timeout)
        return not subagent.thread.is_alive()

    def list_subagents(self) -> List[str]:
        """Return a list of all subagent ids."""
        with self._lock:
            return list(self._subagents.keys())

    def get_result(self, subagent_id: str) -> Dict[str, Any]:
        """Return a dict with the subagent's current status, result, and error."""
        with self._lock:
            subagent = self._subagents.get(subagent_id)
            if subagent is None:
                return {
                    "status": "unknown",
                    "result": None,
                    "error": "Subagent not found",
                }
            return {
                "status": subagent.status,
                "result": subagent.result,
                "error": subagent.error,
            }