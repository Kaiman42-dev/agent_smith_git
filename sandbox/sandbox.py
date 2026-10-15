"""Persistent sandbox: runs the LLM's code in an isolated child process.

This file is the PARENT side: it starts the child process (child.py), sends it
code through a Pipe and waits for the result. The child stays alive for the
whole task, so variables persist between steps without replaying history.

Usage:
    with Sandbox(config) as sandbox:
        sandbox.execute("x = 2")
        sandbox.execute("print(x * 21)")   # ExecutionResult(success=True, output="42\n", error="")
"""

import multiprocessing

from .child import ExecutionResult, ExitSignal, child_main
from .config_sandbox import Conifg_Sandbox

# "spawn" starts a fresh interpreter for the child. "fork" is unsafe when the
# parent has threads, which is the case with SyncMcpClient
_CONTEXT = multiprocessing.get_context("spawn")

_EXIT_EXCEPTIONS = {"SystemExit": SystemExit, "KeyboardInterrupt": KeyboardInterrupt}


class Sandbox:
    """Controls the child process: start, execute, timeout, stop."""

    def __init__(self, config: Conifg_Sandbox | None = None):
        self.config = config or Conifg_Sandbox()
        self._process = None
        self._conn = None

    def start(self):
        parent_conn, child_conn = _CONTEXT.Pipe()
        self._process = _CONTEXT.Process(
            target=child_main, args=(child_conn, self.config), daemon=True
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

    def execute(self, code: str) -> ExecutionResult:
        """Run `code` in the persistent namespace."""
        if self._process is None:
            self.start()
        self._conn.send(code)

        timeout = self.config.max_execution_time_seconds
        if not self._conn.poll(timeout):
            self.restart()
            return self._state_lost(f"Timeout: the code ran for more than {timeout}s and was stopped.")

        try:
            message = self._conn.recv()
        except EOFError:
            # The child died without answering (memory limit, crash)
            self.restart()
            return self._state_lost("The sandbox process crashed (memory limit exceeded?).")

        if isinstance(message, ExitSignal):
            self.restart()
            raise _EXIT_EXCEPTIONS[message.exception_name](*message.args)
        return message

    @staticmethod
    def _state_lost(reason: str) -> ExecutionResult:
        error = f"{reason} The sandbox was restarted: all variables were lost."
        return ExecutionResult(success=False, output="", error=error)
