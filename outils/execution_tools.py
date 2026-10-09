import os
import subprocess

#verification du code faite par loutil (moulinette)
def run_tests(eval_script_path="eval.sh"):
    testbed_path = os.environ.get("TESTBED_PATH", "/testbed")
    try:
        result = subprocess.run(
            ["bash", eval_script_path], 
            cwd=testbed_path, 
            capture_output=True, 
            text=True, 
            timeout=300
        )
        return f"Exit code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Timeout after 300 seconds."
    except Exception as err:
        return f"Error: {err}"

# compare le fichier avant et apres la modification faite par l'outil
def get_patch():
    testbed_path = os.environ.get("TESTBED_PATH", "/testbed")
    try:
        result = subprocess.run(
            ["git", "-c", "core.fileMode=false", "diff"],
            cwd=testbed_path,
            capture_output=True,
            text=True
        )
        return result.stdout if result.stdout else "No changes found."
    except Exception as err:
        return f"Error: {err}"

# permet de regarde les text ou erreur dans le terminal example: (ls, python script.py)
def run_command(command, workdir=None):
    if workdir is None:
        workdir = os.environ.get("TESTBED_PATH", "/testbed")
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=120
        )
        return f"Exit code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Timeout after 120 seconds."
    except Exception as err:
        return f"Error: {err}"