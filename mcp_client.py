import asyncio
import inspect
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

test_input = {
    "code": """
def add(a, b):
    return a + b
""",
    "test_list": ["assert add(1, 2) == 5", "assert add(-1, 1) == 1"]
}
async def main():

    params = StdioServerParameters(command="python3", args=["mcp_tools_mbpp.py"])
    async with stdio_client(params) as streams:
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
asyncio.run(main())