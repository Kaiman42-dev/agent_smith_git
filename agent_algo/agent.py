import json
import urllib.request
import urllib.error
from dotenv import load_dotenv
import os
import sys
import io
import inspect
import logging
import traceback
import contextlib
from pathlib import Path

# permet d'importer Extraction_llm et outils/ qui sont a la racine du projet
sys.path.append(str(Path(__file__).resolve().parent.parent))

from Extraction_llm import p_mardown
from outils.file_systeme_tool import read_file, edit_file, list_files
from outils.code_search_tools import search_code, search_function_or_class_definition_in_code, find_references
from outils.execution_tools import run_tests, get_patch, run_command

# les outils que le llm peut appeler dans son code
OUTILS = {f.__name__: f for f in (
    read_file, edit_file, list_files,
    search_code, search_function_or_class_definition_in_code, find_references,
    run_tests, get_patch, run_command,
)}

MAX_OBSERVATION = 5000  # sert a couper les observations trop longues pour ne pas exploser le contexte

PROMPT_SYSTEME = f"""Tu es un agent qui resout des taches de code.
A chaque tour :
1. Thought: tu expliques ce que tu vas faire.
2. Code: tu ecris UN bloc ```python ... ``` qui sera execute. Utilise print() pour voir les resultats.
3. Tu recois ensuite une Observation avec ce qui a ete affiche (ou l'erreur).
Les variables sont conservees d'un tour a l'autre.

Outils disponibles (deja importes) :
{chr(10).join(f"- {nom}{inspect.signature(f)}" for nom, f in OUTILS.items())}

Quand tu as la reponse finale, reponds SANS bloc ```python```, en commencant par "Final Answer:".
"""


def executer_code(code, namespace):
    """execute le code du llm et renvoie ce qui a ete affiche (stdout + erreurs)"""
    sortie = io.StringIO()
    try:
        with contextlib.redirect_stdout(sortie):
            exec(code, namespace)
    except Exception:
        sortie.write(traceback.format_exc(limit=-1))
    observation = sortie.getvalue() or "(le code n'a rien affiche, utilise print())"
    return observation[:MAX_OBSERVATION]

class ClientLLM:
    def __init__(self, adress, modele, key):
        self.adress = adress
        self.modele = modele
        self.key = key
    
    def appel_llm(self, messages):
        """Envoie la conversation au modèle et renvoie son message de réponse"""
        corps = json.dumps(
            {"model": self.modele, "messages": messages, "stream": False }
        ).encode()
        requete = urllib.request.Request(
            self.adress, data=corps, headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"} # c'est ce qui est envoyé a l'API, avec la clé
        )
        i = 0
        while i <= 5:
            try:
                with urllib.request.urlopen(requete, timeout=300) as response: #envoie la requete au serveur
                    return json.load(response)["choices"][0]["message"] # retourne la reponse du serveur
            except urllib.error.HTTPError as e:
                logging.error(f"Echec HTTP. Code {e.code}, Raison {e.reason}")
                # je distingue les erreurs 400 et 404 pour ne pas réessayer inutilement (erreures de requete ou ressource non trouvée)
                if e.code in(400, 404): 
                    return None
                i = i + 1
                pass
            except urllib.error.URLError as e:
                logging.error(f"Echec URL. Raison {e.reason}")
                i = i + 1
                pass
        return None

class Agent:
    def __init__(self, question, max_tours, client):
        self.question = question
        self.max_tours = max_tours
        self.client = client

    def agent_algo(self) -> tuple[str, list[str]]:
        """fait tourner la boucle think->act->observe jusqu'a la reponse"""
        memoire=[
            {"role": "system", "content": PROMPT_SYSTEME},
            {"role": "user", "content": self.question}
        ]
        trace: list[str] = []
        namespace = dict(OUTILS)  # garde les variables du llm d'un tour a l'autre

        for _ in range(self.max_tours):
            message = self.client.appel_llm(memoire) # parti de thinking
            if message is None:  # si le llm ne repond pas on sort de la boucle
                return "le llm ne repond pas", trace
            contenu = message.get("content") or ""
            memoire.append({"role": "assistant", "content": contenu}) # je sauvegarde la reponse du llm en mémoire
            trace.append(contenu)

            code = p_mardown(contenu)  # parti code
            if code is None:  # pas de code = reponse finale
                return contenu.split("Final Answer:")[-1].strip(), trace

            observation = executer_code(code, namespace)  # parti observe
            memoire.append({"role": "user", "content": f"Observation:\n{observation}"})
            trace.append(f"Observation:\n{observation}")

        return "nombre maximum de tours atteint", trace

if __name__ == "__main__":
    try:
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        client = ClientLLM(adress="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                        , modele="gemini-3.6-flash", key=api_key)
        test = Agent(question="combien font 2 + 2", max_tours=6, client=client)
        res = test.agent_algo()
        print(res)
    except Exception as e:
        logging.error(f"Erreur lors de l'exécution de l'agent: {e}")
    
