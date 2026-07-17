"""Subagent architecture for parallel specialized task execution."""

import logging
import threading
import uuid

from api_client import call_openrouter
from prompts import RESEARCH_PROMPT, MONITORING_PROMPT, INTERACTING_PROMPT
from tools import TOOL_SCHEMAS, dispatch

LOGGER = logging.getLogger("coding_agent")

AGENT_TYPE_PROMPTS = {
    "research": RESEARCH_PROMPT,
    "monitoring": MONITORING_PROMPT,
    "interacting": INTERACTING_PROMPT,
}


class Subagent:
    """A background subagent that executes a specialized task in a thread."""

    def __init__(self, agent_id, agent_type, task, api_key, model):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.task = task
        self.api_key = api_key
        self.model = model
        self.status = "idle"
        self.result = None
        self.error = None
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        """Start the subagent in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            LOGGER.warning("Subagent %s is already running.", self.agent_id)
            return
        self.status = "running"
        self.result = None
        self.error = None
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        LOGGER.info("Subagent %s (%s) started.", self.agent_id, self.agent_type)

    def _run(self):
        """Main execution loop for the subagent."""
        try:
            system_prompt = AGENT_TYPE_PROMPTS.get(self.agent_type, RESEARCH_PROMPT)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self.task},
            ]

            max_turns = 10
            for _ in range(max_turns):
                if self._stop_event.is_set():
                    self.status = "stopped"
                    LOGGER.info("Subagent %s stopped by request.", self.agent_id)
                    return

                try:
                    data = call_openrouter(messages, TOOL_SCHEMAS, self.api_key, self.model)
                except Exception as e:
                    self.error = str(e)
                    self.status = "failed"
                    LOGGER.exception("Subagent %s API call failed", self.agent_id)
                    return

                choice = data["choices"][0]
                msg = choice["message"]
                messages.append(msg)

                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    LOGGER.info(
                        "Subagent %s processing %d tool call(s).",
                        self.agent_id,
                        len(tool_calls),
                    )
                    for tc in tool_calls:
                        if self._stop_event.is_set():
                            self.status = "stopped"
                            return
                        name = tc["function"]["name"]
                        args = tc["function"].get("arguments", "{}")
                        LOGGER.info(
                            "Subagent %s | %s(%s%s)",
                            self.agent_id,
                            name,
                            args[:80],
                            "..." if len(args) > 80 else "",
                        )
                        output = dispatch(name, args)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": output,
                        })
                    continue

                if msg.get("content"):
                    self.result = msg["content"]
                    self.status = "completed"
                    LOGGER.info("Subagent %s completed.", self.agent_id)
                else:
                    self.result = ""
                    self.status = "completed"
                return

            self.status = "completed"
            self.result = "Task reached maximum turn limit without final content."
            LOGGER.warning("Subagent %s hit max turn limit.", self.agent_id)

        except Exception as e:
            self.error = str(e)
            self.status = "failed"
            LOGGER.exception("Subagent %s encountered an error", self.agent_id)

    def stop(self):
        """Signal the subagent to stop."""
        self._stop_event.set()
        LOGGER.info("Subagent %s stop requested.", self.agent_id)

    def join(self, timeout=None):
        """Wait for the subagent thread to finish."""
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)

    def is_alive(self):
        """Return whether the subagent thread is still running."""
        return self._thread is not None and self._thread.is_alive()

    def to_dict(self):
        """Return a dictionary representation of the subagent state."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "task": self.task,
            "status": self.status,
            "result": self.result,
            "error": self.error,
        }


class SubagentManager:
    """Singleton manager for spawning and tracking subagents."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, api_key=None, model=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._subagents = {}
                    cls._instance._counter = 0
                    cls._instance._spawn_lock = threading.Lock()
                    cls._instance._api_key = api_key
                    cls._instance._model = model
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance. Useful for testing."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.shutdown()
            cls._instance = None

    def spawn(self, agent_type, task, api_key=None, model=None):
        """Spawn a new subagent and start it. Returns the subagent ID."""
        if agent_type not in AGENT_TYPE_PROMPTS:
            raise ValueError(
                f"Unknown agent type: {agent_type}. "
                f"Must be one of {list(AGENT_TYPE_PROMPTS.keys())}"
            )

        if api_key is None:
            api_key = self._api_key
        if model is None:
            model = self._model
        if not api_key or not model:
            raise ValueError("api_key and model are required to spawn a subagent")

        with self._spawn_lock:
            self._counter += 1
            agent_id = f"{agent_type}-{self._counter}-{uuid.uuid4().hex[:6]}"
            subagent = Subagent(agent_id, agent_type, task, api_key, model)
            self._subagents[agent_id] = subagent
        subagent.start()
        LOGGER.info("Spawned subagent %s.", agent_id)
        return agent_id

    def get(self, agent_id):
        """Get a subagent by its ID."""
        with self._spawn_lock:
            return self._subagents.get(agent_id)

    def list_all(self):
        """List all subagents with their current state."""
        with self._spawn_lock:
            return [s.to_dict() for s in self._subagents.values()]

    def shutdown(self, timeout=None):
        """Stop all subagents and wait for them to finish."""
        with self._spawn_lock:
            subagents = list(self._subagents.values())
        LOGGER.info("Shutting down %d subagent(s).", len(subagents))
        for subagent in subagents:
            subagent.stop()
        for subagent in subagents:
            subagent.join(timeout)
        with self._spawn_lock:
            self._subagents.clear()
        LOGGER.info("All subagents shut down.")