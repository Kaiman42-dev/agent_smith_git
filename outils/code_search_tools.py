import ast

from outils import testbed

# Les recherches ne parcourent que le dépôt (TESTBED_PATH), liens symboliques compris (AS-41)


 # Cherche un mot precis dans un fichier (file_pattern pour chercher dans des fichier precis *.py, *.txt)
def search_code(pattern, file_pattern):
    try:
        dossier = testbed.racine()
    except PermissionError as err:
        return f"Error: {err}"
    res = []
    try:
        for f in dossier.rglob(file_pattern):
            if f.is_file() and testbed.dans_le_depot(f, dossier):
                try:
                    with f.open("r", encoding="utf-8") as fichier:
                        for nbr_ligne, ligne in enumerate(fichier, start=1):
                            if pattern in ligne:
                                contenu = ligne.rstrip('\r\n')
                                res.append(f"{testbed.chemin_affiche(f)}:{nbr_ligne} {contenu}")
                except UnicodeDecodeError:
                    pass
        return "\n".join(res) if res else "no results"
        
    except Exception as err:
        return f"Search error: {err}"


# cherher une fonction ou class precis
def search_function_or_class_definition_in_code(name):
    try:
        dossier = testbed.racine()
    except PermissionError as err:
        return f"Error: {err}"
    
    results = []
    try:
        for filepath in dossier.rglob("*.py"):
            if filepath.is_file() and testbed.dans_le_depot(filepath, dossier):
                with open(filepath, 'r', encoding="utf-8") as file_obj:
                    res = file_obj.read()
                    try:
                        tree = ast.parse(res)
                    except SyntaxError:
                        continue
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                            numero_ligne = node.lineno
                            lines = res.splitlines()
                            line_content = lines[numero_ligne - 1].strip()
                            results.append(f"{testbed.chemin_affiche(filepath)}:{numero_ligne} {line_content}")
                            
        return "\n".join(results) if results else "No results found."
        
    except Exception as err:
        return f"Error: {err}"


#Cherche tous les appels d'une fonction precis
def find_references(name, filepath, line):
    try:
        dossier = testbed.racine()
    except PermissionError as err:
        return f"Error: {err}"
    results = []
    try:
        for current_filepath in dossier.rglob("*.py"):
            if not (current_filepath.is_file() and testbed.dans_le_depot(current_filepath, dossier)):
                continue
            with open(current_filepath, 'r', encoding="utf-8") as file_obj:
                res = file_obj.read()
                try:
                    tree = ast.parse(res)
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    found = False
                    if isinstance(node, ast.Name) and node.id == name:
                        found = True
                    elif isinstance(node, ast.Attribute) and node.attr == name:
                        found = True
                    if found:
                        numero_ligne = getattr(node, 'lineno', None)
                        if numero_ligne is not None:
                            lines = res.splitlines()
                            line_content = lines[numero_ligne - 1].strip()
                            formatted_result = f"{testbed.chemin_affiche(current_filepath)}:{numero_ligne} {line_content}"
                            if formatted_result not in results:
                                results.append(formatted_result)
        if results:
            return "\n".join(results)
        else:
            return "no result"
    except Exception as e:
        return f"Error {e}"


"""
if __name__ == "__main__":
	print(search_function_or_class_definition_in_code("calculate_total"))
"""