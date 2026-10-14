import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

test_input = {
                "code": """
def add(a, b):
    return a + b
""",
                "test_list": ["assert add(1, 2) == 3", "assert add(-1, 1) == 0"]
            }

async def main():
    async with streamable_http_client("http://127.0.0.1:8000/mcp") as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            result = await session.list_tools()
            for tool in result.tools:
                print(f"Tool: {tool.name}, description: {tool.description}")
                print(f"input schema: properties: {tool.input_schema.get('properties', {})}")
                print(f"input schema: required: {tool.input_schema.get('required', [])}")
            result_call_tool = await session.call_tool(str(result.tools[0].name), test_input)
            print(f"\nresponse: {result_call_tool}")
    
            

asyncio.run(main())
