# Minimal Coding Agent

A coding agent in under 400 lines of Python. It connects to any LLM through [OpenRouter](https://openrouter.ai/) and can read, write, search, and execute code autonomously.

## How it works

```
You ↔ agent.py (main agent + orchestrator) ↔ OpenRouter API ↔ Any LLM
                      │
                      ├─ standard tools via tools.py
                      │        ↓
                      │   sandbox.py (subprocess with timeout)
                      │
                      └─ subagent workflows (parallel)
                           ├─ research worker
                           ├─ monitoring worker
                           └─ interaction worker
```

The main agent now acts as an orchestrator: it plans work, delegates independent tasks to subagents in parallel, polls for progress/results, then synthesizes outputs into a final response.

### Tools

#### Standard tools (backward compatible)

| Tool | What it does |
|------|-------------|
| `read_file` | Read a file's contents |
| `write_file` | Create or overwrite a file |
| `run_command` | Execute a shell command (with timeout) |
| `list_directory` | List files and folders |
| `search_files` | Search for text patterns across files |

#### Subagent coordination tools

| Tool | What it does | Typical response |
|------|---------------|------------------|
| `start_subagent` | Start a worker with a role (`research`, `monitoring`, `interaction`) and task payload | `{"subagent_id": "...", "status": "queued|running"}` |
| `get_subagent_status` | Poll current status and optional progress metadata | `{"subagent_id": "...", "status": "running", "progress": ...}` |
| `collect_subagent_result` | Retrieve final output, logs, and/or error details when complete | `{"subagent_id": "...", "status": "completed|failed", "result": ...}` |
| `cancel_subagent` | Stop an in-flight worker when no longer needed | `{"subagent_id": "...", "status": "cancelled"}` |

### Workflow pattern

1. Main agent decomposes a request into independent subtasks.
2. Main agent starts one or more subagents concurrently.
3. Main agent periodically polls status while continuing other orchestration work.
4. Main agent collects completed outputs and merges them into a single user-facing answer.

### Operational notes

- Parallel execution is best for independent tasks; tightly coupled steps should stay sequential.
- Prefer status polling (`get_subagent_status`) for long-running jobs and only collect (`collect_subagent_result`) when a worker is terminal (`completed`, `failed`, or `cancelled`).
- If subagent orchestration is unavailable or unnecessary, the agent should fall back to the standard single-agent tool loop, preserving existing behavior.
- Errors from a single subagent should be isolated and surfaced with context; they should not automatically discard successful results from other workers.

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env   # then add your OpenRouter API key
```

## Usage

```bash
python agent.py
```

```
Coding Agent (model: minimax/minimax-m2.5)
Type /quit to exit, Ctrl+C to interrupt.

You: Create a fizzbuzz.py that takes a number from the command line, then run it with 20
  🔧 write_file({"path": "fizzbuzz.py", "content": "..."})
  🔧 run_command({"command": "python fizzbuzz.py 20"})

Agent: Done! Here's the output:
1, 2, Fizz, 4, Buzz, Fizz, 7, 8, Fizz, Buzz, 11, Fizz, 13, 14, FizzBuzz, ...
```

## Tests

```bash
python -m pytest tests/ -v
```

43 tests across two suites — no API key needed:
- **test_easy.py** (17 tests) — happy-path validation for every tool
- **test_medium.py** (26 tests) — edge cases, error handling, multi-tool workflows

## Files

```
agent.py      — Chat loop + OpenRouter API calls (147 lines)
tools.py      — Tool schemas, implementations, dispatch (196 lines)
sandbox.py    — Subprocess wrapper with timeout (44 lines)
prompts.py    — System prompt (20 lines)
```

## Configuration

Set these in your `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | *(required)* | Your [OpenRouter API key](https://openrouter.ai/keys) |
| `OPENROUTER_MODEL` | `minimax/minimax-m2.5` | Any model on OpenRouter |