# Test: Blocked imports - copy/paste entire file at once
# Or run line by line interactively

# Test os - should fail
try:
    import os
    print("FAIL: os imported")
except ImportError:
    print("OK: os blocked")

# Test subprocess - should fail
try:
    import subprocess
    print("FAIL: subprocess imported")
except ImportError:
    print("OK: subprocess blocked")

# Test sys - should fail
try:
    import sys
    print("FAIL: sys imported")
except ImportError:
    print("OK: sys blocked")

# Test socket - should fail
try:
    import socket
    print("FAIL: socket imported")
except ImportError:
    print("OK: socket blocked")

# Test importlib - should fail
try:
    import importlib
    print("FAIL: importlib imported")
except ImportError:
    print("OK: importlib blocked")

# Test builtins - should fail
try:
    import builtins
    print("FAIL: builtins imported")
except ImportError:
    print("OK: builtins blocked")

print("=== BLOCKED IMPORTS TEST COMPLETE ===")
