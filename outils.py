from pathlib import Path
import os

### Outils de système de fichiers :


def read_file(filepath): # compte le nombre de ligne dun fichier 
	try:
		with open(filepath, 'r', encoding="utf-8") as f:
			ligne = sum(1 for _ in f)
			return (ligne)
	except:
		return "Error"
	
def edit_file(filepath, old_str, new_str): # remplace un ancien mot par un nouveaux dans un fichier
	try:
		with open(filepath, 'r', encoding="utf-8") as f:
			text = f.read()
			replacee = text.replace(old_str, new_str)
			with open(filepath, 'w', encoding="utf-8") as f:
				f.write(replacee)
	except:
		return "Error"

def search_in_file(filepath, s): # cherche un mot dans un fichier
	try:
		with open(filepath, 'r', encoding="utf-8") as f:
			text = f.read()
			if s in text:
				print(f"mot trouve: {s}")
				return s
	except:
		return "Error"


def list_files(directory, pattern): # cherche des fichier specifique dans un dossier (pattern(*.py , *.txt ....))
	dossier = Path(directory)
	if dossier.exists():
		for f in dossier.glob(pattern):
			return f
	else:
		return "Error"


### Outils de recherche de code

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

def search_function_or_class_definition_in_code(name)

def find_references(name, filepath, line) :


if __name__ == "__main__":
	print(search_code("hello", "*.txt"))