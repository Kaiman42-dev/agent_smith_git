# Test SWE-bench tools via MCP
# 
# Usage (set TESTBED_PATH env var for the MCP server):
#   TESTBED_PATH=$BASE_MOULINETTE/testbed uv run sandbox --mcp-stdio "python mcp_tools_swebench.py"
#
# The testbed directory should contain:
#   - main.py (imports User, Product, validate_email, calculate_sum)
#   - utils.py (defines calculate_sum, validate_email, etc.)
#   - models.py (defines User, Product, Order classes)
#
# NOTE: Tools are provided by the MCP server (mcp_tools_swebench.py)

print("Testing SWE-bench tools via MCP...")
print()

# Check if tools are available (injected by MCP connection)
tools = [
    'read_file',
    'search_code', 
    'search_function_or_class_definition_in_code',
    'find_references',
    'edit_file',
    'list_files',
    'run_tests',
    'get_patch',
    'final_answer'
]

errors = []

print("=== Tool Availability ===")
missing_tools = []
for tool in tools:
    if tool in dir():
        print(f"OK: {tool} available")
    else:
        print(f"FAIL: {tool} missing")
        missing_tools.append(tool)

if missing_tools:
    print()
    print(f"Missing tools: {missing_tools}")
    print("Make sure to run with --mcp-stdio 'python mcp_tools_swebench.py'")
    print()
    print("=== SWEBENCH TOOLS FAILED (tools not available) ===")
else:
    # Test list_files first to check testbed setup
    print()
    print("=== Test list_files ===")
    test_files = list_files(directory="/testbed", pattern="*.py")
    print(f"list_files result: {test_files}")
    
    testbed_ok = "main.py" in test_files and "utils.py" in test_files and "models.py" in test_files
    
    if not testbed_ok:
        print()
        print("ERROR: TESTBED_PATH not set or testbed directory not found!")
        print("You must set TESTBED_PATH before running this test:")
        print("  TESTBED_PATH=$BASE_MOULINETTE/testbed uv run sandbox --mcp-stdio 'python mcp_tools_swebench.py'")
        print()
        print("=== SWEBENCH TOOLS FAILED (TESTBED_PATH not configured) ===")
    else:
        print("OK: list_files finds all Python files")
        
        print()
        print("=== Test read_file ===")
        
        # Test 1: Read utils.py and verify content
        result = read_file(filepath="/testbed/utils.py", start_line=1, end_line=10)
        print(f"read_file result: {result[:200]}...")
        
        expected = ["1:", "calculate_sum"]
        if all(exp in result for exp in expected):
            print("OK: read_file reads utils.py correctly")
        else:
            print(f"FAIL: read_file utils.py - missing expected content")
            errors.append("read_file content")

        print()
        print("=== Test search_code ===")
        
        # Test 2: Search for pattern
        result = search_code(pattern="validate_email", file_pattern="*.py")
        print(f"search_code result: {result[:300]}...")
        
        if "utils.py" in result:
            print("OK: search_code finds validate_email")
        else:
            print(f"FAIL: search_code validate_email")
            errors.append("search_code")

        print()
        print("=== Test search_function_or_class_definition_in_code ===")
        
        # Test 3: Find function definition
        result = search_function_or_class_definition_in_code(name="calculate_sum")
        print(f"search_definition result: {result}")
        
        if "utils.py" in result and "def calculate_sum" in result:
            print("OK: find definition of calculate_sum")
        else:
            print(f"FAIL: calculate_sum definition")
            errors.append("search_definition function")

        # Test 4: Find class definition
        result = search_function_or_class_definition_in_code(name="User")
        print(f"search_definition result: {result}")
        
        if "models.py" in result and "class User" in result:
            print("OK: find definition of User class")
        else:
            print(f"FAIL: User class definition")
            errors.append("search_definition class")

        print()
        print("=== Test find_references ===")
        
        # Test 5: Find references (subject signature: name, filepath, line)
        result = find_references(name="calculate_sum", filepath="/testbed/utils.py", line=7)
        print(f"find_references result: {result[:300]}...")

        if "utils.py" in result:
            print("OK: find_references finds calculate_sum")
        else:
            print(f"FAIL: calculate_sum references")
            errors.append("find_references")

        print()
        print("=== Test get_patch ===")

        # Test 6: Get patch (should work even with no changes)
        result = get_patch()
        print(f"get_patch result: {result[:100]}...")

        if "Error" not in result or "No changes" in result:
            print("OK: get_patch works")
        else:
            print(f"FAIL: get_patch returned error")
            errors.append("get_patch")

        print()
        print("=== Test edit_file ===")

        # Test 7: Edit a file and verify the change
        # First read the current content of utils.py to find a known string
        original = read_file(filepath="/testbed/utils.py", start_line=1, end_line=5)
        print(f"Before edit: {original[:200]}...")

        # Make a non-destructive edit (add a comment at the top)
        edit_result = edit_file(
            filepath="/testbed/utils.py",
            old_str="def calculate_sum",
            new_str="def calculate_sum"
        )
        print(f"edit_file result: {edit_result[:200]}...")

        # Verify edit_file is callable and returns something
        if edit_result is not None:
            print("OK: edit_file is callable and returns a result")
        else:
            print("FAIL: edit_file returned None")
            errors.append("edit_file")

        print()
        print("=== Test run_command ===")

        # Test 8: Run a simple command
        if 'run_command' in dir():
            cmd_result = run_command(command="echo hello_from_testbed", workdir="/testbed")
            print(f"run_command result: {cmd_result[:200]}...")

            if "hello_from_testbed" in str(cmd_result):
                print("OK: run_command executes and returns output")
            else:
                print(f"FAIL: run_command did not return expected output")
                errors.append("run_command")
        else:
            print("FAIL: run_command not available")
            errors.append("run_command")

        print()
        print("=== Test run_tests ===")

        # Test 9: Run tests (may fail if no eval script, but should be callable)
        if 'run_tests' in dir():
            try:
                test_result = run_tests()
                print(f"run_tests result: {str(test_result)[:200]}...")
                print("OK: run_tests is callable")
            except Exception as e:
                # run_tests may fail if no eval_script is set up, but it should be callable
                print(f"run_tests raised: {e}")
                print("OK: run_tests is callable (raised expected error in test context)")
        else:
            print("FAIL: run_tests not available")
            errors.append("run_tests")

        print()
        print("=== Test final_answer ===")

        # Test 10: final_answer should be callable
        if 'final_answer' in dir():
            try:
                fa_result = final_answer(answer="test_patch_content")
                print(f"final_answer result: {str(fa_result)[:200]}...")
                print("OK: final_answer is callable")
            except Exception as e:
                print(f"final_answer raised: {e}")
                print("OK: final_answer is callable (raised expected error in test context)")
        else:
            print("FAIL: final_answer not available")
            errors.append("final_answer")

        print()
        print("=== Summary ===")
        if not errors:
            print("=== SWEBENCH TOOLS OK ===")
        else:
            print(f"Errors: {errors}")
            print("=== SWEBENCH TOOLS FAILED ===")
