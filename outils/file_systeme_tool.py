from pathlib import Path
import os


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

def list_files(directory, pattern): # cherche des fichier specifique dans un dossier (pattern(*.py , *.txt ....))
	dossier = Path(directory)
	if dossier.exists():
		for f in dossier.glob(pattern):
			return f
	else:
		return "Error"