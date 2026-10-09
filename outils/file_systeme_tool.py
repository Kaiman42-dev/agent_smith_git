from pathlib import Path
import os


def read_file(filepath: str, start_line: int, end_line: int): # compte le nombre de ligne dun fichier
	info = ""
	try:
		with open(filepath, 'r', encoding="utf-8") as f:
			for l, e in enumerate(f, start=1):
				if l >= start_line and l <= end_line:
					info += (f"{l}: {e}")
			return info.strip()
	except Exception as err:
		return f"Error file: '{filepath}': {err}"


def edit_file(filepath, old_str, new_str): # remplace un ancien mot par un nouveaux dans un fichier
    try:
        with open(filepath, 'r', encoding="utf-8") as f:
            text = f.read()
            
        count = text.count(old_str)
        
        if count == 0:
            return "Error: old_str not found in the file."
        elif count > 1:
            return f"Error: old_str found {count} times. Please be more specific."
            
        replacee = text.replace(old_str, new_str)
        
        with open(filepath, 'w', encoding="utf-8") as f:
            f.write(replacee)
            
        return "File updated successfully."
    except Exception as err:
        return f"Error: {err}"



def list_files(directory, pattern): # cherche des fichier specifique dans un dossier (pattern(*.py , *.txt ....))
    dossier = Path(directory)
    res = []
    
    if dossier.exists():
        try:
            for f in dossier.rglob(pattern):
                if f.is_file():
                    res.append(str(f.absolute()))
            return "\n".join(res) if res else "No files found."
        except Exception as err:
            return f"Error: {err}"
    else:
        return f"Error: the directory {directory} does not exist."


"""
if __name__ == "__main__":
	print(read_file("tet.txt", 4, 6))
"""