from Parsing import p_SWE
import subprocess


def image_SWE(): # pull le image-docker 
	cls = p_SWE("../Json/task.json")
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
	
	print("returncode:", result.returncode)
	print("stdout:", repr(result.stdout))
	print("stderr:", repr(result.stderr))


def proble():
	try:
		cls = p_SWE("../Json/task.json")
		problem_statement = cls.problem_statement
		return problem_statement
	except:
		return "Error"


def mcp():
	id = image_SWE()
	quest = proble()
	try:
		result = subprocess.run( # execute la question dans le id du conteneur 
			["docker", "exec", "-w", "/testbed", id, "ls", "-la"],
			capture_output=True,
			text=True
			)
	except:
		return "Error"

	print("return code:", result.returncode)
	print("stdout:", result.stdout)
	print("stderr:", result.stderr)

if __name__ == "__main__":
	print(mcp)