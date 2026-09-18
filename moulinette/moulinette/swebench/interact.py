# ABOUTME: SWE-bench instance management, Docker container lifecycle, and patch evaluation.
# ABOUTME: Provides InteractSweBench class as Fire CLI for listing/inspecting/evaluating SWE-bench tasks.
import json
import platform
import random
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

from swebench.harness.utils import load_swebench_dataset


def get_system_arch() -> str:
    """Return Docker-compatible arch string.

    Always returns x86_64 because SWE-bench does not have arm64 images
    for all tasks. On Apple Silicon, Docker Desktop runs x86_64 images
    via emulation.
    """
    return "x86_64"


class Difficulty(str, Enum):
    """SWE-bench task difficulty levels."""
    LESS_THAN_15_MIN = "<15 min fix"
    MIN_15_TO_1_HOUR = "15 min - 1 hour"
    HOURS_1_TO_4 = "1-4 hours"
    MORE_THAN_4_HOURS = ">4 hours"


# Seed pool of tasks guaranteed to appear in list_instances results.
# All verified solvable by reference models across multiple providers.
SEED_POOL = [
    "django__django-11066",
    "pydata__xarray-4629",
    "scikit-learn__scikit-learn-13439",
    "sympy__sympy-13480",
    "sympy__sympy-18189",
]

# Full exam pool: SEED_POOL + additional exam-only tasks.
# Used by --exclude_exam_pool to avoid selecting predefined exam tasks.
EXAM_POOL = SEED_POOL + [
    "sympy__sympy-14711",
]

from swebench.harness.test_spec.test_spec import make_test_spec
from swebench.harness.docker_utils import copy_to_container, exec_run_with_timeout
from swebench.harness.constants import (
    DOCKER_PATCH,
    DOCKER_WORKDIR,
    DOCKER_USER,
    START_TEST_OUTPUT,
    END_TEST_OUTPUT,
    FAIL_TO_PASS,
    PASS_TO_PASS,
    KEY_INSTANCE_ID,
    FAIL_ONLY_REPOS,
    EvalType,
    ResolvedStatus,
)
from swebench.harness.grading import (
    get_logs_eval,
    get_eval_tests_report,
    get_resolution_status,
)
import docker

DEFAULT_DATASET = "SWE-bench/SWE-bench_Verified"
DEFAULT_SPLIT = "test"


class InteractSweBench:
    """Small helper CLI for interacting with pre-built SWE-bench instance images.

    Examples
    --------
    # Print the docker image tag for an instance_id
    python -m moulinette image-name sympy__sympy-23534

    # Pull it
    python -m moulinette pull sympy__sympy-23534

    # Open a shell
    python -m moulinette shell sympy__sympy-23534

    # Run the evaluation script inside the container
    python -m moulinette eval sympy__sympy-23534
    """
    
    # Docker image configuration (can be overridden)
    DEFAULT_NAMESPACE = "swebench"
    DEFAULT_TAG = "latest"
    
    def __init__(
        self,
        namespace: str = DEFAULT_NAMESPACE,
        arch: Optional[str] = None,
        tag: str = DEFAULT_TAG,
    ):
        """Initialize with configurable Docker image settings.
        
        Parameters
        ----------
        namespace : str
            Docker Hub namespace (default: "swebench")
        arch : str or None
            Architecture. If None, auto-detected from system.
            Common values: "x86_64", "arm64"
        tag : str
            Image tag (default: "latest")
        """
        self.namespace = namespace
        self.arch = arch if arch is not None else get_system_arch()
        self.tag = tag

    def _image_name(self, instance_id: str, arch: Optional[str] = None, tag: Optional[str] = None, namespace: Optional[str] = None) -> str:
        arch = arch or self.arch
        tag = tag or self.tag
        namespace = namespace or self.namespace
        key = f"sweb.eval.{arch}.{instance_id.lower()}:{tag}"
        key = key.replace("__", "_1776_")
        return f"{namespace}/{key}"

    def _get_eval_script(self, instance_id: str, dataset: str = DEFAULT_DATASET, split: str = DEFAULT_SPLIT) -> str:
        """Helper to get eval script for an instance."""
        ds = load_swebench_dataset(dataset, split, [instance_id])
        if not ds:
            raise SystemExit(f"Instance {instance_id} not found in dataset {dataset}/{split}")
        test_spec = make_test_spec(ds[0])
        return test_spec.eval_script

    def _get_test_spec(self, instance_id: str, dataset: str = DEFAULT_DATASET, split: str = DEFAULT_SPLIT):
        """Helper to get test_spec for an instance."""
        ds = load_swebench_dataset(dataset, split, [instance_id])
        if not ds:
            raise SystemExit(f"Instance {instance_id} not found in dataset {dataset}/{split}")
        return make_test_spec(ds[0])

    def image_name(self, instance_id: str) -> str:
        """Return the full docker-hub image name for *instance_id*."""
        return self._image_name(instance_id)

    def list_instances(
        self,
        repo_pattern: str = "sympy|requests|django|scikit-learn|pydata",
        difficulty: Union[str, List[str], Difficulty, List[Difficulty]] = Difficulty.LESS_THAN_15_MIN,
        dataset: str = DEFAULT_DATASET,
        split: str = DEFAULT_SPLIT,
        sort_by_patch_length: bool = False,
        exclude_exam_pool: bool = False,
        limit: Optional[int] = 7,
    ) -> List[str]:
        """List instance_ids matching repo pattern and difficulty.

        The result always includes the SEED_POOL tasks (verified solvable
        by reference models), then fills remaining slots from filtered
        matches up to ``limit``.

        Parameters
        ----------
        repo_pattern
            Regex pattern to match repo names (e.g., "sympy|requests").
        difficulty
            Difficulty filter(s). Can be a single value or a list.
            Values: "<15 min fix", "15 min - 1 hour", "1-4 hours", ">4 hours"
            Or use Difficulty enum: Difficulty.LESS_THAN_15_MIN, etc.
        dataset / split
            Dataset and split to search.
        sort_by_patch_length
            If True, sort instances by solution patch length (smallest first).
            This helps select easier instances for evaluation.
            If False, results are shuffled randomly.
        exclude_exam_pool
            If True, exclude all EXAM_POOL tasks from results. Use this
            for selecting bonus challenge tasks outside the predefined pool.
            When False (default), SEED_POOL tasks appear first as usual.
        limit
            Maximum number of instances to return. None for no limit.

        Returns
        -------
        List[str]
            List of instance IDs. SEED_POOL tasks appear first, followed
            by additional filtered matches.
        """
        import re
        pattern = re.compile(repo_pattern, re.IGNORECASE)

        # Normalize difficulty to a set of string values
        if isinstance(difficulty, (str, Difficulty)):
            difficulties = {difficulty.value if isinstance(difficulty, Difficulty) else difficulty}
        else:
            difficulties = {d.value if isinstance(d, Difficulty) else d for d in difficulty}

        ds = load_swebench_dataset(dataset, split)

        # Filter matching instances
        matching_instances = [
            inst
            for inst in ds
            if pattern.search(inst.get("repo", "")) and inst.get("difficulty") in difficulties
        ]

        # Sort by patch length or shuffle
        if sort_by_patch_length:
            matching_instances.sort(key=lambda x: len(x.get("patch", "")))
        else:
            random.shuffle(matching_instances)

        # Extract instance IDs
        filtered_ids = [inst["instance_id"] for inst in matching_instances]

        # Build result
        exam_set = set(EXAM_POOL)
        seed_set = set(SEED_POOL)
        if exclude_exam_pool:
            # Exclude all exam pool tasks
            result = [inst_id for inst_id in filtered_ids if inst_id not in exam_set]
        else:
            # Seed pool first, then fill with filtered matches
            result = list(SEED_POOL)
            for inst_id in filtered_ids:
                if inst_id not in seed_set:
                    result.append(inst_id)

        # Apply limit
        if limit is not None:
            result = result[:limit]

        for inst_id in result:
            print(inst_id)
        return result

    def get_instance_info(self, instance_id: str, dataset: str = DEFAULT_DATASET, split: str = DEFAULT_SPLIT):
        """Get instance details: instance_id, problem_statement, eval.sh content, dockerhub_image_name.

        Parameters
        ----------
        instance_id
            Instance ID to get info for.
        dataset / split
            Dataset and split.
        """
        ds = load_swebench_dataset(dataset, split, [instance_id])
        if not ds:
            raise SystemExit(f"Instance {instance_id} not found in dataset {dataset}/{split}")
        instance = ds[0]
        eval_script = self._get_eval_script(instance_id, dataset, split)
        dockerhub_name = self._image_name(instance_id)

        result = {
            "repo": instance["repo"],
            "instance_id": instance["instance_id"],
            "difficulty": instance.get("difficulty", ""),
            "problem_statement": instance.get("problem_statement", ""),
            "hints_text": instance.get("hints_text", ""),
            "eval_script": eval_script,
            "dockerhub_image_name": dockerhub_name,
            # "patch": instance.get("patch", ""),
        }
        # Clean \r characters and print as JSON for easy copy-paste
        result_clean = {
            k: v.replace("\r", "\n") if isinstance(v, str) else v
            for k, v in result.items()
        }
        print(json.dumps(result_clean, indent=2, ensure_ascii=False))
        
        # Print eval_script separately with actual newlines and no \r
        print("\n--- eval_script ---")
        eval_script_clean = eval_script.replace("\r", "")
        print(eval_script_clean)
        print("--- end eval_script ---\n")
        
        return result

    def get_container_id(self, instance_id: str, auto_start: bool = True):
        """Get container_id of running container for given instance_id.

        If no running container is found and auto_start is True, will pull the
        image from DockerHub if needed and start a new container.

        Parameters
        ----------
        instance_id
            Instance ID to find container for.
        auto_start
            If True (default), automatically pull image and start container if
            no running container is found.
        """
        client = docker.from_env()
        # Search for containers with instance_id in name or labels
        containers = client.containers.list(filters={"status": "running"})
        instance_id_lower = instance_id.lower()
        for container in containers:
            # Check if container name or image contains instance_id
            if instance_id_lower in container.name.lower() or instance_id_lower in str(container.image).lower():
                print(container.id, file=sys.stdout)
                return container.id
        # Also try to find by image name pattern
        img_name = self._image_name(instance_id)
        for container in containers:
            if img_name in str(container.image):
                print(container.id, file=sys.stdout)
                return container.id
        
        # No running container found
        if not auto_start:
            print("No running container found", file=sys.stderr)
            return None
        
        # Check if image exists locally, pull if needed
        print(f"No running container found for {instance_id}", file=sys.stderr)
        try:
            client.images.get(img_name)
            print(f"Image {img_name} found locally", file=sys.stderr)
        except docker.errors.ImageNotFound:
            print(f"Image {img_name} not found locally, pulling from DockerHub...", file=sys.stderr)
            self.pull(instance_id)
        
        # Start a new container
        print("Starting new container...", file=sys.stderr)
        container_id = self.start_container(instance_id, quiet=True)
        print(container_id, file=sys.stdout)
        return container_id

    def start_container(self, instance_id: str, quiet: bool = False):
        """Launch a new container session and return its container_id.

        Parameters
        ----------
        instance_id
            Instance ID to start container for.
        quiet
            If True, only print container ID to stdout, send other messages to stderr.

        Returns
        -------
        str
            Container ID that can be used to connect to the container.
        """
        client = docker.from_env()
        img = self._image_name(instance_id)
        container = client.containers.create(
            image=img,
            command="tail -f /dev/null",
            detach=True,
        )
        container.start()
        if quiet:
            # Only print container ID to stdout when called from get_container_id
            return container.id
        else:
            print(container.id)
            print(f"Container {container.id} started. Use this ID to connect with:")
            print(f"  docker exec -it {container.id} bash")
            print(f"Or use: python -m moulinette eval {instance_id} --container_id {container.id}")
            return container.id

    def pull(self, instance_id: str):
        """docker pull the eval image for *instance_id*."""
        img = self._image_name(instance_id)
        print(f"Pulling {img} ...", file=sys.stderr)
        # Redirect docker pull output to stderr so it doesn't interfere with stdout
        subprocess.run(["docker", "pull", img], check=True, stderr=sys.stderr, stdout=sys.stderr)
        print("done", file=sys.stderr)

    def shell(self, instance_id: str):
        """Run an interactive bash shell in the container (foreground)."""
        img = self._image_name(instance_id)
        subprocess.run(["docker", "run", "-it", "--rm", img, "bash"], check=False)

    def eval(
        self,
        instance_id: str,
        container_id: Optional[str] = None,
        dataset: str = DEFAULT_DATASET,
        split: str = DEFAULT_SPLIT,
        timeout: int = 1800,
        patch: Optional[str] = None,
    ) -> bool:
        """Run the SWE-bench evaluation script inside an existing or new container.

        Parameters
        ----------
        instance_id
            For example ``sympy__sympy-23534``.
        container_id
            If omitted a new container is started from the pre-built image.
        dataset / split
            Where to fetch metadata so the correct eval script can be built.
        timeout
            Seconds after which the test run is killed.
        patch
            Optional patch diff to apply before running tests.

        Returns
        -------
        bool
            True if all tests passed (FULL resolution), False otherwise.
        """
        client = docker.from_env()

        # 1. Ensure we have a running container
        if container_id:
            container = client.containers.get(container_id)
            if container.status != "running":
                container.start()
                print(f"Started existing container {container.id}")
        else:
            img = self._image_name(instance_id)
            container = client.containers.create(
                image=img,
                command="tail -f /dev/null",
                detach=True,
            )
            container.start()
            print(f"Started container {container.id}")

        # 2. Get eval script
        eval_script = self._get_eval_script(instance_id, dataset, split)

        # 3. Apply patch if provided
        if patch:
            patch_file = Path("/tmp/patch.diff")
            patch_file.write_text(patch)
            copy_to_container(container, patch_file, Path(DOCKER_PATCH))
            # Try to apply patch
            GIT_APPLY_CMDS = [
                "git apply --verbose",
                "git apply --verbose --reject",
                "patch --batch --fuzz=5 -p1 -i",
            ]
            applied = False
            for git_apply_cmd in GIT_APPLY_CMDS:
                result = container.exec_run(
                    f"{git_apply_cmd} {DOCKER_PATCH}",
                    workdir=DOCKER_WORKDIR,
                    user=DOCKER_USER,
                )
                if result.exit_code == 0:
                    print(f"Patch applied successfully using: {git_apply_cmd}")
                    applied = True
                    break
            if not applied:
                print(f"Warning: Failed to apply patch. Output: {result.output.decode('utf-8')}")

        # 4. Copy script into container and execute
        test_spec = self._get_test_spec(instance_id, dataset, split)
        try:
            tmp = Path("/tmp/eval.sh")
            tmp.write_text(eval_script)
            copy_to_container(container, tmp, Path("/eval.sh"))
            container.exec_run("chmod +x /eval.sh")
            out, timed_out, runtime = exec_run_with_timeout(container, "/bin/bash /eval.sh", timeout)
            print(out)
            print(f"Runtime: {runtime:.1f}s")
            if timed_out:
                print("Timed-out!")
                return False

            # 5. Grade the evaluation using SWE-bench's grading logic
            # Save output to temp file for parsing
            log_file = Path("/tmp/test_output.txt")
            log_file.write_text(out)

            # Parse test results
            eval_status_map, found = get_logs_eval(test_spec, str(log_file))
            if not found:
                print("Failed to parse test output or tests did not run")
                return False

            # Check for required test markers
            if START_TEST_OUTPUT not in out or END_TEST_OUTPUT not in out:
                print("Test output markers not found")
                return False

            # Get evaluation report
            eval_ref = {
                KEY_INSTANCE_ID: test_spec.instance_id,
                FAIL_TO_PASS: test_spec.FAIL_TO_PASS,
                PASS_TO_PASS: test_spec.PASS_TO_PASS,
            }

            eval_type = (
                EvalType.FAIL_ONLY
                if test_spec.repo in FAIL_ONLY_REPOS
                else EvalType.PASS_AND_FAIL
            )

            report = get_eval_tests_report(eval_status_map, eval_ref, eval_type=eval_type)
            resolution_status = get_resolution_status(report)

            # Return True only if FULL resolution (all tests pass)
            passed = resolution_status == ResolvedStatus.FULL.value
            print(f"Resolution status: {resolution_status}")
            print(f"Evaluation passed: {passed}")
            return passed

        finally:
            # Cleanup: stop and remove container if we created it
            if not container_id:
                container.stop()
                container.remove()
                print(f"Cleaned up container {container.id}")


def _fire_main():
    """Entry point for moulinette_swebench CLI."""
    import fire
    fire.Fire(InteractSweBench)

