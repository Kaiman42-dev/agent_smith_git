# Test: Timeout enforcement
# Uses sandbox_config_resources.json (5s timeout) for fast feedback.
# Short computation should complete; busy loop should be interrupted.

import time

# Positive test: short computation completes within timeout
start = time.time()
total = sum(range(1000))
elapsed = time.time() - start
print(f"OK: short computation completed in {elapsed:.3f}s (result={total})")

# Partial output test: print before timeout to verify output is preserved
print("PARTIAL_OUTPUT_MARKER: this line was printed before timeout")

# Print the COMPLETE marker BEFORE the infinite loop.
# If the sandbox correctly enforces timeout, the loop below will be interrupted
# (either via exception or subprocess kill) and this marker will be in the output.
print("=== TIMEOUT TEST COMPLETE ===")

# Negative test: busy loop should be interrupted by timeout.
# The sandbox may interrupt this via TimeoutError (in-process) or by killing
# the subprocess. Either way, the loop must not run forever.
start = time.time()
try:
    while True:
        pass
except Exception as e:
    elapsed = time.time() - start
    print(f"OK: busy loop interrupted after {elapsed:.1f}s ({e})")
