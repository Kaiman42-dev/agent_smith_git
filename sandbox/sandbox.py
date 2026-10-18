"""Persistent sandbox: runs the LLM's code in an isolated child process.

This file is the PARENT side: it starts the child process (child.py), sends it
code through a Pipe and waits for the result. The child stays alive for the
whole task, so variables persist between steps without replaying history.

While the code runs, the child may ask the parent to call an MCP tool
(see protocol.py): the parent runs the real tool here, outside the sandbox.

Usage:
    tools = build_tools(mcp_client)          # {name: function}, see mcp_bridge.py
    with Sandbox(config, tools) as sandbox:
        sandbox.execute("x = 2")
        sandbox.execute("print(x * 21)")     # ExecutionResult(success=True, output="42\n", ...)
"""

import multiprocessing
import time

from .child import child_main
from .config_sandbox import Conifg_Sandbox
from .protocol import (ExecutionResult, ExitSignal, ProtocolError, RunCode,
                       ToolCall, ToolReply, receive_message, send_message)

# "spawn" starts a fresh interpreter for the child. "fork" is unsafe when the
# parent has threads, which is the case with SyncMcpClient
_CONTEXT = multiprocessing.get_context("spawn")

_EXIT_EXCEPTIONS = {"SystemExit": SystemExit, "KeyboardInterrupt": KeyboardInterrupt}


class _ChildTimeout(Exception):
    pass


class Sandbox:
    """Controls the child process: start, execute, timeout, stop."""

    def __init__(self, config: Conifg_Sandbox | None = None, tools: dict | None = None):
        """tools: {tool_name: function}, run in the parent when the code calls them."""
        self.config = config or Conifg_Sandbox()
        self.tools = tools or {}
        self._process = None
        self._conn = None

    # ------------------------------------------------------------ lifecycle --

    def start(self):
        # Only names and descriptions go to the child: the functions stay here
        tool_docs = {name: function.__doc__ for name, function in self.tools.items()}
        parent_conn, child_conn = _CONTEXT.Pipe()
        self._process = _CONTEXT.Process(
            target=child_main, args=(child_conn, self.config, tool_docs), daemon=True
        )
        self._process.start()
        child_conn.close()  # only the child keeps its end of the pipe
        self._conn = parent_conn

    def close(self):
        if self._process is None:
            return
        self._process.kill()
        self._process.join()
        self._conn.close()
        self._process = None
        self._conn = None

    def restart(self):
        self.close()
        self.start()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ execution --

    def execute(self, code: str, interactive: bool = False) -> ExecutionResult:
        """Run `code` in the persistent namespace.

        interactive: also print the value of the last expression (REPL).
        """
        if self._process is None:
            self.start()
        try:
            return self._run(code, interactive)
        except (SystemExit, KeyboardInterrupt):
            # exit() in the code, or Ctrl+C while the child may still be busy:
            # stop it, the next execute() starts a fresh one
            self.close()
            raise

    def _run(self, code: str, interactive: bool) -> ExecutionResult:
        send_message(self._conn, RunCode(code, interactive))

        # Only the time spent running the LLM's code counts, not tool calls
        time_left = self.config.max_execution_time_seconds
        while True:
            try:
                message, time_left = self._wait_for_child(time_left)
            except _ChildTimeout:
                timeout = self.config.max_execution_time_seconds
                return self._state_lost(f"Timeout: the code ran for more than {timeout}s and was stopped.")
            except EOFError:
                return self._state_lost("The sandbox process crashed (memory limit exceeded?).")
            except ProtocolError as e:
                return self._state_lost(str(e))

            if isinstance(message, ToolCall):
                send_message(self._conn, self._call_tool(message))
            elif isinstance(message, ExitSignal):
                raise _EXIT_EXCEPTIONS[message.exception_name](*message.args)
            elif isinstance(message, ExecutionResult):
                return message
            else:
                return self._state_lost(f"Unexpected message from the sandbox: {type(message).__name__}")

    def _wait_for_child(self, time_left: float):
        """Waits for the next message. Returns (message, time left)."""
        started = time.monotonic()
        if not self._conn.poll(time_left):
            raise _ChildTimeout()
        message = receive_message(self._conn)
        return message, time_left - (time.monotonic() - started)

    def _call_tool(self, call: ToolCall) -> ToolReply:
        # Runs the real tool here, in the parent, outside the sandbox
        tool = self.tools.get(call.name)
        if tool is None:
            return ToolReply(error=f"Unknown tool: {call.name}")
        if not isinstance(call.arguments, dict):
            return ToolReply(error="Tool arguments must be passed by keyword")
        try:
            value = tool(**call.arguments)
        except Exception as e:
            return ToolReply(error=f"{type(e).__name__}: {e}")
        # MCP tools return text; str() keeps the reply JSON-safe for any other tool
        return ToolReply(value=value if isinstance(value, str) else str(value))

    def _state_lost(self, reason: str) -> ExecutionResult:
        self.restart()
        error = f"{reason} The sandbox was restarted: all variables were lost."
        return ExecutionResult(success=False, output="", error=error)
