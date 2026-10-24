import subprocess

from outils import testbed

# Les commandes tournent dans le conteneur de la tâche, ou dans TESTBED_PATH pendant
# les tests isolés : jamais ailleurs sur l'hôte (voir outils/testbed.py)

def run_tests(eval_script_path="eval.sh"):
    try:
        result = testbed.executer(f"bash {eval_script_path}", None, 300)
        return f"Exit code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
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
