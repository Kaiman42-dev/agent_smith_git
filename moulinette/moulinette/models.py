# ABOUTME: Internal moulinette models — re-exports public models and adds validation/factory logic.
# ABOUTME: Keeps from_moulinette classmethods, MetricsLimits, and MetricsValidationResult.
import sys
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field

# Add moulinette repo root to path so we can import the public models file
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from models_public import (  # noqa: E402
    StepMetrics,
    SolutionOutput,
    SandboxConfig as _SandboxConfigBase,
    MBPPTaskInput as _MBPPTaskInputBase,
    SWEBenchTaskInput as _SWEBenchTaskInputBase,
)


# =============================================================================
# Sandbox Configuration (with moulinette defaults)
# =============================================================================

class SandboxConfig(_SandboxConfigBase):
    """Sandbox configuration with moulinette-specific defaults."""
    authorized_imports: List[str] = Field(default_factory=lambda: [
        "math", "math.*",
        "collections", "collections.*",
        "itertools", "re", "json",
        "typing", "typing.*",
        "functools", "operator",
        "heapq", "bisect", "copy",
        "string", "random",
        "datetime", "datetime.*",
        "array", "cmath",
    ])
    allowed_directories: List[str] = Field(default_factory=lambda: [
        "/testbed", "/tmp/agent"
    ])


# =============================================================================
# MBPP Task Models (with from_moulinette factory)
# =============================================================================

class MBPPTaskInput(_MBPPTaskInputBase):
    """MBPP task input with moulinette factory method."""

    @classmethod
    def from_moulinette(cls, task_info: dict) -> "MBPPTaskInput":
        """Create from moulinette task info."""
        return cls(
            task_id=task_info["task_id"],
            task_definition=task_info["task_definition"],
            function_definition=task_info["function_definition"],
            test_imports=task_info.get("public_test_imports", []),
            test_list=task_info.get("public_test_list", []),
        )


# =============================================================================
# SWE-bench Task Models (with from_moulinette factory)
# =============================================================================

class SWEBenchTaskInput(_SWEBenchTaskInputBase):
    """SWE-bench task input with moulinette factory method."""

    @classmethod
    def from_moulinette(cls, instance_info: dict) -> "SWEBenchTaskInput":
        """Create from moulinette instance info."""
        return cls(
            instance_id=instance_info["instance_id"],
            problem_statement=instance_info["problem_statement"],
            docker_image=instance_info.get("dockerhub_image_name", ""),
            eval_script=instance_info.get("eval_script", ""),
            hints_text=instance_info.get("hints_text", ""),
            repo=instance_info.get("repo", ""),
        )


# =============================================================================
# Metrics Limits (moulinette-internal)
# =============================================================================

class MetricsLimits(BaseModel):
    """Limits for validating student solution metrics."""
    max_iterations: int
    max_input_tokens: int
    max_output_tokens: int
    max_time_seconds: float

    @classmethod
    def mbpp_defaults(cls) -> "MetricsLimits":
        """Default limits for MBPP benchmark."""
        return cls(
            max_iterations=10,
            max_input_tokens=6_000,
            max_output_tokens=1_500,
            max_time_seconds=120.0,
        )

    @classmethod
    def swebench_defaults(cls) -> "MetricsLimits":
        """Default limits for SWE-bench benchmark."""
        return cls(
            max_iterations=30,
            max_input_tokens=300_000,
            max_output_tokens=10_000,
            max_time_seconds=900.0,
        )


class MetricsValidationResult(BaseModel):
    """Result of validating solution metrics against limits."""
    valid: bool
    iterations_ok: bool
    input_tokens_ok: bool
    output_tokens_ok: bool
    time_ok: bool
    errors: List[str] = Field(default_factory=list)

    @classmethod
    def validate_solution(
        cls, solution: SolutionOutput, limits: MetricsLimits
    ) -> "MetricsValidationResult":
        """Validate a solution's metrics against limits."""
        errors = []

        iterations_ok = solution.iterations <= limits.max_iterations
        if not iterations_ok:
            errors.append(f"Iterations {solution.iterations} exceeds limit {limits.max_iterations}")

        input_tokens_ok = solution.total_input_tokens <= limits.max_input_tokens
        if not input_tokens_ok:
            errors.append(f"Input tokens {solution.total_input_tokens} exceeds limit {limits.max_input_tokens}")

        output_tokens_ok = solution.total_output_tokens <= limits.max_output_tokens
        if not output_tokens_ok:
            errors.append(f"Output tokens {solution.total_output_tokens} exceeds limit {limits.max_output_tokens}")

        time_ok = solution.total_time_seconds <= limits.max_time_seconds
        if not time_ok:
            errors.append(f"Time {solution.total_time_seconds}s exceeds limit {limits.max_time_seconds}s")

        return cls(
            valid=iterations_ok and input_tokens_ok and output_tokens_ok and time_ok,
            iterations_ok=iterations_ok,
            input_tokens_ok=input_tokens_ok,
            output_tokens_ok=output_tokens_ok,
            time_ok=time_ok,
            errors=errors,
        )
