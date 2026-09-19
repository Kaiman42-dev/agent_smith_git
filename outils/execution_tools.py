from pathlib import Path
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
        return {
            "success": result.returncode == 0, 
            "stdout": result.stdout, 
            "stderr": result.stderr, 
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Timeout"
        }
    except Exception as e:
        return {
            "success": False, 
            "error": f"Error system {str(e)}"
        }


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
        return result.stdout
        
    except Exception as e:
        return f"Error: {str(e)}"


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
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
        
    except subprocess.TimeoutExpired:
        return {
            "error": "Timeout,
            "exit_code": -1
        }
        
    except Exception as e:
        return {
            "error": f"Error systme {str(e)}",
            "exit_code": -1
        }