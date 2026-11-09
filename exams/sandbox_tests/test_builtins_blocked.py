# Test: Restricted builtins - dangerous builtins must be blocked

# Test eval - should fail
try:
    result = eval("1 + 1")
    print("FAIL: eval executed successfully")
except Exception:
    print("OK: eval blocked")

# Test exec - should fail
try:
    exec("x = 42")
    print("FAIL: exec executed successfully")
except Exception:
    print("OK: exec blocked")

# Test compile - should fail
try:
    code = compile("x = 42", "<string>", "exec")
    print("FAIL: compile executed successfully")
except Exception:
    print("OK: compile blocked")

# Positive test: safe builtins still work
try:
    assert len([1, 2, 3]) == 3
    assert type(42) == int
    assert list(range(3)) == [0, 1, 2]
    print("OK: safe builtins work")
except Exception:
    print("FAIL: safe builtins broken")

print("=== BUILTINS BLOCKED TEST COMPLETE ===")
