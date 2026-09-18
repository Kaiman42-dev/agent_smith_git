#!/bin/bash
# Runs dump -> run-agent -> validate for one task. Usage: ./quickstart.sh mbpp|swebench [options]
set -e

BENCHMARK="${1:-}"
shift || true

STUDENT_PATH="../student"
CACHE_DIR="../cache"
TASK_ID=""
SEED=""
MODEL=""
BACKEND=""

usage() {
    echo "Usage: $0 mbpp|swebench [options]"
    echo ""
    echo "Options:"
    echo "  --student-path PATH   Path to your agent project (default: ../student)"
    echo "  --cache-dir PATH      Where task.json/solution.json are written (default: ../cache)"
    echo "  --task-id ID          Dump a specific task instead of a random one"
    echo "  --seed N              Seed for random task selection"
    echo "  --model-name MODEL    Forwarded to your agent"
    echo "  --provider-url URL    Forwarded to your agent"
    exit 1
}

if [ "$BENCHMARK" != "mbpp" ] && [ "$BENCHMARK" != "swebench" ]; then
    usage
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --student-path) STUDENT_PATH="$2"; shift 2 ;;
        --cache-dir) CACHE_DIR="$2"; shift 2 ;;
        --task-id) TASK_ID="$2"; shift 2 ;;
        --seed) SEED="$2"; shift 2 ;;
        --model-name) MODEL="$2"; shift 2 ;;
        --provider-url) BACKEND="$2"; shift 2 ;;
        *) echo "Error: unknown argument: $1"; usage ;;
    esac
done

if [ ! -d "$STUDENT_PATH" ]; then
    echo "Error: student path is not a directory: $STUDENT_PATH"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STUDENT_PATH="$(cd "$STUDENT_PATH" && pwd)"
mkdir -p "$CACHE_DIR"
CACHE_DIR="$(cd "$CACHE_DIR" && pwd)"

TASK_FILE="$CACHE_DIR/${BENCHMARK}_task.json"
SOLUTION_FILE="$CACHE_DIR/${BENCHMARK}_solution.json"

if [ "$BENCHMARK" = "mbpp" ]; then
    TIME_LIMIT=120
else
    TIME_LIMIT=900
fi

DUMP_ARGS=""
[ -n "$TASK_ID" ] && DUMP_ARGS="$DUMP_ARGS --task-id $TASK_ID"
[ -n "$SEED" ] && DUMP_ARGS="$DUMP_ARGS --seed $SEED"

MODEL_ARGS=""
[ -n "$MODEL" ] && MODEL_ARGS="$MODEL_ARGS --model-name $MODEL"
[ -n "$BACKEND" ] && MODEL_ARGS="$MODEL_ARGS --provider-url $BACKEND"

echo "--- 1/3 dump ---"
cd "$SCRIPT_DIR"
uv run moulinette_eval dump "$BENCHMARK" $DUMP_ARGS --output "$TASK_FILE"

echo ""
echo "--- 2/3 run your agent (timeout ${TIME_LIMIT}s) ---"
cd "$STUDENT_PATH"
AGENT_CMD="uv run python -m agent_$BENCHMARK --task-file $TASK_FILE --output $SOLUTION_FILE $MODEL_ARGS"
uv run --project "$SCRIPT_DIR" moulinette_eval run-agent "$TIME_LIMIT" "$AGENT_CMD"

echo ""
echo "--- 3/3 validate ---"
cd "$SCRIPT_DIR"
uv run moulinette_eval validate "$BENCHMARK" "$TASK_FILE" "$SOLUTION_FILE"
