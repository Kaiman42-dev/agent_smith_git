from Parsing import p_SWE
import subprocess


def SWE():
	cls = p_SWE("../Json/task.json")
	image = cls.docker_image
	print(image)
	result = subprocess.run(
    ["docker", "run", "--rm", image],
    capture_output=True,
    text=True
	)
	return result

if __name__ == "__main__":
	print(SWE())