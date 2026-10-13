import argparse
from mcp.server.mcpserver import MCPServer
from outils import file_systeme_tool

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
