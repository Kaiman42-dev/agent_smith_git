import ast

from outils import testbed

# Chaque chemin donné par le LLM passe par testbed.chemin_local : rien hors du dépôt (AS-41)


def read_file(filepath: str, start_line: int, end_line: int): # compte le nombre de ligne dun fichier
	info = ""
	try:
		with open(testbed.chemin_local(filepath), 'r', encoding="utf-8") as f:
			for l, e in enumerate(f, start=1):
				if l >= start_line and l <= end_line:
					info += (f"{l}: {e}")
			return info.strip()
	except Exception as err:
		return f"Error file: '{filepath}': {err}"


def edit_file(filepath, old_str, new_str): # remplace un ancien mot par un nouveaux dans un fichier
    try:
        chemin = testbed.chemin_local(filepath)
        with open(chemin, 'r', encoding="utf-8") as f:
            text = f.read()
            
        count = text.count(old_str)
        
        if count == 0:
            return "Error: old_str not found in the file."
        elif count > 1:
            return f"Error: old_str found {count} times. Please be more specific."
            
        replacee = text.replace(old_str, new_str)
        
        with open(chemin, 'w', encoding="utf-8") as f:
            f.write(replacee)

        message = "File updated successfully."

        # Vérification de la syntaxe pour avertir le LLM
        if chemin.suffix == ".py":
            try:
                ast.parse(replacee)
            except SyntaxError as e:
                message += f"\n[WARNING] Syntax error introduced: {e.msg} at line {e.lineno}. Please fix it."
                
        return message
    except Exception as err:
        return f"Error: {err}"



def list_files(directory, pattern): # cherche des fichier specifique dans un dossier (pattern(*.py , *.txt ....))
    try:
        dossier = testbed.chemin_local(directory)
        base = testbed.racine()
    except PermissionError as err:
        return f"Error: {err}"
    res = []

    if dossier.exists():
        try:
            for f in dossier.rglob(pattern):
                # un lien symbolique (ou un pattern avec ..) ne doit pas faire sortir du dépôt
                if f.is_file() and testbed.dans_le_depot(f, base):
                    res.append(testbed.chemin_affiche(f))
            return "\n".join(res) if res else "No files found."
        except Exception as err:
            return f"Error: {err}"
    else:
        return f"Error: the directory {directory} does not exist."


"""
if __name__ == "__main__":
	print(read_file("tet.txt", 4, 6))
"""