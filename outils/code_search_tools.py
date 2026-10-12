from pathlib import Path
import os
import ast
import re


 # Cherche un mot precis dans un fichier (file_pattern pour chercher dans des fichier precis *.py, *.txt)
def search_code(pattern, file_pattern):
    testbed = os.environ.get("TESTBED_PATH", "./testbed")
    dossier = Path(testbed)
    
    if not dossier.exists():
        return f"Erreur : le dossier {testbed} n'existe pas."
    res = []
    try:
        for f in dossier.rglob(file_pattern):
            if f.is_file():
                try:
                    with f.open("r", encoding="utf-8") as fichier:
                        for nbr_ligne, ligne in enumerate(fichier, start=1):
                            if pattern in ligne:
                                res.append(f"{f.absolute()}:{nbr_ligne} {ligne.rstrip('\r\n')}")
                except UnicodeDecodeError:
                    pass
        return "\n".join(res) if res else "no results"
        
    except Exception as err:
        return f"Search error: {err}"


# cherher une fonction ou class precis
def search_function_or_class_definition_in_code(name):
    testbed = os.environ.get("TESTBED_PATH", "./testbed")
    dossier = Path(testbed)
    
    if not dossier.exists():
        return f"Error: directory {testbed} does not exist."
        
    results = []
    try:
        for filepath in dossier.rglob("*.py"):
            if filepath.is_file():
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
                            results.append(f"{filepath.absolute()}:{numero_ligne} {line_content}")
                            
        return "\n".join(results) if results else "No results found."
        
    except Exception as err:
        return f"Error: {err}"


#Cherche tous les appels d'une fonction precis
def find_references(name, filepath, line):
    testbed = os.environ.get("TESTBED_PATH", "./testbed")
    dossier = Path(testbed)
    if not dossier.exists():
        return "Error"
    results = []
    try:
        for current_filepath in dossier.rglob("*.py"):
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
                            formatted_result = f"{current_filepath.absolute()}:{numero_ligne} {line_content}"
                            if formatted_result not in results:
                                results.append(formatted_result)
        if results:
            return "\n".join(results)
        else:
            return "no result"
    except Exception as e:
        return "Error {e}"


"""
if __name__ == "__main__":
	print(search_function_or_class_definition_in_code("calculate_total"))
"""