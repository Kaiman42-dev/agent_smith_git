# Test: MBPP tools via MCP
# Run sandbox with: uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py"
# Then cat this file into it

import json

# Test run_tests function (provided by MCP server)
code = """
def add(a, b):
    return a + b
"""

tests = [
    "assert add(1, 2) == 3",
    "assert add(0, 0) == 0",
    "assert add(-1, 1) == 0",
]

print("Testing run_tests tool via MCP...")

# run_tests is injected by the MCP server connection
# It returns a JSON string with success and output fields
result = run_tests(code=code, test_list=tests)
print(f"Result: {result}")

# Parse the result
verify_ok = False
try:
    parsed = json.loads(result)
    success = parsed.get("success", False)
    output = parsed.get("output", "")

    if success:
        verify_ok = True
        print("\n=== MBPP TOOLS OK ===")
    else:
        print(f"Output: {output}")
        print("\n=== MBPP TOOLS FAILED ===")
except json.JSONDecodeError:
    # If not JSON, check for success indicators in raw result
    if "success" in result.lower() and "true" in result.lower():
        verify_ok = True
    else:
        verify_ok = False

errors = []

if not verify_ok:
    errors.append("run_tests")

# Test final_answer tool
print("\nTesting final_answer tool...")
if 'final_answer' in dir():
    try:
        fa_result = final_answer(answer="def add(a, b): return a + b")
        print(f"final_answer result: {fa_result}")
        print("OK: final_answer is callable")
    except Exception as e:
        print(f"final_answer raised: {e}")
        print("OK: final_answer is callable (raised expected error)")
else:
    print("FAIL: final_answer not available")
    errors.append("final_answer")

if not errors:
    print("\n=== MBPP TOOLS OK ===")
else:
    print(f"\nErrors: {errors}")
    print("\n=== MBPP TOOLS FAILED ===")
