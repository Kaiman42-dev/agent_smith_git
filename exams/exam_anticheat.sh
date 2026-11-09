#!/bin/bash
# ABOUTME: Automated anti-cheat checks on student codebase.
# ABOUTME: Searches for suspicious patterns that indicate solution lookup rather than legitimate solving.

set -e

# --- Argument parsing ---
STUDENT_PATH=""

usage() {
    echo "Usage: $0 --student-path PATH"
    echo ""
    echo "Required arguments:"
    echo "  --student-path PATH       Path to student code directory"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --student-path)
            STUDENT_PATH="$2"
            shift 2
            ;;
        *)
            echo "Error: Unknown argument: $1"
            usage
            ;;
    esac
done

if [ -z "$STUDENT_PATH" ]; then
    echo "Error: --student-path is required."
    usage
fi

if [ ! -d "$STUDENT_PATH" ]; then
    echo "Error: Student path is not a directory: $STUDENT_PATH"
    exit 1
fi

# Resolve to absolute path
STUDENT_PATH="$(cd "$STUDENT_PATH" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

CHECKS_PASSED=0
CHECKS_WARNED=0
TOTAL_CHECKS=6

echo -e "${YELLOW}============================================================${NC}"
echo -e "${YELLOW}ANTI-CHEAT CHECKS${NC}"
echo -e "${YELLOW}============================================================${NC}"
echo "Student path: $STUDENT_PATH"
echo ""

# Helper: run a check and report pass/warn
run_check() {
    local CHECK_NAME="$1"
    local CHECK_DESC="$2"
    local MATCHES="$3"

    echo -e "${YELLOW}Check: $CHECK_NAME${NC}"
    echo "  $CHECK_DESC"

    if [ -z "$MATCHES" ]; then
        echo -e "  Result: ${GREEN}PASS${NC} (no suspicious matches)"
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
    else
        echo -e "  Result: ${RED}WARNING${NC} — review these matches:"
        echo "$MATCHES" | sed 's/^/    /'
        CHECKS_WARNED=$((CHECKS_WARNED + 1))
    fi
    echo ""
}

# --- Check 1: GitHub URL detection ---
MATCHES=$(grep -rn --exclude-dir='.*' "github.com" "$STUDENT_PATH/" --include="*.py" | grep -v "import\|#\|swebench.com" || true)
run_check "GitHub URLs" \
    "Detects references to github.com in Python source (excluding imports and comments)" \
    "$MATCHES"

# --- Check 2: PR/issue/commit references in prompts ---
MATCHES=$(grep -rn --exclude-dir='.*' "pull\|PR\|issue\|commit" "$STUDENT_PATH/" --include="*.py" | grep -i "prompt\|system\|message" || true)
run_check "PR/Issue references in prompts" \
    "Detects PR, issue, or commit mentions near prompt/system/message strings" \
    "$MATCHES"

# --- Check 3: HTTP requests to code-hosting platforms (not the LLM API itself) ---
MATCHES=$(grep -rn --exclude-dir='.*' "requests\.get\|urllib\|httpx" "$STUDENT_PATH/" --include="*.py" | grep -iE "github\.com|gitlab\.com|bitbucket\.org|gist\.github" || true)
run_check "External HTTP requests" \
    "Detects HTTP client usage targeting a code-hosting platform (vs. the LLM provider)" \
    "$MATCHES"

# --- Check 4: SWE-bench dataset access (gold patches) ---
MATCHES=$(grep -rnE --exclude-dir='.*' "gold_patch|FAIL_TO_PASS|PASS_TO_PASS|^\s*(import|from)\s+swebench\b|load_dataset\(.*SWE-bench" "$STUDENT_PATH/" --include="*.py" || true)
run_check "SWE-bench dataset access" \
    "Detects direct access to SWE-bench dataset or gold patches" \
    "$MATCHES"

# --- Check 5: Git history mining in prompts ---
MATCHES=$(grep -rn --exclude-dir='.*' "git log\|git show\|git diff.*HEAD" "$STUDENT_PATH/" --include="*.py" | grep -i "prompt\|system\|message" || true)
run_check "Git history mining in prompts" \
    "Detects git history commands embedded in prompt/system/message strings" \
    "$MATCHES"

# --- Check 6: Forbidden orchestration libraries ---
MATCHES=$(grep -rn --exclude-dir='.*' "llama.index\|smolagents\|langgraph\|crewai\|autogen" "$STUDENT_PATH/" --include="*.py" || true)
run_check "Forbidden orchestration libraries" \
    "Detects usage of banned agent orchestration libraries" \
    "$MATCHES"

# --- Summary ---
echo -e "${YELLOW}============================================================${NC}"
echo -e "${YELLOW}SUMMARY${NC}"
echo -e "${YELLOW}============================================================${NC}"
echo -e "Checks passed: ${GREEN}$CHECKS_PASSED${NC} / $TOTAL_CHECKS"
echo -e "Checks warned: ${RED}$CHECKS_WARNED${NC} / $TOTAL_CHECKS"

if [ $CHECKS_WARNED -eq 0 ]; then
    echo -e "\n${GREEN}ALL CHECKS PASSED${NC}"
    echo "STATUS: PASS"
    exit 0
else
    echo -e "\n${RED}$CHECKS_WARNED CHECK(S) NEED MANUAL REVIEW${NC}"
    echo "STATUS: REVIEW"
    echo "Investigate the flagged matches above with the student."
    exit 1
fi
