import asyncio
import shlex
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
async def main():

    params = StdioServerParameters(command="python3", args=["mcp_tools_mbpp.py"])
    async with stdio_client(params) as streams: # stdio_client returns a pair of streams (reader, writer), il sert à communiquer avec le serveur mcp_tools_mbpp.py via stdio
        print("Connected to the MCP server via stdio.")
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            result = await session.list_tools()
            for tool in result.tools:
                print(f"Tool: {tool.name}, description: {tool.description}")
                print(f"input schema: properties: {tool.input_schema.get('properties', {})}")
                print(f"input schema: required: {tool.input_schema.get('required', [])}")
    
            reponse = await session.call_tool(str(result.tools[0].name), test_input)
            print(f"\nresponse: {reponse}")
            ressource_response = await session.list_resources()
            print(f"\nlist_resources response: {ressource_response}\n")

            result_read = await session.read_resource("mbpp://limits")
            print(f"read ressource = {result_read}\n")
        
            list_prompt = await session.list_prompts()
            print(f"\nlist_promp = {list_prompt}\n")
        
            result_prompt = await session.get_prompt(list_prompt.prompts[0].name, prompt_args)
            print(f"\nresult_prompt = {result_prompt}")
            
asyncio.run(main())