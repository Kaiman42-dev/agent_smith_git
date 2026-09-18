from pathlib import Path
import os


def search_code(pattern, file_pattern):
	testbed = os.environ.get("TESTBED_PATH", "./testbed")
	dossier = Path(testbed)
	if not dossier.exists():
		return "Error"
	all_file = ""
	try:
		for f in dossier.glob(file_pattern):
			with f.open("r", encoding="utf-8") as fichier:
				for nbr_ligne, ligne in enumerate(fichier):
					if pattern in ligne:
						return(f"File : {f.name} | Ligne : {nbr_ligne + 1} | mot : {pattern}")
	except:
		return "Error" 


def search_function_or_class_definition_in_code(name):
	pass

def find_references(name, filepath, line) :
	pass