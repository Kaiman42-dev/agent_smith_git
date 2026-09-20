from pydantic import BaseModel, Field
from typing import List
import os
import tempfile


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
         

def mbpp(code_ia, data_mbpp):
    Info_config = Conifg_Sandbox()
    try:
        with tempfile.NamedTemporaryFile(mode='w+', suffix=".py", delete=False) as f:
            name_file = f.name 
            
            f.write(code_ia)
            f.write("\n\n")
            f.write(data_mbpp)
            
            f.seek(0) # remonte en haut du fichier
            print(f.read())
            
    except:
        return f"Error"
    
    os.remove(name_file)

if __name__ == "__main__":
    mbpp("def ft_sub(a, b):\n    return a - b", "assert ft_sub(5, 2) == 3")



"""
Lecture : Tu prends un exercice du dataset.

Génération : Le LLM écrit une fonction en Python pour résoudre l'exercice.

Assemblage : Tu colles le code du LLM et les tests (les réponses) du dataset dans ton fichier temporaire.

Vérification : La Sandbox exécute ce fichier en toute sécurité. Si aucune erreur ne s'affiche, le code du LLM est correct !

Tu passes à la question suivant
"""