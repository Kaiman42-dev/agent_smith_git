"""Tests for moulinette SWE-bench module."""
import pytest


INSTANCE_ID = "sympy__sympy-23534"

# Correct patch that fixes the issue
CORRECT_PATCH = """diff --git a/sympy/core/symbol.py b/sympy/core/symbol.py
--- a/sympy/core/symbol.py
+++ b/sympy/core/symbol.py
@@ -791,7 +791,7 @@ def literal(s):
         return tuple(result)
     else:
         for name in names:
-            result.append(symbols(name, **args))
+            result.append(symbols(name, cls=cls, **args))
 
         return type(names)(result)
"""

# Bad patch that doesn't fix the issue (no actual change)
BAD_PATCH = """diff --git a/sympy/core/symbol.py b/sympy/core/symbol.py
--- a/sympy/core/symbol.py
+++ b/sympy/core/symbol.py
@@ -791,7 +791,7 @@ def literal(s):
         return tuple(result)
     else:
         for name in names:
-            result.append(symbols(name, **args))
+            result.append(symbols(name, **args))
 
         return type(names)(result)
"""


class TestSWEBench:
    """Tests for moulinette SWE-bench module."""

    def test_list_instances(self):
        """Test listing SWE-bench instances."""
        from moulinette.swebench import InteractSweBench
        
        sb = InteractSweBench()
        instances = sb.list_instances(repo_pattern="sympy", difficulty="<15 min fix")
        
        assert isinstance(instances, list)

    def test_get_instance_info(self):
        """Test getting instance info."""
        from moulinette.swebench import InteractSweBench
        
        sb = InteractSweBench()
        
        try:
            info = sb.get_instance_info(INSTANCE_ID)
            
            assert "instance_id" in info
            assert info["instance_id"] == INSTANCE_ID
            assert "problem_statement" in info
            assert "eval_script" in info
            assert "dockerhub_image_name" in info
        except SystemExit:
            pytest.skip(f"Instance {INSTANCE_ID} not found in dataset")

    def test_get_container_id(self):
        """Test getting/starting a container for an instance."""
        from moulinette.swebench import InteractSweBench
        import docker
        
        sb = InteractSweBench()
        client = docker.from_env()
        
        try:
            container_id = sb.get_container_id(INSTANCE_ID, auto_start=True)
            
            assert container_id is not None
            assert isinstance(container_id, str)
            assert len(container_id) > 0
            
            # Verify container exists and is running
            container = client.containers.get(container_id)
            assert container.status == "running"
            
        finally:
            # Cleanup: stop and remove the container
            try:
                container = client.containers.get(container_id)
                container.stop(timeout=5)
                container.remove(force=True)
            except Exception:
                pass

    def test_container_hello_world(self):
        """Test executing hello world in a container."""
        from moulinette.swebench import InteractSweBench
        import docker
        
        sb = InteractSweBench()
        client = docker.from_env()
        container_id = None
        
        try:
            container_id = sb.get_container_id(INSTANCE_ID, auto_start=True)
            container = client.containers.get(container_id)
            
            # Execute hello world
            exit_code, output = container.exec_run("echo 'Hello World'")
            
            assert exit_code == 0
            assert "Hello World" in output.decode()
            
        finally:
            # Cleanup
            if container_id:
                try:
                    container = client.containers.get(container_id)
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception:
                    pass

    def test_eval_correct_patch(self):
        """Test that the correct patch passes evaluation."""
        from moulinette.swebench import InteractSweBench
        import docker
        
        sb = InteractSweBench()
        client = docker.from_env()
        container_id = None
        
        try:
            # Start a container
            container_id = sb.get_container_id(INSTANCE_ID, auto_start=True)
            
            # Run evaluation with correct patch
            result = sb.eval(
                INSTANCE_ID,
                container_id=container_id,
                patch=CORRECT_PATCH,
                timeout=300,
            )
            
            assert result is True, "Correct patch should pass evaluation"
            
        finally:
            # Cleanup
            if container_id:
                try:
                    container = client.containers.get(container_id)
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception:
                    pass

    def test_eval_bad_patch(self):
        """Test that a bad patch fails evaluation."""
        from moulinette.swebench import InteractSweBench
        import docker
        
        sb = InteractSweBench()
        client = docker.from_env()
        container_id = None
        
        try:
            # Start a container
            container_id = sb.get_container_id(INSTANCE_ID, auto_start=True)
            
            # Run evaluation with bad patch
            result = sb.eval(
                INSTANCE_ID,
                container_id=container_id,
                patch=BAD_PATCH,
                timeout=300,
            )
            
            assert result is False, "Bad patch should fail evaluation"
            
        finally:
            # Cleanup
            if container_id:
                try:
                    container = client.containers.get(container_id)
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception:
                    pass
