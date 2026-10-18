import os
import subprocess

def _executer_commande(cmd: str, workdir: str, timeout: int) -> subprocess.CompletedProcess:
    container_id = os.environ.get("CONTAINER_ID")
    if container_id:
        docker_cmd = ["docker", "exec", "-w", workdir, container_id, "bash", "-c", cmd]
        return subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
    else:
        return subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True, timeout=timeout)

def run_tests(eval_script_path="eval.sh"):
    testbed_path = os.environ.get("TESTBED_PATH", "/testbed")
    try:
        result = _executer_commande(f"bash {eval_script_path}", testbed_path, 300)
        return f"Exit code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Timeout after 300 seconds."
    except Exception as err:
        return f"Error: {err}"

def get_patch():
    testbed_path = os.environ.get("TESTBED_PATH", "/testbed")
    try:
        result = _executer_commande("git -c core.fileMode=false diff", testbed_path, 120)
        return result.stdout if result.stdout else "No changes found."
    except Exception as err:
        return f"Error: {err}"

def run_command(command, workdir=None):
    if workdir is None:
        workdir = os.environ.get("TESTBED_PATH", "/testbed")
    try:
        result = _executer_commande(command, workdir, 120)
        return f"Exit code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Timeout after 120 seconds."
    except Exception as err:
        return f"Error: {err}"