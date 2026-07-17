"""Subagent workflow support for the coding agent."""


class SubagentManager:
    """Manages subagents that can execute tasks in parallel."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def run(self, tasks: list) -> list:
        """Run a list of tasks and return results."""
        # Placeholder for parallel subagent execution
        return []