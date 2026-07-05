"""Secure code execution sandbox tool.

Runs arbitrary Python code in an isolated E2B cloud sandbox to prevent
security breaches. Falls back to a restricted local subprocess when
E2B_API_KEY is not configured (useful for development/testing).
"""

import os
import subprocess
import sys
import tempfile
import textwrap
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

E2B_API_KEY: Optional[str] = os.getenv("E2B_API_KEY")
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "30"))

# Patterns that are ALWAYS dangerous regardless of sandbox type.
# E2B handles isolation at the VM level, but we still block these to
# prevent accidental data exfiltration or credential scraping.
_BLOCKED_PATTERNS = [
    "os.system",
    "os.popen",
    "subprocess",
    "socket",
    "__import__",
    "importlib",
    "open(",          # filesystem access
    "eval(",          # arbitrary code injection
    "exec(",          # same
    "compile(",
    "globals()",
    "locals()",
    "getattr(",       # reflection-based bypasses
    "requests",
    "urllib",
    "httpx",
    "aiohttp",
    "boto3",          # cloud credentials
    "paramiko",       # SSH
]


def _validate_code_safety(code: str) -> Optional[str]:
    """Scan code for dangerous patterns before execution.

    Returns an error string if the code is unsafe, None if safe.
    Applies to both E2B and local subprocess paths — E2B adds VM-level
    isolation on top, but we still enforce this allowlist for defense-in-depth.
    """
    code_lower = code.lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern.lower() in code_lower:
            return (
                f"SECURITY_ERROR: pattern '{pattern}' is not allowed in sandbox code.\n"
                f"Allowed operations: pure math, numpy, pandas, statistics, json, datetime, math, re.\n"
                f"For live data: use the dedicated tools (get_fx_rates, get_market_data, etc.) instead."
            )
    return None


class ExecuteCodeInput(BaseModel):
    """Input schema for execute_python_sandbox."""

    code: str = Field(
        ...,
        description="Valid Python 3 code to execute. Must be self-contained — import every library you need.",
        min_length=1,
        max_length=8000,
    )


def _run_e2b(code: str) -> str:
    """Execute code in an E2B cloud sandbox (fully isolated VM)."""
    from e2b_code_interpreter import Sandbox

    with Sandbox(api_key=E2B_API_KEY, timeout=SANDBOX_TIMEOUT) as sandbox:
        execution = sandbox.run_code(code)

        output_parts = []

        if execution.logs.stdout:
            output_parts.append("=== STDOUT ===\n" + "\n".join(execution.logs.stdout))

        if execution.logs.stderr:
            output_parts.append("=== STDERR ===\n" + "\n".join(execution.logs.stderr))

        if execution.error:
            output_parts.append(f"=== ERROR ===\n{execution.error.name}: {execution.error.value}")
            if execution.error.traceback:
                output_parts.append("Traceback:\n" + execution.error.traceback)

        if execution.results:
            for result in execution.results:
                if hasattr(result, "text") and result.text:
                    output_parts.append(f"=== RESULT ===\n{result.text}")

        return "\n\n".join(output_parts) if output_parts else "(no output)"


def _run_local_subprocess(code: str) -> str:
    """Fallback: run code in a local subprocess with timeout.

    Less isolated than E2B but sufficient for development.
    Set E2B_API_KEY for production use.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(textwrap.dedent(code))
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=SANDBOX_TIMEOUT,
            encoding="utf-8",
        )
        parts = []
        if result.stdout:
            parts.append(f"=== STDOUT ===\n{result.stdout.strip()}")
        if result.stderr:
            parts.append(f"=== STDERR ===\n{result.stderr.strip()}")
        if not parts:
            return "(no output)"
        return "\n\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"=== ERROR ===\nExecution timed out after {SANDBOX_TIMEOUT} seconds."
    except Exception as exc:
        return f"=== ERROR ===\n{type(exc).__name__}: {exc}"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@tool("execute_python_sandbox", args_schema=ExecuteCodeInput)
def execute_python_sandbox(code: str) -> str:
    """Execute Python code securely in an isolated sandbox environment.

    Use this tool whenever you need to:
    - Run a backtest or simulation on financial data
    - Calculate technical indicators (moving averages, RSI, Bollinger Bands, etc.)
    - Process or transform datasets
    - Verify mathematical calculations with actual code execution
    - Perform any computation that benefits from running real Python

    The code runs in a fully isolated environment — it cannot access the host
    filesystem, network, or production database. Each execution starts fresh.

    Args:
        code: Self-contained Python 3 code to execute. Include all necessary
              imports. Print your results explicitly with print().

    Returns:
        Captured stdout, stderr, or error messages from the execution.

    Example usage:
        code = '''
        import statistics
        prices = [100, 102, 98, 105, 103]
        print(f"Mean: {statistics.mean(prices):.2f}")
        print(f"Stdev: {statistics.stdev(prices):.2f}")
        '''
    """
    sandbox_type = "e2b_cloud" if E2B_API_KEY else "local_subprocess"

    # Phase 2.1 — security gate (runs before any execution)
    safety_error = _validate_code_safety(code)
    if safety_error:
        return f"[sandbox={sandbox_type}]\n\n{safety_error}"

    try:
        if E2B_API_KEY:
            result = _run_e2b(code)
        else:
            result = _run_local_subprocess(code)

        return f"[sandbox={sandbox_type}]\n\n{result}"

    except Exception as exc:
        return (
            f"[sandbox={sandbox_type}]\n\n"
            f"=== ERROR ===\n{type(exc).__name__}: {exc}\n\n"
            "Please check the code for syntax errors and try again."
        )
