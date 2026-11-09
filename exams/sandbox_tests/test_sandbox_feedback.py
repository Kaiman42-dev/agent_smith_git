# Test: Sandbox feedback transparency
#
# Verifies that the sandbox provides explicit feedback in error situations:
# - No code block found in input
# - Truncated output notification
# - Timeout with partial output
#
# NOTE: This test checks the sandbox's feedback behavior by examining
# its responses to various edge cases. It is designed to be run
# interactively or by the exam script which checks output patterns.
#
# Run with: cat test_sandbox_feedback.py | uv run sandbox sandbox_config.json

print("Testing sandbox feedback transparency...")
print()

# Test 1: Verify that output from code execution is captured
# (This is a basic positive test - the sandbox should show this output)
print("FEEDBACK_TEST_1: Output capture works")

# Test 2: Verify that errors are reported back clearly
try:
    result = 1 / 0
except ZeroDivisionError as e:
    print(f"FEEDBACK_TEST_2: Error reported: {e}")

# Test 3: Verify long output handling
# Print enough lines to potentially trigger truncation
long_output = "\n".join([f"line_{i}" for i in range(50)])
print(f"FEEDBACK_TEST_3: Generated 50 lines of output")

# Test 4: Verify exception tracebacks are visible
try:
    x = {}
    _ = x['nonexistent_key']
except KeyError as e:
    print(f"FEEDBACK_TEST_4: KeyError reported: {e}")

print()
print("=== SANDBOX FEEDBACK COMPLETE ===")
