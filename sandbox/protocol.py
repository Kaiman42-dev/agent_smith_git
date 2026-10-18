"""Messages exchanged between the parent (sandbox.py) and the child (child.py).

Messages travel as JSON, never as pickle: unpickling data can execute code,
and the LLM's code can reach the pipe from inside the child. With JSON, the
worst a malicious child can send is a malformed message, which the parent
rejects.

Conversation for one code block:
    parent -> child   RunCode
    child  -> parent  ToolCall      (0 or more times, when the code calls a tool)
    parent -> child   ToolReply     (one per ToolCall)
    child  -> parent  ExecutionResult or ExitSignal
"""

import json
from dataclasses import asdict, dataclass

MAX_MESSAGE_BYTES = 10 * 1024 * 1024  # a bigger message is rejected


class ProtocolError(Exception):
    """A received message is not valid JSON or not a known message."""


@dataclass
class RunCode:
    """Parent asks the child to run a code block."""
    code: str
    interactive: bool = False  # REPL: also print the value of the last expression


@dataclass
class ToolCall:
    """Child asks the parent to call an MCP tool (outside the sandbox)."""
    name: str
    arguments: dict


@dataclass
class ToolReply:
    """Parent answers a ToolCall: either a value or an error message."""
    value: str | None = None
    error: str | None = None


@dataclass
class ExecutionResult:
    """Outcome of one code block."""
    success: bool
    output: str  # everything printed (stdout + stderr)
    error: str   # traceback if the code raised, "" otherwise
    final_answer: str | None = None  # set when the code called final_answer()


@dataclass
class ExitSignal:
    """The code raised SystemExit or KeyboardInterrupt.

    The subject requires these two to reach the agent loop, so the parent
    re-raises them on its side.
    """
    exception_name: str  # "SystemExit" or "KeyboardInterrupt"
    args: list


_MESSAGE_TYPES = {cls.__name__: cls
                  for cls in (RunCode, ToolCall, ToolReply, ExecutionResult, ExitSignal)}


def send_message(conn, message):
    payload = {"type": type(message).__name__, **asdict(message)}
    conn.send_bytes(json.dumps(payload).encode())


def receive_message(conn):
    """Reads one message. Raises EOFError if the other side is gone."""
    try:
        payload = json.loads(conn.recv_bytes(MAX_MESSAGE_BYTES))
        message_class = _MESSAGE_TYPES[payload.pop("type")]
        return message_class(**payload)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        # OSError: message too big / ValueError: invalid JSON
        # KeyError, TypeError, AttributeError: not a known message shape
        raise ProtocolError(f"Invalid message from the other process: {e}") from e
