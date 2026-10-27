import argparse
import json
from mcp.server.mcpserver import MCPServer
from outils import code_search_tools, execution_tools, file_systeme_tool

mcp = MCPServer("swebench")


# ---- File system tools ----

@mcp.tool()
def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """Read lines start_line to end_line (inclusive) of a file.

    Args:
        filepath: absolute path of the file, e.g. "/testbed/src/module.py".
        start_line: first line to read (starts at 1).
        end_line: last line to read.

    Returns:
        The lines in the format "<line_number>: <line_content>".
    """
    return file_systeme_tool.read_file(filepath, start_line, end_line)


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file with a new string.

    old_str must appear exactly once in the file, otherwise nothing is
    changed and an error is returned.

    Args:
        filepath: absolute path of the file to edit.
        old_str: exact text to replace (whitespace and indentation included).
        new_str: text to put in its place.

    Returns:
        A success message or an error message.
    """
    return file_systeme_tool.edit_file(filepath, old_str, new_str)


@mcp.tool()
def list_files(directory: str, pattern: str) -> str:
    """List files in a directory (recursively) matching a glob pattern.

    Args:
        directory: directory to search in, e.g. "/testbed".
        pattern: glob pattern, e.g. "*.py" or "test_*.py".

    Returns:
        One absolute path per line, or a message if nothing matches.
    """
    return file_systeme_tool.list_files(directory, pattern)


# ---- Code search tools ----

@mcp.tool()
def search_code(pattern: str, file_pattern: str) -> str:
    """Search the repository for lines containing a text (like grep).

    The search is recursive from the repository root (TESTBED_PATH).

    Args:
        pattern: exact text to look for (not a regex).
        file_pattern: glob pattern of the files to search, e.g. "*.py".

    Returns:
        One match per line: "/absolute/path.py:<line_number> <line_content>".
    """
    return code_search_tools.search_code(pattern, file_pattern)


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """Find where a function or a class is defined in the repository.

    Args:
        name: exact name of the function or class, e.g. "add" or "Calc".

    Returns:
        One definition per line: "/absolute/path.py:<line_number> <line_content>".
    """
    return code_search_tools.search_function_or_class_definition_in_code(name)


@mcp.tool()
def find_references(name: str, filepath: str, line: int) -> str:
    """Find all usages of a symbol (function or class) in the repository.

    Args:
        name: name of the symbol, e.g. "add".
        filepath: file where the symbol is defined.
        line: line where the symbol is defined.

    Returns:
        One usage per line: "/absolute/path.py:<line_number> <line_content>".
    """
    return code_search_tools.find_references(name, filepath, line)


# ---- Execution tools ----

@mcp.tool()
def run_tests() -> str:
    """Run the task's evaluation script (eval.sh at the repository root).

    Returns:
        The test part of the evaluation script's output (between its "Start Test Output"
        and "End Test Output" markers). If it is too long, only the last 4000 characters are returned.
    """
    return execution_tools.run_tests()


@mcp.tool()
def get_patch() -> str:
    """Get the unified git diff of every change made to the repository.

    Returns:
        The output of "git -c core.fileMode=false diff", or a message if
        nothing changed.
    """
    return execution_tools.get_patch()


@mcp.tool()
def run_command(command: str, workdir: str | None = None) -> str:
    """Run a shell command (timeout: 120 seconds).

    Args:
        command: the shell command, e.g. "ls" or "python -m pytest tests/".
        workdir: directory to run it in. Defaults to the repository root.

    Returns:
        The exit code, stdout and stderr of the command.
    """
    return execution_tools.run_command(command, workdir)


@mcp.resource("swebench://limits", mime_type="application/json")
def swebench_limits() -> str:
    """Limits the SWE-bench agent must respect (subject, section VI.1.2)."""
    return json.dumps({
        "max_iterations": 30,
        "max_input_tokens": 300000,
        "max_output_tokens": 10000,
        "timeout_seconds": 900,
    })


@mcp.prompt()
def solve_swebench(problem_statement: str, hints_text: str = "") -> str:
    """Prompt asking the LLM to fix one SWE-bench issue.

    Args:
        problem_statement: the GitHub issue to fix.
        hints_text: optional hints about the issue.
    """
    hints = f"\nHints:\n{hints_text}\n" if hints_text else ""
    return (
        f"Fix this GitHub issue in the repository:\n{problem_statement}\n"
        f"{hints}\n"
        "Explore the code with list_files, search_code and read_file, "
        "fix it with edit_file, check it with run_tests, then call "
        "final_answer(get_patch()) to submit the git diff."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP server for SWE-bench tools")
    parser.add_argument("--http", action="store_true",
                        help="use streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.http:
        mcp.run("streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()
