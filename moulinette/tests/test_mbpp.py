"""Tests for moulinette MBPP module."""
import pytest
import docker


class TestMBPP:
    """Tests for moulinette MBPP module."""

    def test_list_tasks(self):
        """Test listing MBPP tasks."""
        from moulinette.mbpp import InteractMBPP
        
        mbpp = InteractMBPP()
        task_ids = mbpp.list_tasks(split="fewshot")
        
        assert isinstance(task_ids, list)
        assert len(task_ids) > 0
        assert all(isinstance(tid, int) for tid in task_ids)

    def test_get_task_by_id(self):
        """Test getting a specific MBPP task."""
        from moulinette.mbpp import InteractMBPP
        
        mbpp = InteractMBPP()
        task = mbpp.get_task(task_id=2)
        
        assert task["task_id"] == 2
        assert "task_definition" in task
        assert "function_definition" in task
        assert "public_test_list" in task
        assert task["function_definition"].startswith("def ")

    def test_get_random_task(self):
        """Test getting a random MBPP task."""
        from moulinette.mbpp import InteractMBPP
        
        mbpp = InteractMBPP()
        task = mbpp.get_task()  # No task_id = random
        
        assert "task_id" in task
        assert "task_definition" in task
        assert "function_definition" in task

    def test_evaluate_success(self):
        """Test successful code evaluation for MBPP task."""
        from moulinette.mbpp import InteractMBPP
        
        mbpp = InteractMBPP()
        
        # Task 2: similar_elements - correct solution
        correct_code = """
def similar_elements(test_tup1, test_tup2):
    return tuple(set(test_tup1) & set(test_tup2))
"""
        result = mbpp.evaluate_task_solution(task_id=2, code=correct_code)
        
        assert result["success"] is True
        assert "passed" in result["message"].lower()

    def test_evaluate_failure(self):
        """Test failed code evaluation for MBPP task."""
        from moulinette.mbpp import InteractMBPP
        
        mbpp = InteractMBPP()
        
        # Task 2: similar_elements - wrong solution
        wrong_code = """
def similar_elements(test_tup1, test_tup2):
    return "wrong answer"
"""
        result = mbpp.evaluate_task_solution(task_id=2, code=wrong_code)
        
        assert result["success"] is False
        assert "failed" in result["message"].lower()
        assert "AssertionError" in result["output"] or "Error" in result["output"]

    def test_evaluate_syntax_error(self):
        """Test code with syntax error."""
        from moulinette.mbpp import InteractMBPP
        
        mbpp = InteractMBPP()
        
        # Invalid Python syntax
        bad_code = """
def similar_elements(test_tup1, test_tup2)
    return None  # Missing colon
"""
        result = mbpp.evaluate_task_solution(task_id=2, code=bad_code)
        
        assert result["success"] is False
        assert "SyntaxError" in result["output"]


class TestDockerExecution:
    """Tests for Docker-based code execution."""

    def test_docker_available(self):
        """Test that Docker is available."""
        client = docker.from_env()
        assert client.ping()

    def test_docker_image_exists(self):
        """Test that the Python Docker image exists."""
        client = docker.from_env()
        try:
            client.images.get("python:3.11-slim")
        except docker.errors.ImageNotFound:
            pytest.skip("Docker image python:3.11-slim not found. Run: docker pull python:3.11-slim")

    def test_run_simple_code(self):
        """Test running simple code in Docker."""
        from moulinette.mbpp import run_code_in_docker
        
        success, output = run_code_in_docker("print('hello')")
        
        assert success is True
        assert output == "hello"

    def test_run_failing_code(self):
        """Test running code that raises an exception."""
        from moulinette.mbpp import run_code_in_docker
        
        success, output = run_code_in_docker("raise ValueError('test error')")
        
        assert success is False
        assert "ValueError" in output

    def test_container_cleanup(self):
        """Test that containers are cleaned up after execution."""
        from moulinette.mbpp import run_code_in_docker
        
        client = docker.from_env()
        
        # Get container count before
        containers_before = len(client.containers.list(all=True))
        
        # Run some code
        run_code_in_docker("print('test')")
        run_code_in_docker("raise Exception('fail')")
        
        # Get container count after
        containers_after = len(client.containers.list(all=True))
        
        # Should be the same (no leaked containers)
        assert containers_after == containers_before


class TestMBPPIntegration:
    """Integration tests for MBPP workflow."""

    def test_mbpp_full_workflow(self):
        """Test full MBPP workflow: get task -> solve -> evaluate."""
        from moulinette.mbpp import InteractMBPP
        
        mbpp = InteractMBPP()
        
        # 1. Get task 3 (is_not_prime)
        task = mbpp.get_task(task_id=3)
        assert task["task_id"] == 3
        assert "is_not_prime" in task["function_definition"]
        
        # 2. Write correct solution
        solution = """
import math

def is_not_prime(n):
    if n < 2:
        return True
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return True
    return False
"""
        
        # 3. Evaluate
        result = mbpp.evaluate_task_solution(task_id=3, code=solution)
        assert result["success"] is True

    def test_mbpp_multiple_tasks(self):
        """Test evaluating multiple different tasks."""
        from moulinette.mbpp import InteractMBPP
        
        mbpp = InteractMBPP()
        
        # Task 2: similar_elements
        result1 = mbpp.evaluate_task_solution(
            task_id=2,
            code="def similar_elements(a, b): return tuple(set(a) & set(b))"
        )
        
        # Task 4: heap_queue_largest
        result2 = mbpp.evaluate_task_solution(
            task_id=4,
            code="""
import heapq
def heap_queue_largest(nums, n):
    return heapq.nlargest(n, nums)
"""
        )
        
        assert result1["success"] is True
        assert result2["success"] is True
