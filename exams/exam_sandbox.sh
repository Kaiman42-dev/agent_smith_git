#!/bin/bash
# Sandbox Examination Script
# Usage: ./exam_sandbox.sh --student-path PATH --moulinette-path PATH --env-file PATH
# Tests student sandbox implementation with MCP-based tools

set -e

# --- Argument parsing ---
STUDENT_PATH=""
MOULINETTE_PATH=""
ENV_FILE=""

usage() {
    echo "Usage: $0 --student-path PATH --moulinette-path PATH --env-file PATH"
    echo ""
    echo "Required arguments:"
    echo "  --student-path PATH       Path to student code directory"
    echo "  --moulinette-path PATH    Path to moulinette directory"
    echo "  --env-file PATH           Path to .env file with API keys"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --student-path)
            STUDENT_PATH="$2"
            shift 2
            ;;
        --moulinette-path)
            MOULINETTE_PATH="$2"
            shift 2
            ;;
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        *)
            echo "Error: Unknown argument: $1"
            usage
            ;;
    esac
done

# Validate required arguments
if [ -z "$STUDENT_PATH" ] || [ -z "$MOULINETTE_PATH" ] || [ -z "$ENV_FILE" ]; then
    echo "Error: All three arguments are required."
    usage
fi

if [ ! -d "$STUDENT_PATH" ]; then
    echo "Error: Student path is not a directory: $STUDENT_PATH"
    exit 1
fi

if [ ! -d "$MOULINETTE_PATH" ]; then
    echo "Error: Moulinette path is not a directory: $MOULINETTE_PATH"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found: $ENV_FILE"
    exit 1
fi

# Resolve to absolute paths
STUDENT_PATH="$(cd "$STUDENT_PATH" && pwd)"
MOULINETTE_PATH="$(cd "$MOULINETTE_PATH" && pwd)"
ENV_FILE="$(cd "$(dirname "$ENV_FILE")" && pwd)/$(basename "$ENV_FILE")"

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TESTS_PATH="$SCRIPT_DIR/sandbox_tests"
SANDBOX_CONFIG="$TESTS_PATH/sandbox_config.json"
SANDBOX_CONFIG_SWEBENCH="$TESTS_PATH/sandbox_config_swebench.json"
SANDBOX_CONFIG_RESOURCES="$TESTS_PATH/sandbox_config_resources.json"
DATETIME=$(date +"%Y-%m-%d_%H-%M-%S")
EVAL_DIR="$PROJECT_DIR/evaluations/sandbox/$DATETIME"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

TESTS_PASSED=0
TESTS_FAILED=0

echo -e "${YELLOW}============================================================${NC}"
echo -e "${YELLOW}SANDBOX EXAMINATION${NC}"
echo -e "${YELLOW}============================================================${NC}"
echo "Student path: $STUDENT_PATH"
echo "Moulinette path: $MOULINETTE_PATH"
echo "Env file: $ENV_FILE"
echo "Eval directory: $EVAL_DIR"
echo "Sandbox config: $SANDBOX_CONFIG"
echo "Sandbox config (swebench): $SANDBOX_CONFIG_SWEBENCH"
echo "Sandbox config (resources): $SANDBOX_CONFIG_RESOURCES"
echo ""

mkdir -p "$EVAL_DIR"

# Load environment variables from .env file
set -a
source "$ENV_FILE"
set +a

# Go to student path
cd "$STUDENT_PATH"

# Helper function to run a test
run_test() {
    local TEST_NAME="$1"
    local TEST_CMD="$2"
    local PASS_PATTERN="$3"

    local TEST_DIR="$EVAL_DIR/$TEST_NAME"
    mkdir -p "$TEST_DIR"

    echo -e "${YELLOW}Running: $TEST_NAME${NC}"
    eval "$TEST_CMD" > "$TEST_DIR/stdout.log" 2> "$TEST_DIR/stderr.log" && true
    local EXIT_CODE=$?

    # Check pass pattern against combined output
    if grep -q "$PASS_PATTERN" "$TEST_DIR/stdout.log" "$TEST_DIR/stderr.log" 2>/dev/null; then
        echo -e "  Result: ${GREEN}PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "  Result: ${RED}FAIL${NC}"
        tail -10 "$TEST_DIR/stderr.log" 2>/dev/null | sed 's/^/    /'
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    echo ""
}

# Test 1: Allowed imports
run_test "allowed_imports" \
    "cat '$TESTS_PATH/test_imports_allowed.py' | uv run sandbox '$SANDBOX_CONFIG'" \
    "=== .* OK ==="

# Test 2: Blocked imports
run_test "blocked_imports" \
    "cat '$TESTS_PATH/test_imports_blocked.py' | uv run sandbox '$SANDBOX_CONFIG'" \
    "=== .* COMPLETE ==="

# Test 3: File access
run_test "file_access" \
    "cat '$TESTS_PATH/test_file_access.py' | uv run sandbox '$SANDBOX_CONFIG'" \
    "=== .* COMPLETE ==="

# Test 4: Builtins blocked
run_test "builtins_blocked" \
    "cat '$TESTS_PATH/test_builtins_blocked.py' | uv run sandbox '$SANDBOX_CONFIG'" \
    "=== .* COMPLETE ==="

# Test 5: Network blocked
run_test "network_blocked" \
    "cat '$TESTS_PATH/test_network_blocked.py' | uv run sandbox '$SANDBOX_CONFIG'" \
    "=== .* COMPLETE ==="

# Test 6: MBPP tools via MCP
run_test "mbpp_tools" \
    "cat '$TESTS_PATH/test_mbpp_tools.py' | uv run sandbox '$SANDBOX_CONFIG' --mcp-stdio 'python mcp_tools_mbpp.py'" \
    "=== .* OK ==="

# Test 7: SWE-bench tools via MCP (with testbed directory)
# Init a temporary git repo in the testbed so get_patch works in isolation
# (in real evaluation, the testbed is a separate Docker container with its own repo)
export TESTBED_PATH="$TESTS_PATH/testbed"
# Clean up any leftover .git from a previous run
rm -rf "$TESTBED_PATH/.git" 2>/dev/null || true
git init "$TESTBED_PATH" > /dev/null 2>&1
git -C "$TESTBED_PATH" add -A > /dev/null 2>&1
git -C "$TESTBED_PATH" commit -m "init" > /dev/null 2>&1
run_test "swebench_tools" \
    "cat '$TESTS_PATH/test_swebench_tools.py' | uv run sandbox '$SANDBOX_CONFIG_SWEBENCH' --mcp-stdio 'python mcp_tools_swebench.py'" \
    "=== .* OK ==="
# Clean up temporary git repo
rm -rf "$TESTBED_PATH/.git" 2>/dev/null || true
unset TESTBED_PATH

# Test 8: MCP HTTP connection
TEST_DIR_HTTP="$EVAL_DIR/mcp_http"
mkdir -p "$TEST_DIR_HTTP"
echo -e "${YELLOW}Running: MCP HTTP Connection${NC}"
uv run --directory "$MOULINETTE_PATH" python "$TESTS_PATH/simple_mcp_server.py" --http --port 18080 > "$TEST_DIR_HTTP/server.log" 2>&1 &
MCP_PID=$!
sleep 2  # Give HTTP server time to start
cat "$TESTS_PATH/test_mcp_http.py" | timeout 15 uv run sandbox "$SANDBOX_CONFIG" --mcp-server http://localhost:18080/mcp \
    > "$TEST_DIR_HTTP/stdout.log" 2> "$TEST_DIR_HTTP/stderr.log" || true
kill $MCP_PID 2>/dev/null || true
if grep -q "=== .* OK ===" "$TEST_DIR_HTTP/stdout.log" "$TEST_DIR_HTTP/stderr.log" 2>/dev/null; then
    echo -e "  Result: ${GREEN}PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "  Result: ${RED}FAIL${NC}"
    tail -10 "$TEST_DIR_HTTP/stderr.log" 2>/dev/null | sed 's/^/    /'
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
echo ""

# Test 9: MCP stdio connection
run_test "mcp_stdio" \
    "cat '$TESTS_PATH/test_mcp_stdio.py' | uv run sandbox '$SANDBOX_CONFIG' --mcp-stdio 'python $TESTS_PATH/simple_mcp_server.py --stdio'" \
    "=== .* OK ==="

# Test 10: Timeout enforcement
run_test "timeout" \
    "cat '$TESTS_PATH/test_timeout.py' | uv run sandbox '$SANDBOX_CONFIG_RESOURCES'" \
    "=== .* COMPLETE ==="

# Test 11: Memory enforcement
run_test "memory" \
    "cat '$TESTS_PATH/test_memory.py' | uv run sandbox '$SANDBOX_CONFIG_RESOURCES'" \
    "=== .* COMPLETE ==="

# Test 12: Dynamic MCP tool discovery
run_test "dynamic_discovery" \
    "cat '$TESTS_PATH/test_dynamic_discovery.py' | uv run sandbox '$SANDBOX_CONFIG' --mcp-stdio 'python $TESTS_PATH/simple_mcp_server.py --stdio'" \
    "=== .* OK ==="

# Test 13: Sandbox manual generation
run_test "sandbox_manual" \
    "cat '$TESTS_PATH/test_sandbox_manual.py' | uv run sandbox '$SANDBOX_CONFIG' --mcp-stdio 'python $TESTS_PATH/simple_mcp_server.py --stdio'" \
    "=== .* OK ==="

# Test 14: Sandbox feedback transparency
run_test "sandbox_feedback" \
    "cat '$TESTS_PATH/test_sandbox_feedback.py' | uv run sandbox '$SANDBOX_CONFIG'" \
    "=== .* COMPLETE ==="

# Test 15 (Bonus): Layer 1 bonus (subprocess isolation)
# This test does NOT count toward pass/fail.
LAYER1_BONUS="SKIP"
TEST_DIR_BONUS="$EVAL_DIR/layer1_bonus"
mkdir -p "$TEST_DIR_BONUS"
echo -e "${YELLOW}Running: Layer 1 Bonus (bare-except bypass resistance)${NC}"
echo -e "  (This is a bonus test - does not count toward pass/fail)"
timeout 15 bash -c "cat '$TESTS_PATH/test_layer1_bonus.py' | uv run sandbox '$SANDBOX_CONFIG_RESOURCES'" \
    > "$TEST_DIR_BONUS/stdout.log" 2> "$TEST_DIR_BONUS/stderr.log" || true
BONUS_OUTPUT=$(cat "$TEST_DIR_BONUS/stdout.log" "$TEST_DIR_BONUS/stderr.log" 2>/dev/null)
if echo "$BONUS_OUTPUT" | grep -q "=== .* COMPLETE ==="; then
    if echo "$BONUS_OUTPUT" | grep -q "WARN:"; then
        echo -e "  Result: ${YELLOW}PARTIAL${NC} (layer 0 only - timeout bypass detected)"
        LAYER1_BONUS="PARTIAL"
    else
        echo -e "  Result: ${GREEN}BONUS PASS${NC} (layer 1 subprocess isolation working)"
        LAYER1_BONUS="PASS"
    fi
else
    echo -e "  Result: ${YELLOW}SKIP${NC} (process hung or timed out - layer 0 behavior)"
    LAYER1_BONUS="SKIP"
fi
echo ""

# Summary
echo -e "${YELLOW}============================================================${NC}"
echo -e "${YELLOW}SUMMARY${NC}"
echo -e "${YELLOW}============================================================${NC}"
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"
echo -e "Layer 1 bonus: ${YELLOW}$LAYER1_BONUS${NC}"
echo "Results saved to: $EVAL_DIR"

echo ""
echo "To inspect individual test results:"
echo "  cat $EVAL_DIR/<test_name>/stdout.log"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "\n${GREEN}ALL TESTS PASSED${NC}"
    echo "STATUS: PASS"
    exit 0
else
    echo -e "\n${RED}SOME TESTS FAILED${NC}"
    echo "STATUS: FAIL"
    exit 1
fi
