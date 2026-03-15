# Minimal Coding Agent

A coding agent in under 400 lines of Python. It connects to any LLM through [OpenRouter](https://openrouter.ai/) and can read, write, search, and execute code autonomously.

## How it works

```
You ↔ agent.py (chat loop) ↔ OpenRouter API ↔ Any LLM
              ↓
      tools.py (5 tools + dispatch)
              ↓
      sandbox.py (subprocess with timeout)
```

The agent runs a simple loop: send your message to the LLM, execute any tool calls it requests, feed results back, repeat until it responds with text.

### Tools

| Tool | What it does |
|------|-------------|
| `read_file` | Read a file's contents |
| `write_file` | Create or overwrite a file |
| `run_command` | Execute a shell command (with timeout) |
| `list_directory` | List files and folders |
| `search_files` | Search for text patterns across files |

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
