"""Minimal coding agent using OpenRouter API."""

import os
import sys
import json
import time
import requests

from prompts import SYSTEM_PROMPT
from tools import TOOL_SCHEMAS, dispatch


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


def get_config():
    """Load configuration from .env file and environment variables."""
    load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set.")
        print("Create a .env file with:  OPENROUTER_API_KEY=your_key")
        print("Get a key at https://openrouter.ai/keys")
        sys.exit(1)
    model = os.environ.get("OPENROUTER_MODEL", "minimax/minimax-m2.5")
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
            print(f"  Server error ({response.status_code}), retrying...")
            time.sleep(2 ** attempt)
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


def process_tool_calls(tool_calls: list) -> list:
    """Execute tool calls and return tool result messages."""
    results = []
    for tc in tool_calls:
        name = tc["function"]["name"]
        args = tc["function"].get("arguments", "{}")
        print(f"  🔧 {name}({args[:80]}{'...' if len(args) > 80 else ''})")
        output = dispatch(name, args)
        results.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": output,
        })
    return results


def agent_loop():
    """Main agent loop: read input, call API, handle tool calls, repeat."""
    api_key, model = get_config()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"Coding Agent (model: {model})")
    print("Type /quit to exit, Ctrl+C to interrupt.\n")

    while True:
        # Get user input
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Goodbye!")
            break

        messages.append({"role": "user", "content": user_input})

        # Agent turn: may loop if there are tool calls
        while True:
            try:
                data = call_openrouter(messages, TOOL_SCHEMAS, api_key, model)
            except Exception as e:
                print(f"\nError: {e}")
                break

            choice = data["choices"][0]
            msg = choice["message"]

            # Add assistant message to history
            messages.append(msg)

            # Check for tool calls
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                tool_results = process_tool_calls(tool_calls)
                messages.extend(tool_results)
                continue  # Loop back for the model's next response

            # Text response — print and break to get next user input
            if msg.get("content"):
                print(f"\nAgent: {msg['content']}\n")
            break


if __name__ == "__main__":
    agent_loop()
