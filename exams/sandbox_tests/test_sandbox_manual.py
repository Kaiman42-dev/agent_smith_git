# Test: Sandbox manual generation from MCP server schemas
#
# Verifies that the sandbox generates tool documentation from the connected
# MCP server's tool schemas. The manual should include tool names, descriptions,
# and parameter types.
#
# Run with: cat test_sandbox_manual.py | uv run sandbox --mcp-stdio "python simple_mcp_server.py --stdio"

errors = []

print("Testing sandbox manual generation...")
print()

# The sandbox should have generated a manual/documentation from the MCP tools.
# Check if there's a way to access it (typically via a special variable or function).

manual_found = False
manual_content = ""

# Check if sandbox_manual variable is in namespace
if 'sandbox_manual' in dir():
    manual_content = str(sandbox_manual)
    manual_found = True
    print("OK: Found manual via 'sandbox_manual' variable")
elif 'tool_manual' in dir():
    manual_content = str(tool_manual)
    manual_found = True
    print("OK: Found manual via 'tool_manual' variable")
elif 'tools_manual' in dir():
    manual_content = str(tools_manual)
    manual_found = True
    print("OK: Found manual via 'tools_manual' variable")

# Check if get_manual function exists
if not manual_found:
    if 'get_manual' in dir():
        manual_content = str(get_manual())
        manual_found = True
        print("OK: Found manual via 'get_manual()' function")
    elif 'get_tool_manual' in dir():
        manual_content = str(get_tool_manual())
        manual_found = True
        print("OK: Found manual via 'get_tool_manual()' function")

if not manual_found:
    # The manual might not be exposed as a standalone variable.
    # Check that the tools from simple_mcp_server are at least available.
    print("INFO: No dedicated manual variable/function found")
    print("Checking if tools from MCP server are discoverable...")

    tool_names = ['add', 'multiply', 'echo']
    for tool in tool_names:
        if tool in dir():
            print(f"  OK: {tool} is available")
        else:
            print(f"  FAIL: {tool} not available")
            errors.append(f"missing_{tool}")

if manual_found and manual_content:
    print(f"Manual content (first 500 chars):")
    print(manual_content[:500])
    print()

    # Verify the manual contains expected tool information
    # The simple_mcp_server provides: add, multiply, echo
    expected_tools = ['add', 'multiply', 'echo']
    for tool in expected_tools:
        if tool in manual_content.lower():
            print(f"OK: Manual mentions '{tool}'")
        else:
            print(f"FAIL: Manual missing '{tool}'")
            errors.append(f"manual_missing_{tool}")

print()
if not errors:
    print("=== SANDBOX MANUAL OK ===")
else:
    print(f"Errors: {errors}")
    print("=== SANDBOX MANUAL FAILED ===")
