# Test: Layer 1 bonus - bare-except timeout bypass resistance
# This test validates that the sandbox can handle code that catches ALL exceptions
# (including TimeoutError) in a loop. Only subprocess-based kill (layer 1) can
# reliably stop this. With layer 0 (signal.alarm), the TimeoutError is caught
# by the bare except and the loop continues forever.
#
# Expected behavior:
#   Layer 0 (signal.alarm): Process hangs after catching TimeoutError.
#     The exam script wraps this with an external `timeout` as a safety net.
#   Layer 1 (subprocess kill): Process is terminated regardless of exception
#     handling. The marker below prints successfully.

import time

start = time.time()
caught_timeout = False

# This loop catches everything, including TimeoutError from signal.alarm.
# Only an external kill signal (SIGKILL via subprocess) can stop it.
while True:
    try:
        time.sleep(0.1)
    except:
        caught_timeout = True
        elapsed = time.time() - start
        # We caught the TimeoutError but keep running to prove bypass.
        # With layer 0, only one alarm fires, so we just continue.
        # Wait a bit to demonstrate we're still alive past the timeout.
        time.sleep(2)
        break

elapsed = time.time() - start
if caught_timeout:
    print(f"WARN: caught timeout exception and continued running ({elapsed:.1f}s)")
    print("Layer 1 (subprocess isolation) would prevent this bypass.")
else:
    print(f"OK: sandbox terminated execution cleanly")

print("=== LAYER1 BONUS COMPLETE ===")
