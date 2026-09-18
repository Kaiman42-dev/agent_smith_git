# ABOUTME: MBPP task loading, Docker-based code execution, and solution evaluation.
# ABOUTME: Provides InteractMBPP class as Fire CLI for listing/getting/evaluating MBPP tasks.
import json
from pathlib import Path
from typing import List, Literal, Optional, Tuple, Union

import docker


# Data directory is colocated with this file
DATA_DIR = Path(__file__).parent / "data"


class MinimalCodeTask:
    """Minimal code task data."""
    def __init__(self, task_id: int, task_definition: str, function_definition: str):
        self.task_id = task_id
        self.task_definition = task_definition
        self.function_definition = function_definition


class MinimalCodeTaskAndTests(MinimalCodeTask):
    """Minimal code task with tests."""
    def __init__(
        self,
        task_id: int,
        task_definition: str,
        function_definition: str,
        split: str,
        code: str,
        test_imports: List[str],
        test_list: List[str],
    ):
        super().__init__(task_id, task_definition, function_definition)
        self.split = split
        self.code = code
        self.test_imports = test_imports
        self.test_list = test_list


def _load_tasks() -> List[dict]:
    """Load all tasks from sanitized_tasks.json."""
    output_path = DATA_DIR / "sanitized_tasks.json"
    if not output_path.exists():
        raise FileNotFoundError(f"sanitized_tasks.json not found at {output_path}")
    with open(output_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _get_task_by_id(task_id: int, with_tests: bool = True) -> Union[MinimalCodeTask, MinimalCodeTaskAndTests]:
    """Get a task by task_id."""
    tasks_data = _load_tasks()
    for task_data in tasks_data:
        if task_data['task_id'] == task_id:
            if with_tests:
                return MinimalCodeTaskAndTests(
                    task_id=task_data['task_id'],
                    task_definition=task_data['task_definition'],
                    function_definition=task_data['function_definition'],
                    split=task_data['split'],
                    code=task_data['code'],
                    test_imports=task_data.get('test_imports', []),
                    test_list=task_data.get('test_list', []),
                )
            else:
                return MinimalCodeTask(
                    task_id=task_data['task_id'],
                    task_definition=task_data['task_definition'],
                    function_definition=task_data['function_definition'],
                )
    raise ValueError(f"Task ID {task_id} not found")


def run_code_in_docker(
    code: str,
    timeout: float = 30.0,
    image: str = "python:3.11-slim",
    mem_limit: str = "128m",
) -> Tuple[bool, str]:
    """Execute Python code in an isolated Docker container.

    Args:
        code: The Python code to execute.
        timeout: Execution timeout in seconds (default 30).
        image: Docker image to use (default python:3.11-slim).
        mem_limit: Memory limit for the container (default 128m).

    Returns:
        Tuple of (success: bool, output: str)
    """
    client = docker.from_env()
    container = None

    try:
        # Pull the image on first use if it isn't cached locally yet.
        try:
            client.images.get(image)
        except docker.errors.ImageNotFound:
            client.images.pull(image)

        # Create container (don't auto-remove so we can get logs on timeout)
        container = client.containers.create(
            image,
            command=["python", "-c", code],
            network_disabled=True,
            mem_limit=mem_limit,
            cpu_period=100000,
            cpu_quota=50000,  # 50% CPU
        )

        # Start the container
        container.start()

        # Wait for completion with timeout
        result = container.wait(timeout=timeout)
        exit_code = result.get("StatusCode", 1)

        # Get logs
        stdout = container.logs(stdout=True, stderr=False).decode()
        stderr = container.logs(stdout=False, stderr=True).decode()

        if exit_code == 0:
            return True, stdout.strip() if stdout else ""
        else:
            # Return stderr on failure (contains traceback)
            return False, stderr.strip() if stderr else stdout.strip()

    except docker.errors.NotFound:
        return False, f"Docker image '{image}' not found. Run: docker pull {image}"
    except docker.errors.APIError as e:
        if "read timeout" in str(e).lower() or "timeout" in str(e).lower():
            return False, f"Execution timed out after {timeout} seconds"
        return False, f"Docker API error: {str(e)}"
    except Exception as e:
        error_msg = str(e)
        if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            return False, f"Execution timed out after {timeout} seconds"
        return False, f"Execution error: {error_msg}"
    finally:
        # Cleanup container
        if container:
            try:
                container.stop(timeout=1)
            except Exception:
                pass
            try:
                container.remove(force=True)
            except Exception:
                pass


class InteractMBPP:
    """Minimal CLI for MBPP tasks.

    Examples
    --------
    # List all tasks
    uv run moulinette_mbpp list_tasks

    # List tasks for a specific split
    uv run moulinette_mbpp list_tasks --split test

    # Get a specific task
    uv run moulinette_mbpp get_task 2

    # Evaluate a solution
    uv run moulinette_mbpp evaluate_task_solution 2 "def similar_elements(test_tup1, test_tup2): return tuple(set(test_tup1) & set(test_tup2))"
    """

    def list_tasks(
        self,
        split: Optional[Literal["train", "fewshot", "test", "val"]] = None,
    ) -> List[int]:
        """List task IDs, optionally filtered by split.

        Parameters
        ----------
        split
            Optional split to filter by (train, fewshot, test, val).
            If not provided, returns all task IDs.
        """
        tasks_data = _load_tasks()

        if split:
            task_ids = [t['task_id'] for t in tasks_data if t['split'] == split]
        else:
            task_ids = [t['task_id'] for t in tasks_data]

        return sorted(task_ids)

    def get_task(
        self,
        task_id: Optional[int] = None,
    ) -> dict:
        """Get task details including definition, function signature, and public tests.

        Parameters
        ----------
        task_id
            Task ID to retrieve. If not provided, returns a random task.
        """
        if task_id is None:
            import random
            tasks_data = _load_tasks()
            task_data = random.choice(tasks_data)
            task_id = task_data['task_id']

        task = _get_task_by_id(task_id, with_tests=True)

        # Build result with public tests (skip first test to keep one hidden)
        result = {
            "task_id": task.task_id,
            "task_definition": task.task_definition,
            "function_definition": task.function_definition,
            "split": task.split,
            "public_test_imports": task.test_imports[1:] if len(task.test_imports) > 1 else [],
            "public_test_list": task.test_list[1:] if len(task.test_list) > 1 else [],
        }

        return result

    def evaluate_task_solution(
        self,
        task_id: int,
        code: str,
        skip_first_k_tests: int = 1,
        timeout: int = 30,
    ) -> dict:
        """Evaluate a code solution for a specific task.

        Parameters
        ----------
        task_id
            Task ID to evaluate solution for.
        code
            The code solution to test.
        skip_first_k_tests
            Number of tests to skip (default 1, keeps first test hidden).
        timeout
            Execution timeout in seconds (default 30).

        Returns
        -------
        dict
            Result with 'success' (bool), 'message' (str), and 'output' (str).
        """
        try:
            task = _get_task_by_id(task_id, with_tests=True)
        except ValueError as e:
            result = {
                "success": False,
                "message": str(e),
                "output": "",
            }
            return result

        # Build test code
        test_imports_code = "\n".join(task.test_imports[skip_first_k_tests:]) if task.test_imports else ""
        test_code_str = "\n".join(task.test_list[skip_first_k_tests:]) if task.test_list else ""

        full_code = code + "\n"
        if test_imports_code:
            full_code += test_imports_code + "\n"
        if test_code_str:
            full_code += test_code_str + "\n"

        success, output = run_code_in_docker(full_code, timeout=timeout)

        result = {
            "success": success,
            "message": "All tests passed!" if success else "Tests failed",
            "output": output,
        }
        return result


def _fire_main():
    """Entry point for moulinette_mbpp CLI."""
    import fire
    fire.Fire(InteractMBPP)
