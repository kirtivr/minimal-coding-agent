"""LLM calling logic for OpenRouter API."""

import time
import logging
import requests


LOGGER = logging.getLogger("coding_agent")


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