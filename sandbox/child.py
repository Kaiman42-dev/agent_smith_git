"""Code that runs INSIDE the sandbox process.

The parent (sandbox.py) starts this process once per task. Here we apply the
restrictions, then loop: receive code, run it in a persistent namespace,
send the result back.
"""

import builtins
import contextlib
import io
import linecache
import os
import signal
import traceback
from dataclasses import dataclass

from .config_sandbox import Conifg_Sandbox

REMOVED_BUILTINS = ("eval", "exec", "compile", "breakpoint", "input")
MAX_CAPTURED_OUTPUT = 50_000  # characters kept from print() output


# ------------------------------------------------- messages sent to parent --

@dataclass
class ExecutionResult:
    """Outcome of one code block."""
    success: bool
    output: str  # everything printed (stdout + stderr)
    error: str   # traceback if the code raised, "" otherwise


@dataclass
class ExitSignal:
    """The code raised SystemExit or KeyboardInterrupt.

    The subject requires these two to reach the agent loop, so the parent
    re-raises them on its side.
    """
    exception_name: str  # "SystemExit" or "KeyboardInterrupt"
    args: tuple


# ------------------------------------------------------------ restrictions --

class Restrictions:
    """The sandbox rules (imports, files), built from the config."""

    def __init__(self, config: Conifg_Sandbox):
        self.allowed_imports = set(config.authorized_imports)
        # realpath resolves "..", symlinks, and /tmp -> /private/tmp on macOS
        self.allowed_dirs = [os.path.realpath(d) for d in config.allowed_directories]

    def is_import_allowed(self, name: str) -> bool:
        if name in self.allowed_imports:
            return True
        # "collections.abc" is allowed if "collections.*" is in the list
        parts = name.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[:i])
            if parent + ".*" in self.allowed_imports:
                return True
        return False

    def is_path_allowed(self, path: str) -> bool:
        for allowed_dir in self.allowed_dirs:
            # the os.sep check rejects "/tmp/agentevil" when "/tmp/agent" is allowed
            if path == allowed_dir or path.startswith(allowed_dir + os.sep):
                return True
        return False

    def safe_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0:
            raise ImportError("Relative imports are blocked by the sandbox")
        if not self.is_import_allowed(name):
            raise ImportError(f"Import blocked by the sandbox: {name}")
        return builtins.__import__(name, globals, locals, fromlist, level)

    def safe_open(self, file, *args, **kwargs):
        if not isinstance(file, (str, bytes, os.PathLike)):
            raise PermissionError("File descriptors are blocked by the sandbox")
        path = os.path.realpath(os.fsdecode(file))
        if not self.is_path_allowed(path):
            raise PermissionError(f"File access blocked by the sandbox: {file}")
        return builtins.open(path, *args, **kwargs)

    def build_builtins(self) -> dict:
        """A copy of the builtins for the LLM namespace.

        We do not modify the real `builtins` module: this loop and the
        allowed modules (json, datetime...) keep working normally.
        """
        restricted = dict(vars(builtins))
        for name in REMOVED_BUILTINS:
            restricted.pop(name, None)
        restricted["__import__"] = self.safe_import
        restricted["open"] = self.safe_open
        return restricted


def apply_process_limits(config: Conifg_Sandbox):
    """Limits that apply to the whole process: Ctrl+C, memory, network."""
    # Ctrl+C is handled by the parent, which then kills this process
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    try:
        import resource
        max_bytes = config.max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
    except (ImportError, ValueError, OSError):
        pass  # RLIMIT_AS is not enforced on macOS; it works on Linux

    import socket

    def blocked_socket(*args, **kwargs):
        raise PermissionError("Network access is blocked by the sandbox")

    socket.socket = blocked_socket
    socket.create_connection = blocked_socket


# --------------------------------------------------------------- execution --

class CappedOutput(io.StringIO):
    """A StringIO that stops storing text after MAX_CAPTURED_OUTPUT.

    Without it, an infinite print loop would fill the memory before the
    timeout stops it.
    """

    def __init__(self):
        super().__init__()
        self.truncated = False

    def write(self, text):
        room_left = MAX_CAPTURED_OUTPUT - self.tell()
        if len(text) > room_left:
            self.truncated = True
        if room_left > 0:
            super().write(text[:room_left])
        return len(text)


def format_error(error: Exception) -> str:
    # The first traceback frame is run_code itself: skip it so the LLM
    # only sees the lines of its own code
    llm_frames = error.__traceback__.tb_next
    return "".join(traceback.format_exception(type(error), error, llm_frames))


def run_code(code: str, namespace: dict, step: int) -> ExecutionResult:
    # A unique "file name" registered in linecache lets the traceback
    # display the LLM's source lines
    filename = f"<sandbox-step-{step}>"
    linecache.cache[filename] = (len(code), None, code.splitlines(True), filename)

    captured = CappedOutput()
    error = ""
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        try:
            exec(compile(code, filename, "exec"), namespace)
        except Exception as e:
            error = format_error(e)

    output = captured.getvalue()
    if captured.truncated:
        output += "\n[output truncated]"
    return ExecutionResult(success=not error, output=output, error=error)


def child_main(conn, config: Conifg_Sandbox):
    """Entry point of the sandbox process."""
    apply_process_limits(config)
    namespace = {
        "__builtins__": Restrictions(config).build_builtins(),
        "__name__": "__sandbox__",
    }

    step = 0
    while True:
        try:
            code = conn.recv()
        except EOFError:
            return  # the parent closed the pipe

        step += 1
        try:
            result = run_code(code, namespace, step)
        except (SystemExit, KeyboardInterrupt) as e:
            conn.send(ExitSignal(type(e).__name__, e.args))
            return
        conn.send(result)
