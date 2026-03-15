"""Subprocess sandbox for running shell commands with timeout."""

import subprocess
import os


def run_command(command: str, timeout: int = 30) -> dict:
    """Run a shell command in a subprocess with a timeout.

    Args:
        command: The shell command to execute.
        timeout: Maximum execution time in seconds (default 30).

    Returns:
        dict with stdout, stderr, and returncode.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
            encoding="utf-8",
            errors="replace",
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
        }
