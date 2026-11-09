# Test: Memory limit enforcement
# Uses sandbox_config_resources.json (256MB limit).
# Small allocation should work; large allocation should raise MemoryError.

# Positive test: small allocation within limits
try:
    small = bytearray(1 * 1024 * 1024)  # 1 MB
    print(f"OK: small allocation succeeded ({len(small)} bytes)")
    del small
except MemoryError:
    print("FAIL: small allocation raised MemoryError (limit too restrictive)")

# Negative test: large allocation should exceed limit
try:
    large = bytearray(512 * 1024 * 1024)  # 512 MB, well over 256MB limit
    print(f"FAIL: large allocation succeeded ({len(large)} bytes)")
    del large
except MemoryError:
    print("OK: large allocation correctly raised MemoryError")

print("=== MEMORY TEST COMPLETE ===")
