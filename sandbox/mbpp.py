from pickle import NONE
from .config_sandbox import Conifg_Sandbox
from pydantic import BaseModel, Field
from multiprocessing import Process
from typing import List
import os
import tempfile
import subprocess
import sys

def file_temp(code_ia, data_mbpp, config=None):
    if config is None:
        config = Conifg_Sandbox()
    try:
        with tempfile.NamedTemporaryFile(mode='w+', suffix=".py", delete=False) as f:
            name_file = f.name
            
            f.write(config.text_config())
            f.write("\n\n")
            f.write(code_ia)
            f.write("\n\n")
            f.write(data_mbpp)
            return name_file

    except Exception:
        return "Error"

def run_sandbox(fichier, config=None):

    if config is None:
        config = Conifg_Sandbox()

    MAX_OBSERVATION = 5000
    try:
        process = subprocess.run( # lit le fichier et execute
            [sys.executable, fichier],
            capture_output=True,
            text=True,
            timeout=config.max_execution_time_seconds
        )
        output = process.stdout
        if len(output) > MAX_OBSERVATION:
            output = output[:MAX_OBSERVATION] + "[cut-off text too long]"

        if process.returncode == 0: # si il a reussi a executer
            return {
                "success": True,
                "output": output,
                "error": process.stderr,
                "returncode": process.returncode
            }

        return { 
            "success": False,
            "output": output,
            "error": process.stderr,
            "returncode": process.returncode
        }

    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        
        if len(out) > MAX_OBSERVATION:
            out = out[:MAX_OBSERVATION] + "[cut-off text too long]"
            
        return {
            "success": False,
            "output": out,
            "error": f"Timeout ({config.max_execution_time_seconds}s)",
            "returncode": -1
        }

    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "returncode": -1
        }


def run_test(code_ia, data_mbpp): # run

    config = Conifg_Sandbox()

    fichier = file_temp(code_ia, data_mbpp)

    if fichier is None:
        return "Error"

    try:
        resultat = run_sandbox(fichier, config)
        return resultat

    finally:
        if os.path.exists(fichier):
            os.remove(fichier)


if __name__ == "__main__":

    code_ia = """
def ft_sub(a, b):
    return a - b
"""

    data_mbpp = """
assert ft_sub(5, 2) == 3
print(ft_sub(5, 2))
"""

    resultat = run_test(code_ia, data_mbpp)

    print("Réussi :", resultat["success"])
    print("Output :", resultat["output"])
    print("Erreur :", resultat["error"])
    print("Code retour :", resultat["returncode"])



# MODE MBBP EXPLICATION
"""
Mode mbbp: CLI terminal ("python main.py --mode mbpp") pour lancer le programe, envoie 1 question au au llm (question dans le json) qui return une string 
du code qu'il pense etre juste, pour tester le code on cree un fichier temporaire dans la standbox ou on mais le code de ia et X test lier a la question du prompt du debut
execution avec import subprocess qui va executer le fichier en securite en respectant les import le time out et la ram max si il reussi les X test lie a la question cest que le code de ia etait bon (test de la question dans le json)

ex: question.json
[
	(question) "task_definition": "Write a function that returns the sum of two integers.",
    
    (test)"test_list": [
    "assert add(2, 2) == 4",
    "assert add(-1, 1) == 0",
    "assert add(10, 5) == 15"
  ]

"""

