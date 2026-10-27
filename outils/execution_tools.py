import subprocess

from outils import testbed

# Les commandes tournent dans le conteneur de la tâche, ou dans TESTBED_PATH pendant
# les tests isolés : jamais ailleurs sur l'hôte (voir outils/testbed.py)

MAX_OUTPUT_LENGTH = 4000

def output_tests(output: str) ->str:
    """Extract the test output from the evaluation script output."""
    res = ""
    start = output.find(">>>>> Start Test Output")
    end = output.rfind(">>>>> End Test Output")
    if start == -1 or end == -1:
        res = output
    else:
        a = output.find("\n", start)
        b = output.rfind("\n", 0, end)
        res = output[a + 1 : b + 1]
    if len(res) > MAX_OUTPUT_LENGTH:
        return "Output too long, showing last 4000 characters:\n" + res[-MAX_OUTPUT_LENGTH:]

    return res

def run_tests(eval_script_path="eval.sh"):
    """Run the task's evaluation script (eval.sh at the repository root)."""
    try:
        result = testbed.executer(f"bash {eval_script_path} 2>&1", None, 300)
        return f"\nTests outputs: {output_tests(result.stdout)}\n"
    except subprocess.TimeoutExpired:
        return "Error: Timeout after 300 seconds."
    except Exception as err:
        return f"Error: {err}"

def get_patch():
    try:
        result = testbed.executer("git -c core.fileMode=false diff", None, 120)
        return result.stdout if result.stdout else "No changes found."
    except Exception as err:
        return f"Error: {err}"

def run_command(command, workdir=None):
    try:
        result = testbed.executer(command, workdir, 120)
        return f"Exit code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Timeout after 120 seconds."
    except Exception as err:
        return f"Error: {err}"
