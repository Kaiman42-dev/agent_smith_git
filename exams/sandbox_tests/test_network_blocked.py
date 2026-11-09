# Test: Network access restrictions - sandboxed code must not open connections

# Test 1: TCP connection via socket to Google DNS - should fail
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(("8.8.8.8", 53))
    s.close()
    print("FAIL: TCP connection to 8.8.8.8:53 succeeded")
except Exception:
    print("OK: TCP connection blocked")

# Test 2: HTTP GET via urllib to pypi.org - should fail
try:
    import urllib.request
    urllib.request.urlopen("https://pypi.org/simple/", timeout=3)
    print("FAIL: HTTP request to pypi.org succeeded")
except Exception:
    print("OK: HTTP request blocked")

# Test 3: HTTP via http.client to github.com - should fail
try:
    import http.client
    conn = http.client.HTTPSConnection("api.github.com", timeout=3)
    conn.request("GET", "/")
    print("FAIL: HTTPS connection to api.github.com succeeded")
except Exception:
    print("OK: HTTPS connection blocked")

# Test 4: Third-party requests library to huggingface.co - should fail
try:
    import requests
    requests.get("https://huggingface.co/api/models", timeout=3)
    print("FAIL: requests to huggingface.co succeeded")
except Exception:
    print("OK: requests library blocked")

# Positive test: non-network imports still work
try:
    import json
    result = json.dumps({"network": "blocked"})
    print("OK: non-network imports work")
except Exception:
    print("FAIL: non-network imports broken")

print("=== NETWORK BLOCKED TEST COMPLETE ===")
