import argparse
import json
import os
import subprocess
import sys
import tempfile
from mcp.server.mcpserver import MCPServer

TIMEOUT = 10

mcp = MCPServer("mbpp")

@mcp.tool()
def run_tests(code: str, test_list: list[str]) -> str:
    """Run a candidate solution against MBPP test assertions.

    Args:
        code: Python source code of the candidate solution.
        test_list: assert statements to run after the code,
            e.g. ["assert add(1, 2) == 3"].

    Returns:
        A JSON string {"success": bool, "output": str}. success is true
        if every assertion passed; output holds the script's output or error.
    """
    code = code + "\n" + "\n".join(test_list)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = subprocess.run([sys.executable, path], capture_output=True,
                                text=True, timeout=TIMEOUT)
        success = result.returncode == 0
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        success = False
        output = f"Timeout: tests took more than {TIMEOUT} seconds"
    finally:
        os.remove(path)
    return json.dumps({"success": success, "output": output})


@mcp.resource("mbpp://limits", mime_type="application/json")
def mbpp_limits() -> str:
    """Limits the MBPP agent must respect (subject, section VI.1.1)."""
    return json.dumps({
        "max_iterations": 10,
        "max_input_tokens": 6000,
        "max_output_tokens": 1500,
        "timeout_seconds": 120,
        "run_tests_timeout_seconds": TIMEOUT,
    })


@mcp.prompt()
def solve_mbpp(task_definition: str, function_definition: str,
               test_list: str) -> str:
    """Prompt asking the LLM to solve one MBPP task.

    Args:
        task_definition: the problem statement.
        function_definition: the signature the solution must use.
        test_list: the assert statements, one per line.
    """
    return (
        f"Solve this Python problem:\n{task_definition}\n\n"
        f"Your function must use this signature:\n{function_definition}\n\n"
        f"It must pass these tests:\n{test_list}\n\n"
        "Check your code with run_tests(code, test_list). When every test "
        "passes, call final_answer(code) with the function code only."
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP server for MBPP tools")
    parser.add_argument("--http", action="store_true",
                        help="use streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.http:
        mcp.run("streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()