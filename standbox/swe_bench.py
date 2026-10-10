from Parsing import p_SWE
import subprocess
import os


def image_SWE():
	"""
	cls = p_SWE("Json/task.json")
	image = cls.docker_image
	print(image)
	"""
	image = "swebench/sweb.eval.x86_64.sympy_1776_sympy-23534:latest"
	try:
		subprocess.run( # telecharge image docker
			["docker", "pull", image],
			capture_output=True,
			text=True,
			check=True
			)
		result = subprocess.run( # run docker
			["docker", "run", "-d", image, "tail", "-f", "/dev/null"],
			capture_output=True,
			text=True,
			check=True
			)
		id_conteneur = result.stdout.strip()
		return id_conteneur
	except:
		return "Error"


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