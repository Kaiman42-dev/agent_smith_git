from sandbox.Parsing import p_SWE
import subprocess
import os


import json
import os

def image_SWE(chemin_task_json: str) -> str:
    if not os.path.exists(chemin_task_json):
        raise FileNotFoundError(f"Le fichier de tâche est introuvable : {chemin_task_json}")
        
    try:
        with open(chemin_task_json, "r") as f:
            data = json.load(f)
            
        image_name = data.get("dockerhub_image_name")
        if not image_name:
            raise ValueError("Clé 'dockerhub_image_name' manquante dans le JSON.")
            
        return image_name
    except Exception as e:
        raise RuntimeError(f"Erreur lors de la lecture de l'image SWE-bench : {e}")


def run_in_docker(outils, workdir="/testbed"):

	container_id = os.environ.get("CONTAINER_ID")
	if not container_id:
		return "Errror: CONTAINER_ID"
	
	base_cmd = ["docker", "exec", "-w", workdir, container_id, "bash", "-c", outils]
	result = subprocess.run(base_cmd, capture_output=True, text=True)
	
	return result.stdout if result.returncode == 0 else result.stderr

"""
if __name__ == "__main__":
    print("Start conteneur...")
    id_du_conteneur = image_SWE()
    
    os.environ["CONTAINER_ID"] = id_du_conteneur
    
    resultat_1 = run_in_docker("ls -la")
    print(resultat_1)
    
    resultat_2 = run_in_docker("python isympy.py --help")
    print(resultat_2)
    
    print("close conteneur...")
    subprocess.run(["docker", "rm", "-f", id_du_conteneur])
"""