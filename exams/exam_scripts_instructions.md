# Exam Scripts Instructions — Corrector Guide

This document explains how to use the exam scripts during correction of
Project 3: Agent Smith. All exam scripts are located in the `exams/` directory.

---

## Prerequisites

Before running any exam script:

1. **Docker must be running** (required for SWE-bench):
   ```bash
   docker info  # Should not error
   ```

2. **Install dependencies** in both student and moulinette directories:
   ```bash
   cd student && uv sync
   cd ../moulinette && uv sync
   ```

3. **Create a .env file** with API keys:
   ```bash
   # Example .env file
   OPENROUTER_API_KEY=sk-or-...
   ```

4. **Verify student code** does not import moulinette packages:
   ```bash
   grep -rn "moulinette" student/ --include="*.py"
   ```

---

## Recommended Correction Flow

The scale is designed so long-running tasks run in the background while
you inspect code. Follow this flow:

1. **Q1**: Set up API keys (generate live, load .env)
2. **Q2**: Launch MBPP + SWE-bench in two background terminals
3. **Q3-Q7**: Inspect CLI, models, sandbox, MCP while agents run
4. **Q8**: Check MBPP results (~5 min after launch)
5. **Q9**: Inspect metrics from MBPP solution.json
6. **Q10**: Execution trace spot-check (live modifications)
7. **Q11**: Anti-cheat checks (run `exam_anticheat.sh` + inspect solution)
8. **Q12/Q12b**: Check benchmark report and its depth
9. **Q13**: Docker lifecycle (use SWE-bench run for cleanup test)
10. **Q14/Q14b**: Check SWE-bench results and agent excellence (~45 min after launch)

---

## Exam Scripts Overview

| Script | Tests | Pass Criteria | Duration |
|--------|-------|---------------|----------|
| `exam_sandbox.sh` | Sandbox security, MCP, resources | All tests pass | ~2 min |
| `exam_mbpp.sh` | MBPP agent (5 random tasks) | 4/5 pass | ~5 min |
| `exam_swebench.sh` | SWE-bench agent (3 random from 6) | 2/3 pass | ~45 min |
| `exam_anticheat.sh` | Codebase anti-cheat grep checks | No warnings | ~10 sec |

All scripts are run from the project root directory:
```bash
./exams/exam_<type>.sh --student-path ./student --moulinette-path ./moulinette --env-file .env
```

The anti-cheat script only needs `--student-path`:
```bash
./exams/exam_anticheat.sh --student-path ./student
```

---

## 1. Sandbox Exam (`exams/exam_sandbox.sh`)

### What it tests

| Test # | Name | What it verifies |
|--------|------|-----------------|
| 1 | Allowed imports | math, json, re, collections, etc. work |
| 2 | Blocked imports | os, subprocess, sys, socket, etc. blocked |
| 3 | File access | /etc/passwd blocked, path traversal blocked |
| 4 | Builtins blocked | eval, exec, compile are blocked |
| 5 | Network blocked | socket, urllib, http, requests connections blocked |
| 6 | MBPP tools (MCP) | run_tests works via MCP stdio |
| 7 | SWE-bench tools (MCP) | All mandatory tools available and functional |
| 8 | MCP HTTP | HTTP (streamable-http) transport works |
| 9 | MCP stdio | stdio transport works with external server |
| 10 | Timeout | Code exceeding timeout is interrupted |
| 11 | Memory | Code exceeding memory limit is interrupted |
| 12 | Dynamic discovery | MCP tools auto-discovered from connected server |
| 13 | Sandbox manual | Tool documentation generated from MCP schemas |
| 14 | Sandbox feedback | Explicit feedback on errors, timeouts, truncation |
| Bonus | Layer 1 | Subprocess isolation (does not count toward pass) |

### How to run

```bash
./exams/exam_sandbox.sh --student-path ./student --moulinette-path ./moulinette --env-file .env
```

### Pass criteria

All non-bonus tests must pass. The bonus test (subprocess isolation) is
informational only and does not affect the pass/fail result.

### Interpreting failures

- **Tests 1-3 fail**: Sandbox security is broken. The student's import
  allowlist or file access restrictions are not working.
- **Tests 4-5 fail**: Dangerous builtins or network-related modules are
  not properly blocked. Check the student's restricted builtins and
  import allowlist.
- **Tests 6-7 fail**: MCP tool integration is broken. The MCP tools are
  not properly exposed in the sandbox namespace.
- **Tests 8-9 fail**: One of the MCP transports (HTTP or stdio) is not
  implemented.
- **Tests 10-11 fail**: Resource enforcement (timeout/memory) is missing.
- **Tests 12-13 fail**: Dynamic MCP discovery or sandbox manual generation
  is not implemented.
- **Test 14 fails**: The sandbox does not provide explicit feedback on
  error conditions.

---

## 2. MBPP Exam (`exams/exam_mbpp.sh`)

### What it tests

Runs 5 randomly selected MBPP tasks through the student's agent. Each task:
1. Is dumped via `moulinette_eval dump mbpp`
2. Is run through the student's agent
3. Has its solution validated via `moulinette_eval validate mbpp`

### How to run

```bash
./exams/exam_mbpp.sh --student-path ./student --moulinette-path ./moulinette --env-file .env
```

Optional: `--model-name MODEL --provider-url URL` to forward LLM configuration.

### Pass criteria

4 out of 5 tasks must pass validation (correctness + metrics).

### Metrics limits

| Metric | Limit |
|--------|-------|
| Max iterations | 10 |
| Max input tokens | 6,000 |
| Max output tokens | 1,500 |
| Timeout | 120 seconds |

### Interpreting failures

- **FAILED (execution)**: The agent crashed. Check `stderr.log` in the
  evaluation directory for the traceback.
- **FAILED (validation)**: The agent produced a solution but it was
  incorrect (tests did not pass) or metrics were exceeded.

### Rerunning a specific task

```bash
# Dump a specific task
cd moulinette
uv run moulinette_eval dump mbpp --task-id 42 --output ../cache/task.json

# Run the agent
cd ../student
uv run python -m agent_mbpp --task-file ../cache/task.json --output ../cache/solution.json

# Validate
cd ../moulinette
uv run moulinette_eval validate mbpp ../cache/task.json ../cache/solution.json
```

---

## 3. SWE-bench Exam (`exams/exam_swebench.sh`)

### What it tests

Randomly selects 3 tasks from a pool of 6 predetermined tasks (all verified
solvable by reference models). The student cannot predict which tasks will
be selected. Each task:
1. Is dumped via `moulinette_eval dump swebench`
2. Is run through the student's agent (inside Docker)
3. Has its solution validated via `moulinette_eval validate swebench`
4. Has container cleanup verified

### How the random selection works

The exam script calls:
```bash
uv run moulinette_eval select swebench --count 3
```

This randomly selects 3 instance IDs from the internal pool of 6 tasks.
The pool is defined in the moulinette (not in the exam script), so students
cannot predict or prepare for specific tasks.

### How to run

```bash
./exams/exam_swebench.sh --student-path ./student --moulinette-path ./moulinette --env-file .env
```

Optional: `--model-name MODEL --provider-url URL` to forward LLM configuration.

### Pass criteria

- 2 out of 3 tasks must pass validation (correctness + metrics)
- Container cleanup must succeed (no orphan containers)

If container cleanup fails for any task, the overall result is FAIL
regardless of the number of tasks passed.

### Metrics limits

| Metric | Limit |
|--------|-------|
| Max iterations | 30 |
| Max input tokens | 300,000 |
| Max output tokens | 10,000 |
| Timeout | 900 seconds (15 min) |

### Interpreting failures

- **FAILED (execution)**: The agent crashed. Check `stderr.log` for the
  traceback. Common causes: Docker image pull failure, container startup
  failure, API key issues.
- **FAILED (validation)**: The agent produced a patch but the moulinette
  evaluation determined it was incorrect (tests did not pass) or metrics
  were exceeded.
- **CLEANUP: FAILED**: A Docker container was left running after the agent
  exited. The student must implement cleanup via atexit/signal handlers.

### Rerunning a specific task

```bash
# Dump a specific task
cd moulinette
uv run moulinette_eval dump swebench --task-id sympy__sympy-13480 --output ../cache/task.json

# Run the agent
cd ../student
uv run python -m agent_swebench --task-file ../cache/task.json --output ../cache/solution.json

# Validate
cd ../moulinette
uv run moulinette_eval validate swebench ../cache/task.json ../cache/solution.json
```

---

## 4. Anti-Cheat Checks (`exams/exam_anticheat.sh`)

### What it tests

Searches the student's Python source code for suspicious patterns that
indicate solution lookup rather than legitimate solving:

| Check | What it detects |
|-------|----------------|
| GitHub URLs | References to github.com (excluding imports/comments) |
| PR/Issue in prompts | PR, issue, commit mentions near prompt strings |
| HTTP requests | External HTTP client usage (requests, urllib, httpx) |
| SWE-bench dataset | Direct access to gold patches or FAIL_TO_PASS |
| Git history in prompts | Git log/show/diff commands in prompt strings |
| Forbidden libraries | llama-index, smolagents, langgraph, crewai, autogen |

### How to run

```bash
./exams/exam_anticheat.sh --student-path ./student
```

### Pass criteria

All checks must pass with no warnings. Any warning requires manual
investigation with the student.

---

## 5. Moulinette Display Command

For quick inspection of solution.json files during correction:

```bash
cd moulinette
uv run moulinette_eval display ../path/to/solution.json
```

Shows:
- Task metadata (ID, benchmark, success, token counts)
- System prompt (truncated to 2000 chars; use `--full` to show all)
- Per-step trace: model, tokens, retries, llm_output, sandbox_input, sandbox_output
- Automated consistency checks (empty fields, sequential timestamps,
  duplicate code detection)

---

## Results Directory Structure

Each exam script saves results to:

```
evaluations/<exam_type>/<YYYY-MM-DD_HH-MM-SS>/
  <task_id>/
    task.json       # Task input
    solution.json   # Agent output
    stdout.log      # Agent stdout + validation output
    stderr.log      # Agent stderr
```

For sandbox exams:
```
evaluations/sandbox/<YYYY-MM-DD_HH-MM-SS>/
  allowed_imports/
    stdout.log
    stderr.log
  blocked_imports/
    ...
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `uv sync` fails | Check Python version matches `.python-version` |
| Docker images not pulling | Ensure Docker daemon is running, check disk space |
| API key errors | Verify .env file exists and contains valid keys |
| Agent hangs | Auto-killed by `moulinette run-agent` after the time limit — task fails as "time limit" instead of blocking the script. If it still doesn't die, check for a stuck Docker container: `docker ps` |
| Container cleanup failure | Student needs atexit/signal handlers; check with `docker ps \| grep sweb.eval` |
| Moulinette validation crashes | Ensure moulinette has `uv sync` completed |
| SWE-bench select fails | Ensure moulinette is up to date |
