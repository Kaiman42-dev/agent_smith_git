import asyncio
import concurrent.futures
import os
import shlex
import sys
import threading
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client


class McpClient:
    """MCP client that picks its transport from the target it receives.

    - a URL ("http://127.0.0.1:8000/mcp")       -> streamable HTTP
    - a command ("python3 mcp_tools_mbpp.py")   -> stdio
    """

    def __init__(self, target: str):
        self.target = target
        self.session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    def _open_transport(self):
        # The only transport-specific code: both return a (read, write) pair
        if self.target.startswith(("http://", "https://")):
            return streamable_http_client(self.target)
        command, *args = shlex.split(self.target)
        return stdio_client(StdioServerParameters(command=command, args=args, env=os.environ))

    async def __aenter__(self):
        # AsyncExitStack replaces the two nested `async with`: it opens the
        # transport then the session, and closes them in reverse order
        self._stack = AsyncExitStack()
        try:
            read, write = await self._stack.enter_async_context(self._open_transport())
            self.session = await self._stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()
        self.session = None

    async def list_tools(self):
        return (await self.session.list_tools()).tools

    async def call_tool(self, name: str, arguments: dict):
        return await self.session.call_tool(name, arguments)

    async def list_resources(self):
        return (await self.session.list_resources()).resources

    async def read_resource(self, uri: str):
        return await self.session.read_resource(uri)

    async def list_prompts(self):
        return (await self.session.list_prompts()).prompts

    async def get_prompt(self, name: str, arguments: dict):
        return await self.session.get_prompt(name, arguments)


class SyncMcpClient:
    """Synchronous version of McpClient, for non-async code (the sandbox).

    An asyncio loop runs forever in a separate thread and keeps the session
    open. Each call sends a coroutine to that loop and waits for the result.

    Usage: `with SyncMcpClient(target) as client: ...`
    """

    def __init__(self, target: str):
        self.target = target
        self._client: McpClient | None = None
        self._closing: asyncio.Event | None = None
        self._main: concurrent.futures.Future | None = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)

    async def _keep_open(self, ready: concurrent.futures.Future):
        # The mcp library requires the connection to be opened and closed in
        # the same task: this coroutine keeps the `async with` open until __exit__
        try:
            async with McpClient(self.target) as client:
                self._client = client
                self._closing = asyncio.Event()
                ready.set_result(None)
                await self._closing.wait()
        except BaseException as e:
            if not ready.done():
                ready.set_exception(e)
            raise

    def _run(self, coro):
        # Sends the coroutine to the thread's loop and blocks until the result
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def _stop_loop(self):
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()

    def __enter__(self):
        self._thread.start()
        ready = concurrent.futures.Future()
        self._main = asyncio.run_coroutine_threadsafe(self._keep_open(ready), self._loop)
        try:
            ready.result()
        except BaseException as e:
            self._stop_loop()
            if not isinstance(e, Exception):
                raise
            # The mcp library wraps the real error in an ExceptionGroup
            # ("unhandled errors in a TaskGroup"): keep the one that explains
            cause = e
            while getattr(cause, "exceptions", None):
                cause = cause.exceptions[0]
            raise ConnectionError(f"cannot connect to the MCP server {self.target!r}: "
                                  f"{type(cause).__name__}: {cause}") from e
        return self

    def __exit__(self, *exc):
        try:
            self._loop.call_soon_threadsafe(self._closing.set)
            self._main.result()
        finally:
            self._stop_loop()

    def list_tools(self):
        return self._run(self._client.list_tools())

    def call_tool(self, name: str, arguments: dict):
        return self._run(self._client.call_tool(name, arguments))

    def list_resources(self):
        return self._run(self._client.list_resources())

    def read_resource(self, uri: str):
        return self._run(self._client.read_resource(uri))

    def list_prompts(self):
        return self._run(self._client.list_prompts())

    def get_prompt(self, name: str, arguments: dict):
        return self._run(self._client.get_prompt(name, arguments))


test_input = {
    "code": """
def add(a, b):
    return a + b
""",
    "test_list": ["assert add(1, 2) == 3", "assert add(-1, 1) == 0"]
}

prompt_args = {
    "task_definition": """ write an addition""",
    "function_definition": """ def add(a,b):""",
    "test_list": """assert add(1,2) == 3 \nassert add(-1,1) == 0"""
}


async def main(target: str):
    async with McpClient(target) as client:
        print(f"Connected to the MCP server: {target}")
        tools = await client.list_tools()
        for tool in tools:
            print(f"Tool: {tool.name}, description: {tool.description}")
            print(f"input schema: properties: {tool.input_schema.get('properties', {})}")
            print(f"input schema: required: {tool.input_schema.get('required', [])}")

        response = await client.call_tool(tools[0].name, test_input)
        print(f"\nresponse: {response}")
        resources = await client.list_resources()
        print(f"\nlist_resources response: {resources}\n")

        resource_content = await client.read_resource("mbpp://limits")
        print(f"read resource = {resource_content}\n")

        prompts = await client.list_prompts()
        print(f"\nlist_prompts = {prompts}\n")

        prompt = await client.get_prompt(prompts[0].name, prompt_args)
        print(f"\nresult_prompt = {prompt}")


if __name__ == "__main__":
    # python mcp_client.py                            -> stdio (default)
    # python mcp_client.py http://127.0.0.1:8000/mcp  -> HTTP
    target = sys.argv[1] if len(sys.argv) > 1 else "python3 mcp_tools_mbpp.py"
    asyncio.run(main(target))
