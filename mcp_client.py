import asyncio
import shlex
import sys
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client


class McpClient:
    """Client MCP qui choisit son transport selon la cible recue.

    - une URL ("http://127.0.0.1:8000/mcp")  -> streamable HTTP
    - une commande ("python3 mcp_tools_mbpp.py") -> stdio
    """

    def __init__(self, target: str):
        self.target = target
        self.session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    def _open_transport(self):
        # Seul endroit qui depend du transport : les deux renvoient (read, write)
        if self.target.startswith(("http://", "https://")):
            return streamable_http_client(self.target)
        command, *args = shlex.split(self.target)
        return stdio_client(StdioServerParameters(command=command, args=args))

    async def __aenter__(self):
        # AsyncExitStack remplace les deux `async with` imbriques :
        # il ouvre transport puis session, et les referme dans l'ordre inverse
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


test_input = {
    "code": """
def add(a, b):
    return a + b
""",
    "test_list": ["assert add(1, 2) == 3", "assert add(-1, 1) == 0"]
}

prompt_args = {
    "task_definition": """ faire une adition""",
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

        reponse = await client.call_tool(tools[0].name, test_input)
        print(f"\nresponse: {reponse}")
        ressource_response = await client.list_resources()
        print(f"\nlist_resources response: {ressource_response}\n")

        result_read = await client.read_resource("mbpp://limits")
        print(f"read ressource = {result_read}\n")

        list_prompt = await client.list_prompts()
        print(f"\nlist_promp = {list_prompt}\n")

        result_prompt = await client.get_prompt(list_prompt[0].name, prompt_args)
        print(f"\nresult_prompt = {result_prompt}")


if __name__ == "__main__":
    # python mcp_client.py                            -> stdio (par defaut)
    # python mcp_client.py http://127.0.0.1:8000/mcp  -> HTTP
    target = sys.argv[1] if len(sys.argv) > 1 else "python3 mcp_tools_mbpp.py"
    asyncio.run(main(target))