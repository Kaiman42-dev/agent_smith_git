# Test: MCP stdio server integration  
# Run: uv run sandbox --mcp-stdio "python sandbox_tests/simple_mcp_server.py --stdio"
# Then cat this file into the sandbox

print("Testing MCP stdio connection...")

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
        result = add(a=5, b=7)
        print(f"add(5, 7) = {result}")
        if "12" in str(result):
            print("Tool call successful!")
            print("=== MCP STDIO CONFIG OK ===")
        else:
            print(f"Unexpected result: {result}")
            print("=== MCP STDIO CONFIG FAIL ===")
    elif 'echo' in available:
        result = echo(message="hello")
        print(f"echo('hello') = {result}")
        if "hello" in str(result):
            print("Tool call successful!")
            print("=== MCP STDIO CONFIG OK ===")
        else:
            print(f"Unexpected result: {result}")
            print("=== MCP STDIO CONFIG FAIL ===")
    else:
        print("No testable tool available")
        print("=== MCP STDIO CONFIG FAIL ===")
else:
    print("No tools available - MCP connection may have failed")
    print("Make sure to run with --mcp-stdio 'python simple_mcp_server.py --stdio'")
    print("=== MCP STDIO CONFIG FAIL ===")
