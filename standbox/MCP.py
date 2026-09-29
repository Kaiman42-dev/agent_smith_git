import subprocess
from swe_bench import run_in_docker


# outil recherche de code
def search_code(pattern, file_pattern):
    commande = f"grep -rnw --include='{file_pattern}' '{pattern}' ."
    return run_in_docker(commande)

def search_function_or_class_definition_in_code(name):
    commande = f"grep -rnE '(def |class ){name}\\b' ."
    return run_in_docker(commande)

def find_references(name, filepath, line):
    commande = f"grep -rn '\\b{name}\\b' ."
    return run_in_docker(commande)



# outils executions
def run_tests():
    eval_script = "ta_variable_eval_script_recuperee_du_json" 
    return run_in_docker(eval_script)

def get_patch():
    commande = "git -c core.fileMode=false diff"
    return run_in_docker(commande)

def run_command(command, workdir):
    return run_in_docker(command, workdir=workdir)

# test
"""
if __name__ == "__main__":
	resultat = search_function_or_class_definition_in_code("Basic")
	print(resultat)
"""