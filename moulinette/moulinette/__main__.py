# ABOUTME: Fire CLI for moulinette evaluation tools (dump, validate, select, display, run-agent, warmup).
# ABOUTME: The moulinette does NOT run student code, except run-agent which enforces a hard timeout on it.
import json
import os
import random
import shlex
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from colorama import Fore, Style, init as colorama_init

from moulinette.models import (
    SolutionOutput,
    MBPPTaskInput,
    SWEBenchTaskInput,
    MetricsLimits,
    MetricsValidationResult,
)
from moulinette.mbpp import InteractMBPP
from moulinette.swebench import InteractSweBench, SEED_POOL, EXAM_POOL

# Silences a harmless multiprocess.ResourceTracker AttributeError on Python 3.12 shutdown.
try:
    from multiprocess.resource_tracker import ResourceTracker as _ResourceTracker

    def _safe_del(self, _original_del=_ResourceTracker.__del__):
        try:
            _original_del(self)
        except AttributeError:
            pass

    _ResourceTracker.__del__ = _safe_del
except ImportError:
    pass

# Initialize colorama
colorama_init(autoreset=True)


# Color helpers
def yellow(text: str) -> str:
    return f"{Fore.YELLOW}{text}{Style.RESET_ALL}"

def green(text: str) -> str:
    return f"{Fore.GREEN}{text}{Style.RESET_ALL}"

def red(text: str) -> str:
    return f"{Fore.RED}{text}{Style.RESET_ALL}"

def cyan(text: str) -> str:
    return f"{Fore.CYAN}{text}{Style.RESET_ALL}"

def magenta(text: str) -> str:
    return f"{Fore.MAGENTA}{text}{Style.RESET_ALL}"

def status_color(ok: bool, ok_text: str = "OK", fail_text: str = "EXCEEDED") -> str:
    if ok:
        return green(ok_text)
    return red(fail_text)


# Pool of predetermined SWE-bench tasks for exam evaluation.
SWEBENCH_EXAM_POOL = EXAM_POOL

# Cap on the SWE-bench grading run itself, separate from the agent's own timeout.
SWEBENCH_EVAL_TIMEOUT_SECONDS = 900


def _validate_swebench_patch(sb: InteractSweBench, instance_id: str, patch: str) -> bool:
    """Validate a SWE-bench patch by running the evaluation script.

    Checks that the solution looks like a git patch, then runs the SWE-bench
    evaluation inside a Docker container.
    """
    patch_markers = ["diff --git", "--- a/", "+++ b/", "@@"]
    if not patch or not any(m in patch for m in patch_markers):
        print("Solution doesn't look like a git patch")
        return False
    try:
        # InteractSweBench.eval runs the SWE-bench evaluation script inside a Docker container
        return sb.eval(
            instance_id=instance_id,
            container_id=None,
            patch=patch,
            timeout=SWEBENCH_EVAL_TIMEOUT_SECONDS,
        )
    except Exception as e:
        print(f"Error validating solution: {e}")
        return False


def _get_limits(benchmark: str) -> MetricsLimits:
    """Get metrics limits for a benchmark."""
    if benchmark == "mbpp":
        return MetricsLimits.mbpp_defaults()
    elif benchmark == "swebench":
        return MetricsLimits.swebench_defaults()
    else:
        print(red(f"Unknown benchmark: {benchmark}"))
        sys.exit(1)


def _print_metrics(solution: SolutionOutput, limits: MetricsLimits, result: MetricsValidationResult) -> None:
    """Print metrics validation table and errors."""
    print(f"Iterations: {solution.iterations} / {limits.max_iterations} {status_color(result.iterations_ok)}")
    print(f"Input tokens: {solution.total_input_tokens} / {limits.max_input_tokens} {status_color(result.input_tokens_ok)}")
    print(f"Output tokens: {solution.total_output_tokens} / {limits.max_output_tokens} {status_color(result.output_tokens_ok)}")
    print(f"Time: {solution.total_time_seconds:.1f}s / {limits.max_time_seconds}s {status_color(result.time_ok)}")

    if not result.valid:
        print(f"\n{red('Errors:')}")
        for error in result.errors:
            print(red(f"  - {error}"))


class MoulinetteCLI:
    """Moulinette CLI for MBPP and SWE-bench task management.

    The moulinette does NOT run student code, except through run-agent, which runs it
    under a hard timeout for exam scripts. Commands:
    1. Dumps tasks to JSON files (dump command)
    2. Validates solutions from JSON files (validate command)
    3. Validates solution metrics (validate_metrics command)
    4. Selects random tasks for exam evaluation (select command)
    5. Pretty-prints solution.json for inspection (display command)
    6. Runs a student agent command under a hard timeout (run-agent command)
    7. Pre-pulls exam-pool Docker images (warmup command)

    Full evaluation is performed by exam scripts (exam_mbpp.sh, exam_swebench.sh).
    """

    def run_agent(self, time_limit: int, cmd: str):
        """Run a student agent command under a hard OS-level timeout.

        exam_mbpp.sh/exam_swebench.sh used to invoke the student agent directly and only
        check its wall-clock duration *after* it returned — an agent that never returns
        (infinite loop, unbounded LLM retries, network deadlock) would hang the exam
        script forever instead of failing the task. This runs the agent in its own
        process group and kills the whole group (agent + anything it forked) once
        time_limit is exceeded, so the script always makes progress.

        Args:
            time_limit: Seconds to allow cmd to run before it is killed.
            cmd: The agent invocation, as a single shell-quoted command line
                (e.g. "python -m agent_mbpp --task-file task.json --output solution.json").
        """
        start = time.monotonic()
        proc = subprocess.Popen(shlex.split(cmd), start_new_session=True)
        try:
            proc.wait(timeout=time_limit)
        except subprocess.TimeoutExpired:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(pgid, signal.SIGKILL)
                proc.wait()
            print(red(f"Agent exceeded time limit ({time_limit}s) — killed"))
            sys.exit(124)  # conventional timeout exit code, mirrors GNU `timeout`

        elapsed = time.monotonic() - start
        if proc.returncode != 0:
            print(red(f"Agent exited with code {proc.returncode} after {elapsed:.1f}s"))
            sys.exit(proc.returncode)
        print(green(f"Agent finished in {elapsed:.1f}s"))

    def warmup(self, benchmark: str = "swebench", max_workers: int = 4):
        """Pre-pull exam-pool Docker images in parallel to avoid cold-pull delays during grading.

        Args:
            benchmark: Only "swebench" is supported (MBPP has no per-task images to pull).
            max_workers: Number of concurrent `docker pull` operations.
        """
        if benchmark != "swebench":
            print(red(f"Warmup is only supported for swebench (got: {benchmark})"))
            sys.exit(1)

        sb = InteractSweBench()
        pool = SWEBENCH_EXAM_POOL
        print(f"Pulling {len(pool)} SWE-bench image(s) ({max_workers} at a time)...")

        failures = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(sb.pull, instance_id): instance_id for instance_id in pool}
            for future in as_completed(futures):
                instance_id = futures[future]
                try:
                    future.result()
                    print(green(f"  {instance_id}: OK"))
                except Exception as e:
                    failures.append(instance_id)
                    print(red(f"  {instance_id}: FAILED ({e})"))

        if failures:
            print(red(f"\n{len(failures)}/{len(pool)} image(s) failed to pull: {', '.join(failures)}"))
            sys.exit(1)
        print(green(f"\nAll {len(pool)} image(s) ready."))

    def dump(self, benchmark: str, task_id: str = None, seed: int = None, output: str = "task.json"):
        """Dump task to JSON. Random if no task_id given.

        Args:
            benchmark: "mbpp" or "swebench"
            task_id: Task/instance ID (random if not specified)
            seed: Random seed for task selection
            output: Output JSON file path
        """
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if benchmark == "mbpp":
            mbpp = InteractMBPP()
            if task_id is not None:
                tid = int(task_id)
            else:
                pool = mbpp.list_tasks(split="test")
                if seed is not None:
                    random.seed(seed)
                tid = random.choice(pool)

            task_info = mbpp.get_task(tid)
            task_input = MBPPTaskInput.from_moulinette(task_info)
            with open(output_path, "w") as f:
                f.write(task_input.model_dump_json(indent=2))
            print(f"Task {tid} dumped to: {output_path}")

        elif benchmark == "swebench":
            sb = InteractSweBench()
            if task_id is not None:
                instance_id = task_id
            else:
                pool = sb.list_instances()
                if seed is not None:
                    random.seed(seed)
                instance_id = random.choice(pool)

            instance_info = sb.get_instance_info(instance_id)
            task_input = SWEBenchTaskInput.from_moulinette(instance_info)
            with open(output_path, "w") as f:
                f.write(task_input.model_dump_json(indent=2))
            print(f"Instance {instance_id} dumped to: {output_path}")

        else:
            print(red(f"Unknown benchmark: {benchmark}. Use 'mbpp' or 'swebench'."))
            sys.exit(1)

        print(f"Task saved to: {output}")

    def validate(self, benchmark: str, task_file: str, solution_file: str, skip_metrics: bool = False):
        """Validate solution (correctness + metrics).

        Args:
            benchmark: "mbpp" or "swebench"
            task_file: Path to task JSON file
            solution_file: Path to solution JSON file
            skip_metrics: Skip metrics validation
        """
        # Load task and solution
        with open(task_file) as f:
            task_data = json.load(f)
        with open(solution_file) as f:
            solution_data = json.load(f)

        solution_output = SolutionOutput.model_validate(solution_data)
        task_id = task_data.get("task_id") or task_data.get("instance_id")

        print(f"\n{yellow('='*60)}")
        print(yellow("VALIDATING SOLUTION"))
        print(f"{yellow('='*60)}")
        print(f"Task ID: {task_id}")
        print(f"Benchmark: {benchmark}")
        print(f"Success claimed: {solution_output.success}")

        # Step 1: Correctness validation
        print(f"\n{yellow('='*60)}")
        print(yellow("STEP 1: CORRECTNESS VALIDATION"))
        print(f"{yellow('='*60)}")

        if benchmark == "mbpp":
            task = MBPPTaskInput.model_validate(task_data)
            mbpp = InteractMBPP()
            eval_result = mbpp.evaluate_task_solution(
                int(task.task_id),
                solution_output.solution,
                skip_first_k_tests=0,  # Run ALL tests including hidden
            )
            passed = eval_result.get("success", False)
            if not passed:
                # Surface infra failures (e.g. a missing Docker image) distinctly from a wrong solution.
                detail = eval_result.get("output") or eval_result.get("message")
                if detail:
                    print(red(f"Correctness check detail: {detail}"))
        elif benchmark == "swebench":
            task = SWEBenchTaskInput.model_validate(task_data)
            sb = InteractSweBench()
            passed = _validate_swebench_patch(sb, task.instance_id, solution_output.solution)
        else:
            print(red(f"Unknown benchmark: {benchmark}"))
            sys.exit(1)

        print(f"Correctness: {status_color(passed, 'PASSED', 'FAILED')}")

        # Step 2: Metrics validation (unless skipped)
        metrics_valid = True
        if not skip_metrics:
            print(f"\n{yellow('='*60)}")
            print(yellow("STEP 2: METRICS VALIDATION"))
            print(f"{yellow('='*60)}")

            limits = _get_limits(benchmark)
            result = MetricsValidationResult.validate_solution(solution_output, limits)
            _print_metrics(solution_output, limits, result)
            print(f"Metrics: {status_color(result.valid, 'VALID', 'INVALID')}")

            metrics_valid = result.valid
        else:
            print("\n(Metrics validation skipped)")

        # Final result
        print(f"\n{yellow('='*60)}")
        print(yellow("FINAL RESULT"))
        print(f"{yellow('='*60)}")
        overall_passed = passed and metrics_valid
        print(f"Correctness: {status_color(passed, 'PASSED', 'FAILED')}")
        if not skip_metrics:
            print(f"Metrics: {status_color(metrics_valid, 'VALID', 'INVALID')}")
        print(f"Overall: {status_color(overall_passed, 'PASSED', 'FAILED')}")

        if not overall_passed:
            sys.exit(1)

    def validate_metrics(self, benchmark: str, solution_file: str):
        """Validate solution metrics against limits.

        Args:
            benchmark: "mbpp" or "swebench"
            solution_file: Path to solution JSON file
        """
        with open(solution_file) as f:
            solution_data = json.load(f)

        solution_output = SolutionOutput.model_validate(solution_data)
        limits = _get_limits(benchmark)
        result = MetricsValidationResult.validate_solution(solution_output, limits)

        print(f"\n{yellow('='*60)}")
        print(yellow("METRICS VALIDATION"))
        print(f"{yellow('='*60)}")
        print(f"Benchmark: {benchmark}")
        print(f"Task ID: {solution_output.task_id}")
        _print_metrics(solution_output, limits, result)
        print(f"\nMetrics valid: {status_color(result.valid, 'YES', 'NO')}")

        if not result.valid:
            sys.exit(1)

    def select(self, benchmark: str = "swebench", count: int = 3, seed: int = None, output: str = None):
        """Select random tasks from the exam pool.

        Args:
            benchmark: Benchmark type (only "swebench" supported)
            count: Number of tasks to select (default: 3)
            seed: Random seed for reproducibility
            output: Output JSON file (prints to stdout if not given)
        """
        if benchmark != "swebench":
            print(red(f"Select is only supported for swebench (got: {benchmark})"))
            sys.exit(1)

        pool = SWEBENCH_EXAM_POOL

        if count > len(pool):
            print(red(f"Requested {count} tasks but pool only has {len(pool)}"))
            sys.exit(1)

        if seed is not None:
            random.seed(seed)

        selected = random.sample(pool, count)

        print(f"Selected {count}/{len(pool)} tasks from exam pool:", file=sys.stderr)
        for task_id in selected:
            print(f"  - {task_id}", file=sys.stderr)

        # Output as JSON (to stdout for piping, or to file)
        output_data = {"instance_ids": selected, "count": count, "pool_size": len(pool)}

        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(output_data, f, indent=2)
            print(f"Selection saved to: {output}", file=sys.stderr)
        else:
            # Print to stdout for piping
            print(json.dumps(output_data))

    def display(self, solution_file: str, full: bool = False):
        """Pretty-print solution.json for corrector inspection.

        Args:
            solution_file: Path to solution JSON file
            full: Show full system prompt (no truncation)
        """
        with open(solution_file) as f:
            solution_data = json.load(f)

        solution = SolutionOutput.model_validate(solution_data)
        truncate_len = 999_999 if full else 2000

        # Header
        print(f"\n{yellow('='*60)}")
        print(yellow("SOLUTION DISPLAY"))
        print(f"{yellow('='*60)}")
        print(f"Task ID:       {solution.task_id}")
        print(f"Benchmark:     {solution.benchmark}")
        print(f"Success:       {status_color(solution.success, 'YES', 'NO')}")
        print(f"Iterations:    {solution.iterations}")
        print(f"Total tokens:  {solution.total_input_tokens} in / {solution.total_output_tokens} out")
        print(f"Time:          {solution.total_time_seconds:.1f}s")
        print(f"Timestamp:     {solution.timestamp}")

        # System prompt
        print(f"\n{yellow('='*60)}")
        print(yellow("SYSTEM PROMPT"))
        print(f"{yellow('='*60)}")
        prompt = solution.system_prompt or "(empty)"
        if len(prompt) > truncate_len:
            print(prompt[:truncate_len])
            print(f"\n... ({len(prompt) - truncate_len} chars truncated, use --full to show all)")
        else:
            print(prompt)

        # Per-step table
        print(f"\n{yellow('='*60)}")
        print(yellow("STEP-BY-STEP TRACE"))
        print(f"{yellow('='*60)}")

        if not solution.steps:
            print("(no steps recorded)")
        else:
            for step in solution.steps:
                llm_out = step.llm_output or "(empty)"
                sandbox_in = step.sandbox_input or "(empty)"
                sandbox_out = step.sandbox_output or "(empty)"
                retries = getattr(step, "retries", 0)

                # Step header
                print(f"\n{yellow('━' * 60)}")
                print(yellow(f"  Step {step.step}"))
                print(f"{yellow('━' * 60)}")

                # Metadata block
                print(f"  {green('Model:')}      {step.model_name or '(empty)'}")
                print(f"  {green('API URL:')}    {step.api_url or '(empty)'}")
                print(f"  {green('Tokens:')}     {step.input_tokens} in / {step.output_tokens} out")
                print(f"  {green('Time:')}       {step.request_time_ms:.0f}ms")
                print(f"  {green('Timestamp:')}  {step.timestamp}")
                retries_display = red(str(retries)) if retries > 0 else green(str(retries))
                print(f"  {green('Retries:')}    {retries_display}")

                # LLM output
                print(f"\n  {cyan('LLM Output')} ({len(llm_out)} chars):")
                llm_preview = llm_out[:500]
                if len(llm_out) > 500:
                    llm_preview += f"... ({len(llm_out) - 500} more chars)"
                for line in llm_preview.split("\n"):
                    print(f"    {line}")

                # Sandbox input (code sent)
                print(f"\n  {green('Sandbox Input')} ({len(sandbox_in)} chars):")
                si_preview = sandbox_in[:300]
                if len(sandbox_in) > 300:
                    si_preview += f"... ({len(sandbox_in) - 300} more chars)"
                for line in si_preview.split("\n"):
                    print(f"    {line}")

                # Sandbox output (execution result)
                print(f"\n  {magenta('Sandbox Output')} ({len(sandbox_out)} chars):")
                so_preview = sandbox_out[:300]
                if len(sandbox_out) > 300:
                    so_preview += f"... ({len(sandbox_out) - 300} more chars)"
                for line in so_preview.split("\n"):
                    print(f"    {line}")

        # Consistency checks
        print(f"\n{yellow('='*60)}")
        print(yellow("CONSISTENCY CHECKS"))
        print(f"{yellow('='*60)}")

        issues = []
        notes = []

        # Check: system_prompt non-empty
        if not solution.system_prompt:
            issues.append("system_prompt is empty")

        # Check: sandbox_input non-empty for steps that have sandbox_output
        for step in solution.steps:
            if step.sandbox_output and not step.sandbox_input:
                issues.append(f"Step {step.step}: has sandbox_output but empty sandbox_input")

        # Check: llm_output non-empty
        for step in solution.steps:
            if not step.llm_output:
                issues.append(f"Step {step.step}: llm_output is empty")

        # Check: retries (informational)
        for step in solution.steps:
            retries = getattr(step, "retries", 0)
            if retries > 0:
                notes.append(f"Step {step.step}: {retries} LLM retries")

        # Check: timestamps sequential
        prev_ts = None
        for step in solution.steps:
            if prev_ts and step.timestamp < prev_ts:
                issues.append(f"Step {step.step}: timestamp {step.timestamp} < previous {prev_ts}")
            prev_ts = step.timestamp

        # Check: model_name consistent
        model_names = {s.model_name for s in solution.steps if s.model_name}
        if len(model_names) > 1:
            issues.append(f"Multiple model_names across steps: {model_names}")

        # Check: no identical sandbox_input in consecutive steps (copy-paste detection)
        for i in range(1, len(solution.steps)):
            prev_code = solution.steps[i - 1].sandbox_input
            curr_code = solution.steps[i].sandbox_input
            if prev_code and curr_code and prev_code == curr_code:
                issues.append(
                    f"Steps {solution.steps[i-1].step} and {solution.steps[i].step}: "
                    f"identical sandbox_input (copy-paste?)"
                )

        if notes:
            for note in notes:
                print(yellow(f"  NOTE: {note}"))
        if issues:
            for issue in issues:
                print(red(f"  WARN: {issue}"))
        if not issues and not notes:
            print(green("  All checks passed"))


def main():
    """Entry point for moulinette_eval CLI."""
    import fire
    fire.Fire(MoulinetteCLI)


if __name__ == "__main__":
    main()
