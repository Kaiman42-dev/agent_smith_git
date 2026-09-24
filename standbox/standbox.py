from pydantic import BaseModel, Field
from multiprocessing import Process
from typing import List
import os
import tempfile
import subprocess
import sys



# La configuration de la stanbox
class Conifg_Sandbox(BaseModel):
    
    max_execution_time_seconds: int = 30
    
    max_memory_mb: int = 512

    allowed_directories: List[str] = Field(default_factory=lambda: [
			"/testbed", "/tmp/agent"
		])
    
    authorized_imports: List[str] = Field(default_factory=lambda: [
        "math", "math.*", "collections", "collections.*",
        "itertools", "re", "json", "typing", "typing.*",
        "functools", "operator", "heapq", "bisect", "copy",
        "string", "random", "datetime", "datetime.*",
        "array", "cmath",
    ])
         

def mbpp(code_ia, data_mbpp): # cree le fichier temporaire et ajoute le code de ia et les test a faire
    #Info_config = Conifg_Sandbox()
    try:
        with tempfile.NamedTemporaryFile(mode='w+', suffix=".py", delete=False) as f:
            name_file = f.name
            
            f.write(code_ia)
            f.write("\n\n")
            f.write(data_mbpp)
            return (name_file)
            
            f.seek(0) # remonte en haut du fichier
            
    except:
        return f"Error"
    
    os.remove(name_file)


def executer_code(fichier, config=None): # executer le fichier temporaire

    if config is None:
        config = Conifg_Sandbox()

    try:
        process = subprocess.run( # lit le fichier et execute tout seul !
            [sys.executable, fichier],
            capture_output=True,
            text=True,
            timeout=config.max_execution_time_seconds
        )

        if process.returncode == 0: # si il a reussi a executer
            return {
                "success": True,
                "output": process.stdout,
                "error": process.stderr,
                "returncode": process.returncode
            }

        return { 
            "success": False,
            "output": process.stdout,
            "error": process.stderr,
            "returncode": process.returncode
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": (
                f"time out"
                f"{config.max_execution_time_seconds} secondes"
            ),
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

    fichier = mbpp(code_ia, data_mbpp)

    if fichier is None:
        return "Error"

    try:
        resultat = executer_code(fichier, config)
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



"""
Lecture : Tu prends un exercice du dataset.

Génération : Le LLM écrit une fonction en Python pour résoudre l'exercice.

Assemblage : Tu colles le code du LLM et les tests (les réponses) du dataset dans ton fichier temporaire.

Vérification : La Sandbox exécute ce fichier en toute sécurité (avec subprocess.run) . Si aucune erreur ne s'affiche, le code du LLM est correct !

Tu passes à la question suivant
"""

"""
def execution_file():
    fichier = mbpp("def ft_sub(a, b):\n    return a - b", "assert ft_sub(5, 2) == 3")
    process = subprocess.Popen([sys.executable, fichier])
    process.wait()
    print("Le fichier est terminé")
    try:
        with open(fichier, 'r') as f:
            c = f.read()
            return c
    except:
        return "Error"
"""


# MODE MBBP EXPLICATION
"""
Mode mbbp: CLI terminal ("python main.py --mode mbpp") pour lancer le programe, charge les 1000 qustion et envoie 1 par 1 au llm qui return une string 
du code qu'il pense etre juste, pour tester le code on cree un fichier temporaire dans la standbox ou on mais le code de ia et X test lier a la question du prompt du debut
execution avec import subprocess qui va executer le fichier en securite en respectant les import le time out et la ram max si il reussi les 4 test lie a la question cest que le code de ia etait bon 
"""


