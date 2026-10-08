import argparse
import sys
import readline
from mbpp import file_temp, executer_code

def main():
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Fichier JSON")
    parser.add_argument("--mcp-stdio", type=str)
    parser.add_argument("--mcp-server", type=str)
    args = parser.parse_args()
    """
    while True:
        try:
            code = input(">>> ")
            
            if code.strip() == "exit":
                break
            if not code.strip():
                continue
            
            fichier = file_temp(code, "") 
            resultat = executer_code(fichier)
            
            if resultat["output"]:
                print(f"Answer: {resultat["output"].strip()}")
            if resultat["error"]:
                print(resultat["error"].strip(), file=sys.stderr)
                
        except EOFError:
            print("\n(Ctrl+D)")
            break
        except KeyboardInterrupt:
            print("\n(Ctrl+C)")
            break

if __name__ == "__main__":
    main()