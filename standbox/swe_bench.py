from Parsing import p_SWE
import subprocess


def image_SWE():
	cls = p_SWE("Json/task.json")
	image = cls.docker_image
	print(image)
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
		print(id_conteneur)
		return id_conteneur
	except:
		return "Error"


def run_in_docker(commande_bash, workdir="/testbed"):

	CONTAINER_ID = image_SWE() # execute
	if CONTAINER_ID is None:
		return
	base_cmd = ["docker", "exec", "-w", workdir, CONTAINER_ID, "bash", "-c", commande_bash]
	result = subprocess.run(base_cmd, capture_output=True, text=True)
	
	return result.stdout if result.returncode == 0 else result.stderr



"""
def proble():
	try:
		cls = p_SWE("../Json/task.json")
		problem_statement = cls.problem_statement
		return problem_statement
	except:
		return "Error"
"""