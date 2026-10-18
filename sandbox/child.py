"""Code that runs INSIDE the sandbox process.

The parent (sandbox.py) starts this process once per task. Here we apply the
restrictions, then loop: receive code, run it in a persistent namespace,
send the result back.

The namespace holds two kinds of functions (subject, "Architectural boundary"):
- MCP tool proxies: they forward the call to the parent, which runs the real
  tool outside the sandbox
- final_answer: provided by the sandbox itself, always present
"""

import ast
import builtins
import contextlib
import io
import linecache
import os
import signal
import traceback

from .config_sandbox import Conifg_Sandbox
from .protocol import (ExecutionResult, ExitSignal, RunCode, ToolCall,
                       receive_message, send_message)

REMOVED_BUILTINS = ("eval", "exec", "compile", "breakpoint", "input")
MAX_CAPTURED_OUTPUT = 50_000  # characters kept from print() output


# -------------------------------------------- functions given to the LLM --

class FinalAnswerSignal(BaseException):
    """Raised by final_answer() to stop the code block immediately.

    It inherits from BaseException, not Exception, so that an
    `except Exception` written by the LLM does not swallow it.
    """

    def __init__(self, answer: str):
        super().__init__(answer)
        self.answer = answer


def final_answer(*args, **kwargs):
    """Submit the final answer and end the task.

    Takes exactly one argument, positional or keyword: LLMs write both
    final_answer(code) and final_answer(code=code).
    """
    values = list(args) + list(kwargs.values())
    if len(values) != 1:
        raise TypeError(f"final_answer() takes exactly one argument ({len(values)} given)")
    raise FinalAnswerSignal(str(values[0]))


def make_tool_proxy(conn, tool_name: str, description: str | None):
    """A function that looks like the MCP tool, but only relays the call.

    The real tool runs in the parent, outside the sandbox: it is not subject
    to the sandbox restrictions or timeout.
    """
    def tool_proxy(**kwargs):
        send_message(conn, ToolCall(name=tool_name, arguments=kwargs))
        reply = receive_message(conn)
        if reply.error is not None:
            raise RuntimeError(reply.error)
        return reply.value

    # __qualname__ is the name shown in error messages (e.g. TypeError)
    tool_proxy.__name__ = tool_proxy.__qualname__ = tool_name
    tool_proxy.__doc__ = description
    return tool_proxy


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


def run_code(code: str, namespace: dict, step: int, interactive: bool = False) -> ExecutionResult:
    # A unique "file name" registered in linecache lets the traceback
    # display the LLM's source lines
    filename = f"<sandbox-step-{step}>"
    linecache.cache[filename] = (len(code), None, code.splitlines(True), filename)

    captured = CappedOutput()
    error = ""
    answer = None
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        try:
            # compile() rather than ast.parse(): no extra frame in the traceback
            tree = compile(code, filename, "exec", ast.PyCF_ONLY_AST)
            last_expression = None
            if interactive and tree.body and isinstance(tree.body[-1], ast.Expr):
                # Like the Python REPL: the value of the last expression is printed
                last_expression = ast.Expression(tree.body.pop().value)
            exec(compile(tree, filename, "exec"), namespace)
            if last_expression is not None:
                value = eval(compile(last_expression, filename, "eval"), namespace)
                if value is not None:
                    print(repr(value))
        except FinalAnswerSignal as final:
            answer = final.answer
        except Exception as e:
            error = format_error(e)

    output = captured.getvalue()
    if captured.truncated:
        output += "\n[output truncated]"
    return ExecutionResult(success=not error, output=output, error=error,
                           final_answer=answer)


def build_namespace(conn, config: Conifg_Sandbox, tool_docs: dict) -> dict:
    """The LLM's namespace: restricted builtins, tool proxies, final_answer."""
    namespace = {
        "__builtins__": Restrictions(config).build_builtins(),
        "__name__": "__sandbox__",
    }
    for tool_name, description in tool_docs.items():
        namespace[tool_name] = make_tool_proxy(conn, tool_name, description)
    namespace["final_answer"] = final_answer  # set last: a tool cannot replace it
    return namespace


def child_main(conn, config: Conifg_Sandbox, tool_docs: dict):
    """Entry point of the sandbox process.

    tool_docs: {tool_name: description} of the MCP tools to expose.
    """
    apply_process_limits(config)
    namespace = build_namespace(conn, config, tool_docs)

    step = 0
    while True:
        try:
            message = receive_message(conn)
        except EOFError:
            return  # the parent closed the pipe
        if not isinstance(message, RunCode):
            continue  # the parent only sends ToolReply in answer to a ToolCall

        step += 1
        try:
            result = run_code(message.code, namespace, step, message.interactive)
        except (SystemExit, KeyboardInterrupt) as e:
            # exit(code) arguments must survive JSON: keep int/str, repr the rest
            args = [arg if isinstance(arg, (int, str)) else repr(arg) for arg in e.args]
            send_message(conn, ExitSignal(type(e).__name__, args))
            return
        send_message(conn, result)
