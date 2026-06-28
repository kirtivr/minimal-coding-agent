"""Tests for agent.py"""

import pytest
from agent import process_tool_calls


def test_process_tool_calls_malformed_payload():
    """process_tool_calls should not raise when payload keys are missing."""
    malformed_payloads = [
        {},
        {"id": "tc_1"},
        {"type": "function"},
        {"function": {}},
        {"function": {"name": "foo"}},
        {"function": {"arguments": "{}"}},
        {"id": "tc_1", "function": {"arguments": "{}"}},
    ]
    for payload in malformed_payloads:
        # Should not raise any exception (especially KeyError)
        result = process_tool_calls([payload])
        assert result == []