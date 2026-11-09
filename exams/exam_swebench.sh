#!/bin/bash
# SWE-bench Examination Script
# Usage: ./exam_swebench.sh --student-path PATH --moulinette-path PATH --env-file PATH
# Pass criteria: 2 out of 3 randomly selected tasks (from pool of 6)

set -e

# --- Argument parsing ---
STUDENT_PATH=""
MOULINETTE_PATH=""
ENV_FILE=""
MODEL=""
BACKEND=""

usage() {
    echo "Usage: $0 --student-path PATH --moulinette-path PATH --env-file PATH [--model-name MODEL] [--provider-url URL]"
    echo ""
    echo "Required arguments:"
    echo "  --student-path PATH       Path to student code directory"
    echo "  --moulinette-path PATH    Path to moulinette directory"
    echo "  --env-file PATH           Path to .env file with API keys"
    echo ""
    echo "Optional arguments:"
    echo "  --model-name MODEL        Model name (forwarded to agent)"
    echo "  --provider-url URL        LLM provider API URL (forwarded to agent)"
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
        --model-name)
            MODEL="$2"
            shift 2
            ;;
        --provider-url)
            BACKEND="$2"
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
DATETIME=$(date +"%Y-%m-%d_%H-%M-%S")
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EVAL_DIR="$PROJECT_DIR/evaluations/swebench/$DATETIME"
PASSED=0
PASS_THRESHOLD=2
CLEANUP_FAILED=0
SELECT_COUNT=3
SWEBENCH_TIME_LIMIT=900  # seconds; enforced by `moulinette run-agent`, not just checked after the fact

# Select random tasks from the exam pool via moulinette
echo "Selecting $SELECT_COUNT random tasks from exam pool..."
cd "$MOULINETTE_PATH"
SELECT_OUTPUT=$(uv run moulinette_eval select swebench --count "$SELECT_COUNT" 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "Error: Failed to select tasks from exam pool"
    exit 1
fi

# Parse instance IDs from JSON output
INSTANCE_IDS=()
while IFS= read -r id; do
    INSTANCE_IDS+=("$id")
done < <(echo "$SELECT_OUTPUT" | python3 -c "import sys,json; [print(x) for x in json.load(sys.stdin)['instance_ids']]")
TOTAL=${#INSTANCE_IDS[@]}

if [ "$TOTAL" -eq 0 ]; then
    echo "Error: No tasks selected"
    exit 1
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}==============================================${NC}"
echo -e "${YELLOW}SWE-BENCH EXAMINATION${NC}"
echo -e "${YELLOW}==============================================${NC}"
echo "Student path: $STUDENT_PATH"
echo "Moulinette path: $MOULINETTE_PATH"
echo "Env file: $ENV_FILE"
echo "Eval directory: $EVAL_DIR"
echo "Tasks: $TOTAL (randomly selected from pool of 6)"
echo "Pass threshold: $PASS_THRESHOLD/$TOTAL"
echo "Selected tasks:"
for id in "${INSTANCE_IDS[@]}"; do
    echo "  - $id"
done
[ -n "$MODEL" ] && echo "Model: $MODEL"
[ -n "$BACKEND" ] && echo "Backend: $BACKEND"
echo -e "${YELLOW}==============================================${NC}"

mkdir -p "$EVAL_DIR"

# Load environment variables from .env file
set -a
source "$ENV_FILE"
set +a

# Build optional model arguments to forward to agent
MODEL_ARGS=""
[ -n "$MODEL" ] && MODEL_ARGS="$MODEL_ARGS --model-name $MODEL"
[ -n "$BACKEND" ] && MODEL_ARGS="$MODEL_ARGS --provider-url $BACKEND"

# Function to count running swebench containers
count_swebench_containers() {
    local count
    count=$(docker ps --format '{{.Image}}' 2>/dev/null | grep -c "sweb.eval") || true
    echo "${count:-0}"
}

# Purge any sweb.eval containers left running from a previous session (e.g. one that
# got stuck before the per-task cleanup below could run). The per-task cleanup further
# down only reacts to containers created *during* the current task, so it wouldn't
# catch leftovers from before this script started.
STALE_CONTAINERS=$(docker ps --format '{{.ID}} {{.Image}}' 2>/dev/null | grep "sweb.eval" | awk '{print $1}') || true
if [ -n "$STALE_CONTAINERS" ]; then
    echo -e "${YELLOW}Found stale sweb.eval container(s) from a previous run, cleaning up...${NC}"
    echo "$STALE_CONTAINERS" | xargs -r docker stop 2>/dev/null || true
    echo "$STALE_CONTAINERS" | xargs -r docker rm 2>/dev/null || true
fi

# Defense-in-depth: even though `moulinette run-agent` now kills a hanging agent by
# itself, cap the whole script's wall-clock time so an unforeseen stall elsewhere
# (dump/validate calls, moulinette itself) can't still block the exam indefinitely.
SCRIPT_DEADLINE=$(( $(date +%s) + TOTAL * (SWEBENCH_TIME_LIMIT + 300) ))

for i in $(seq 0 $((TOTAL - 1))); do
    if [ "$(date +%s)" -ge "$SCRIPT_DEADLINE" ]; then
        echo -e "${RED}Aborting: script exceeded its overall time budget, remaining tasks marked as not run.${NC}"
        break
    fi

    INSTANCE_ID="${INSTANCE_IDS[$i]}"
    TASK_NUM=$((i + 1))

    echo ""
    echo -e "${YELLOW}--- Task $TASK_NUM/$TOTAL ($INSTANCE_ID) ---${NC}"

    # Count containers before
    CONTAINERS_BEFORE=$(count_swebench_containers)

    # Dump specific task
    echo "Dumping task..."
    TEMP_TASK=$(mktemp --suffix=.json)
    cd "$MOULINETTE_PATH"
    uv run moulinette_eval dump swebench --task-id "$INSTANCE_ID" --output "$TEMP_TASK"

    DOCKER_IMAGE=$(cat "$TEMP_TASK" | python3 -c "import sys,json; print(json.load(sys.stdin)['docker_image'])")
    echo "Docker image: $DOCKER_IMAGE"

    # Create task directory (use instance_id, replace / with __)
    SAFE_INSTANCE_ID=$(echo "$INSTANCE_ID" | tr '/' '__')
    TASK_DIR="$EVAL_DIR/$SAFE_INSTANCE_ID"
    mkdir -p "$TASK_DIR"
    cp "$TEMP_TASK" "$TASK_DIR/task.json"
    rm -f "$TEMP_TASK"

    TASK_FILE="$TASK_DIR/task.json"
    SOLUTION_FILE="$TASK_DIR/solution.json"

    # Run student solution with separate stdout/stderr capture. The agent is launched
    # through `moulinette run-agent`, which enforces SWEBENCH_TIME_LIMIT as a hard
    # OS-level timeout (kills the agent's whole process group) instead of only measuring
    # its duration after it returns — an agent that hangs no longer stalls the whole exam.
    echo "Running student solution..."
    cd "$STUDENT_PATH"
    AGENT_CMD="uv run python -m agent_swebench --task-file $TASK_FILE --output $SOLUTION_FILE $MODEL_ARGS"
    AGENT_START=$(date +%s)
    AGENT_EXIT=0
    uv run --project "$MOULINETTE_PATH" moulinette_eval run-agent "$SWEBENCH_TIME_LIMIT" "$AGENT_CMD" \
        > "$TASK_DIR/stdout.log" 2> "$TASK_DIR/stderr.log" \
        || AGENT_EXIT=$?
    AGENT_END=$(date +%s)
    AGENT_DURATION=$((AGENT_END - AGENT_START))
    echo "Agent duration: ${AGENT_DURATION}s"
    # A valid solution.json means the agent ran, whether or not it solved the task.
    if [ -s "$SOLUTION_FILE" ] && python3 -c "import json; json.load(open('$SOLUTION_FILE'))" 2>/dev/null; then
        EXEC_SUCCESS=1
    else
        EXEC_SUCCESS=0
    fi

    if [ "$AGENT_EXIT" -eq 124 ]; then
        echo -e "${RED}FAILED: Agent exceeded time limit (${SWEBENCH_TIME_LIMIT}s) — killed${NC}"
        echo "TIME_LIMIT: EXCEEDED (killed after ${SWEBENCH_TIME_LIMIT}s)" >> "$TASK_DIR/stdout.log"
        echo "RESULT: FAILED (time limit)" >> "$TASK_DIR/stdout.log"
    elif [ $EXEC_SUCCESS -eq 1 ]; then
        echo "TIME_LIMIT: OK (${AGENT_DURATION}s <= ${SWEBENCH_TIME_LIMIT}s)" >> "$TASK_DIR/stdout.log"
        # Validate
        cd "$MOULINETTE_PATH"
        echo "Validating solution..."
        VALIDATE_OUTPUT=$(uv run moulinette_eval validate swebench "$TASK_FILE" "$SOLUTION_FILE" 2>&1) && VALIDATE_SUCCESS=1 || VALIDATE_SUCCESS=0
        echo "$VALIDATE_OUTPUT" >> "$TASK_DIR/stdout.log"

        if [ $VALIDATE_SUCCESS -eq 1 ]; then
            echo -e "Result: ${GREEN}PASSED${NC}"
            echo "RESULT: PASSED" >> "$TASK_DIR/stdout.log"
            ((PASSED++)) || true
        else
            echo -e "Result: ${RED}FAILED (validation)${NC}"
            echo "RESULT: FAILED (validation)" >> "$TASK_DIR/stdout.log"
        fi
    else
        echo "TIME_LIMIT: OK (${AGENT_DURATION}s <= ${SWEBENCH_TIME_LIMIT}s)" >> "$TASK_DIR/stdout.log"
        echo -e "Result: ${RED}FAILED (execution)${NC}"
        echo "RESULT: FAILED (execution)" >> "$TASK_DIR/stderr.log"
        # Show last few lines of error
        grep -E "(Error|Exception|Traceback)" "$TASK_DIR/stderr.log" | tail -3 | sed 's/^/  /' || true
    fi

    # Check container cleanup
    CONTAINERS_AFTER=$(count_swebench_containers)
    if [ "$CONTAINERS_AFTER" -gt "$CONTAINERS_BEFORE" ]; then
        echo -e "${YELLOW}WARNING: Container not cleaned up! ($CONTAINERS_AFTER > $CONTAINERS_BEFORE)${NC}"
        echo "CLEANUP: FAILED" >> "$TASK_DIR/stdout.log"
        CLEANUP_FAILED=1
        # Clean up orphaned containers
        docker ps -q --filter ancestor="$DOCKER_IMAGE" | xargs -r docker stop 2>/dev/null || true
        docker ps -aq --filter ancestor="$DOCKER_IMAGE" | xargs -r docker rm 2>/dev/null || true
    else
        echo "Container cleanup: OK"
        echo "CLEANUP: OK" >> "$TASK_DIR/stdout.log"
    fi
done

echo ""
echo -e "${YELLOW}==============================================${NC}"
echo -e "${YELLOW}FINAL RESULT: $PASSED/$TOTAL${NC}"
echo -e "${YELLOW}==============================================${NC}"
echo "Results saved to: $EVAL_DIR"

if [ $CLEANUP_FAILED -eq 1 ]; then
    echo -e "${YELLOW}WARNING: Container cleanup test FAILED${NC}"
    echo "Student must ensure containers are stopped even on crash"
fi

echo ""
echo "To inspect results:"
echo "  cd moulinette && uv run moulinette_eval display ../\$SOLUTION_FILE"
echo ""

if [ $PASSED -ge $PASS_THRESHOLD ] && [ $CLEANUP_FAILED -eq 0 ]; then
    echo -e "${GREEN}STATUS: PASS${NC}"
    exit 0
else
    echo -e "${RED}STATUS: FAIL${NC}"
    exit 1
fi
