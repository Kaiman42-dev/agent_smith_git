"""Command line of the sandbox: `uv run sandbox`.

    uv run sandbox                                     # default config
    uv run sandbox sandbox_template.json               # custom config
    uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json
    uv run sandbox --mcp-server http://127.0.0.1:8000/mcp

Opens a REPL: each entry runs in the persistent sandbox (sandbox.py), with the
same restrictions as for the agent, the MCP tools and final_answer.
"""

import argparse
import code
import contextlib
import readline  # noqa: F401  (arrow keys and history in input())
import sys
from pathlib import Path

from pydantic import ValidationError

from .config_sandbox import Conifg_Sandbox
from .sandbox import Sandbox

EXIT_COMMANDS = ("exit", "quit")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="sandbox", description="Interactive Python sandbox with MCP tools.")
    parser.add_argument("config", nargs="?",
                        help="sandbox config JSON file (default config if omitted)")
    server = parser.add_mutually_exclusive_group()
    server.add_argument("--mcp-stdio", metavar="COMMAND",
                        help='start an MCP server with this command, e.g. "python mcp_tools_mbpp.py"')
    server.add_argument("--mcp-server", metavar="URL",
                        help="connect to a streamable HTTP MCP server")
    return parser.parse_args(argv)


def load_config(path: str | None) -> Conifg_Sandbox:
    if path is None:
        return Conifg_Sandbox()
    try:
        return Conifg_Sandbox.model_validate_json(Path(path).read_text())
    except OSError as e:
        sys.exit(f"sandbox: cannot read {path}: {e.strerror}")
    except ValidationError as e:
        sys.exit(f"sandbox: invalid config {path}:\n{e}")


def print_result(result):
    if result.output:
        print(result.output, end="" if result.output.endswith("\n") else "\n")
    if result.error:
        print(result.error.rstrip("\n"), file=sys.stderr)
    if result.final_answer is not None:
        print(f"Final answer: {result.final_answer}")


class SandboxConsole(code.InteractiveConsole):
    """The Python REPL (prompts, blocks, Ctrl+C, Ctrl+D), running each entry in the sandbox."""

    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox

    def runsource(self, source, filename="<stdin>", symbol="single"):
        """Returns True while the block is not finished (the console asks for more)."""
        if source.strip() in EXIT_COMMANDS:
            raise SystemExit
        try:
            if self.compile(source, filename, symbol) is None:
                return True
        except (SyntaxError, ValueError, OverflowError):
            pass  # the sandbox reports the error
        if source.strip():
            try:
                print_result(self.sandbox.execute(source, interactive=True))
            except KeyboardInterrupt:
                print("KeyboardInterrupt: the sandbox was restarted, all variables were lost.",
                      file=sys.stderr)
        return False


def main(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    target = args.mcp_stdio or args.mcp_server

    with contextlib.ExitStack() as stack:
        tools = {}
        if target:
            # Imported here: `mcp` is heavy, and the sandbox child re-imports this module
            from mcp_bridge import build_tools
            from mcp_client import SyncMcpClient
            try:
                tools = build_tools(stack.enter_context(SyncMcpClient(target)))
            except Exception as e:
                sys.exit(f"sandbox: {e}")
        sandbox = stack.enter_context(Sandbox(config, tools))
        banner = (f"Sandbox ready. MCP tools: {', '.join(tools) or 'none'}.\n"
                  "final_answer() is always available. Type exit or press Ctrl+D to quit.")
        with contextlib.suppress(SystemExit):  # exit, or exit() in the code
            SandboxConsole(sandbox).interact(banner=banner, exitmsg="")


if __name__ == "__main__":
    main()
