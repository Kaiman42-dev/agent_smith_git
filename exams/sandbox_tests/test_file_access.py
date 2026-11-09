# Test: File access restrictions - copy/paste entire file at once

# Test /etc/passwd - should fail
try:
    f = open('/etc/passwd', 'r')
    f.close()
    print("FAIL: /etc/passwd accessible")
except Exception:
    print("OK: /etc/passwd blocked")

# Test path traversal - should fail
try:
    f = open('../../../etc/passwd', 'r')
    f.close()
    print("FAIL: path traversal accessible")
except Exception:
    print("OK: path traversal blocked")

# Test /home - should fail
try:
    f = open('/home/user/.bashrc', 'r')
    f.close()
    print("FAIL: /home accessible")
except Exception:
    print("OK: /home blocked")

# Test /root - should fail
try:
    f = open('/root/.bashrc', 'r')
    f.close()
    print("FAIL: /root accessible")
except Exception:
    print("OK: /root blocked")

# Positive tests: allowed directories should work

# Test /tmp - should succeed (commonly allowed)
try:
    test_file = "/tmp/sandbox_test_write.txt"
    with open(test_file, 'w') as f:
        f.write("test content")
    with open(test_file, 'r') as f:
        content = f.read()
    if content == "test content":
        print("OK: /tmp write/read works")
    else:
        print("FAIL: /tmp write/read returned wrong content")
except Exception:
    print("INFO: /tmp not in allowed directories (OK if not configured)")

print("=== FILE ACCESS TEST COMPLETE ===")
