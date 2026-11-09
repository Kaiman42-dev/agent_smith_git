# Test: MCP HTTP server integration (streamable HTTP transport)
# First start the server: python sandbox_tests/simple_mcp_server.py --http --port 18080
# Then run: uv run sandbox --mcp-server http://localhost:18080/mcp
# Then cat this file into the sandbox

print("Testing MCP HTTP connection...")

# Check if tools from MCP server are available
# The simple_mcp_server.py provides: add, multiply, echo

tools_to_check = ['add', 'multiply', 'echo']
available = []
missing = []

for tool in tools_to_check:
    if tool in dir():
        available.append(tool)
    else:
        missing.append(tool)

print(f"Available tools: {available}")
print(f"Missing tools: {missing}")

if len(available) >= 1:
    # Test one of the tools
    if 'add' in available:
        result = add(a=2, b=3)
        print(f"add(2, 3) = {result}")
        if "5" in str(result):
            print("Tool call successful!")
            print("=== MCP HTTP CONFIG OK ===")
        else:
            print(f"Unexpected result: {result}")
            print("=== MCP HTTP CONFIG FAIL ===")
    elif 'echo' in available:
        result = echo(message="test")
        print(f"echo('test') = {result}")
        if "test" in str(result):
            print("Tool call successful!")
            print("=== MCP HTTP CONFIG OK ===")
        else:
            print(f"Unexpected result: {result}")
            print("=== MCP HTTP CONFIG FAIL ===")
    else:
        print("No testable tool available")
        print("=== MCP HTTP CONFIG FAIL ===")
else:
    print("No tools available - MCP connection may have failed")
    print("Make sure to run with --mcp-server http://localhost:18080")
    print("=== MCP HTTP CONFIG FAIL ===")
