# Test: Dynamic MCP tool discovery
#
# Verifies that when an MCP server is connected, the sandbox dynamically
# discovers and exposes that server's tools as callable functions.
#
# Run with: cat test_dynamic_discovery.py | uv run sandbox --mcp-stdio "python simple_mcp_server.py --stdio"

errors = []

print("Testing dynamic MCP tool discovery...")
print()

# The simple_mcp_server.py provides: add, multiply, echo
# These should be automatically discovered and available in the sandbox namespace.

print("=== Tool Discovery ===")
expected_tools = ['add', 'multiply', 'echo']
discovered = []
missing = []

for tool in expected_tools:
    if tool in dir():
        discovered.append(tool)
        print(f"OK: '{tool}' discovered from MCP server")
    else:
        missing.append(tool)
        print(f"FAIL: '{tool}' not discovered")
        errors.append(f"not_discovered_{tool}")

print()
print(f"Discovered: {len(discovered)}/{len(expected_tools)} tools")

# Test that discovered tools are actually callable
if discovered:
    print()
    print("=== Tool Invocation ===")

    if 'add' in discovered:
        result = add(a=3, b=4)
        if "7" in str(result):
            print(f"OK: add(3, 4) = {result}")
        else:
            print(f"FAIL: add(3, 4) returned {result}, expected 7")
            errors.append("add_wrong_result")

    if 'multiply' in discovered:
        result = multiply(a=6, b=7)
        if "42" in str(result):
            print(f"OK: multiply(6, 7) = {result}")
        else:
            print(f"FAIL: multiply(6, 7) returned {result}, expected 42")
            errors.append("multiply_wrong_result")

    if 'echo' in discovered:
        result = echo(message="test_message")
        if "test_message" in str(result):
            print(f"OK: echo('test_message') = {result}")
        else:
            print(f"FAIL: echo('test_message') returned {result}")
            errors.append("echo_wrong_result")

print()
if not errors:
    print("=== DYNAMIC DISCOVERY OK ===")
else:
    print(f"Errors: {errors}")
    print("=== DYNAMIC DISCOVERY FAILED ===")
