"""Bridge between an MCP server and the sandbox.

Turns what the server announces (tools, schemas) into what the sandbox needs:
callable Python functions, and a manual for the LLM.

The functions receive the client as a parameter instead of creating it: any
object with `list_tools()` and `call_tool(name, arguments)` works
(SyncMcpClient, or a fake client in tests).
"""

import inspect

# JSON Schema types -> Python annotations (what the LLM knows best)
_JSON_TO_PY = {"string": "str", "integer": "int", "number": "float",
               "boolean": "bool", "object": "dict", "null": "None"}


def _result_to_text(result) -> str:
    # A CallToolResult holds a list of contents: keep only the text ones
    return "\n".join(item.text for item in result.content if item.type == "text")


def make_tool(client, tool_name: str, description: str | None = None):
    """Builds a Python function that calls the MCP tool `tool_name`.

    Arguments must be passed by keyword: run_tests(code=..., test_list=...)
    """
    def tool_function(**kwargs):
        result = client.call_tool(tool_name, kwargs)
        text = _result_to_text(result)
        if result.is_error:
            raise RuntimeError(f"{tool_name}: {text}")
        return text

    # __qualname__ is the name shown in error messages (e.g. TypeError)
    tool_function.__name__ = tool_function.__qualname__ = tool_name
    tool_function.__doc__ = description
    return tool_function


def build_tools(client) -> dict:
    """Returns {tool_name: function} for every tool of the connected server."""
    return {tool.name: make_tool(client, tool.name, tool.description)
            for tool in client.list_tools()}


def _schema_to_type(schema: dict) -> str:
    # "Any" for anything we cannot translate (unknown server)
    if "anyOf" in schema:
        return " | ".join(_schema_to_type(s) for s in schema["anyOf"])
    json_type = schema.get("type")
    if json_type == "array":
        return f"list[{_schema_to_type(schema.get('items', {}))}]"
    if isinstance(json_type, list):  # e.g. {"type": ["string", "null"]}
        return " | ".join(_JSON_TO_PY.get(t, "Any") for t in json_type)
    return _JSON_TO_PY.get(json_type, "Any")


def _tool_stub(tool) -> str:
    # Writes the tool as a Python function: signature + docstring
    schema = tool.input_schema or {}
    required = set(schema.get("required", []))
    params, params_doc = [], []
    for name, prop in schema.get("properties", {}).items():
        param = f"{name}: {_schema_to_type(prop)}"
        if name not in required:
            param += f" = {prop.get('default')!r}"
        params.append(param)
        if prop.get("description"):
            params_doc.append(f"{name}: {prop['description']}")

    doc = inspect.cleandoc(tool.description or "No description.")
    if params_doc:
        doc += "\n\nParameters:\n" + "\n".join(f"    {p}" for p in params_doc)
    doc = "\n".join(f"    {line}" if line else "" for line in doc.splitlines())
    return f'def {tool.name}({", ".join(params)}) -> str:\n    """\n{doc}\n    """'


def build_manual(tools) -> str:
    """Tool manual for the LLM prompt, generated from the tool schemas.

    `tools` is the list returned by client.list_tools(): the manual follows
    the connected server automatically.
    """
    if not tools:
        return "## Available tools\n\nNo MCP tools are available."
    stubs = "\n\n".join(_tool_stub(tool) for tool in tools)
    return (
        "## Available tools\n\n"
        "The following functions are already defined in your Python namespace.\n"
        "- Call them directly, always with keyword arguments: tool(arg=value).\n"
        "- Each call returns a string.\n"
        "- An invalid call raises RuntimeError with the server's message.\n\n"
        f"```python\n{stubs}\n```"
    )
