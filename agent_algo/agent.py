import json
import time
import urllib.request
import urllib.error
from dotenv import load_dotenv # type: ignore
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
from models_public import StepMetrics
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
URL = {"groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "modele": "modele"}, 
       "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "modele": "gemini-3.6-flash"}}

def executer_code(code, namespace):
    """execute le code du llm et renvoie ce qui a ete affiche (stdout + erreurs)"""
    sortie = io.StringIO()
    try:
        with contextlib.redirect_stdout(sortie):
            exec(code, namespace)
    except Exception:
        sortie.write(traceback.format_exc(limit=-1))
    observation = sortie.getvalue() or "(le code a tourne sans erreur, rien n'a ete affiche)"
    return observation[:MAX_OBSERVATION]

class ClientLLM:
    def __init__(self, adress, modele, key):
        self.adress = adress
        self.modele = modele
        self.key = key
        # metriques du dernier appel (lues par l'agent pour remplir solution.json)
        self.input_tokens = 0
        self.output_tokens = 0
        self.temps_ms = 0.0
        self.retries = 0
        self.total_requetes = 0  # toutes les requetes envoyees, retries compris

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
            self.retries = i
            self.total_requetes += 1
            debut = time.perf_counter()
            try:
                with urllib.request.urlopen(requete, timeout=300) as response: #envoie la requete au serveur
                    reponse = json.load(response)
                self.temps_ms = (time.perf_counter() - debut) * 1000
                usage = reponse.get("usage") or {}  # nombre de tokens renvoye par l'API
                self.input_tokens = usage.get("prompt_tokens", 0)
                self.output_tokens = usage.get("completion_tokens", 0)
                return reponse["choices"][0]["message"] # retourne la reponse du serveur
            except urllib.error.HTTPError as e:
                logging.error(f"Echec HTTP. Code {e.code}, Raison {e.reason}")
                # je distingue les erreurs 400 et 404 pour ne pas réessayer inutilement (erreures de requete ou ressource non trouvée)
                if e.code in(400, 404):
                    return None
                attente = e.headers.get("Retry-After") if e.headers else None  # le serveur peut dire combien attendre
                i = i + 1
                self.attendre(i, attente)
            except urllib.error.URLError as e:
                logging.error(f"Echec URL. Raison {e.reason}")
                i = i + 1
                self.attendre(i)
        return None

    def attendre(self, essai, attente=None):
        """attend avant de reessayer : 1s, 2s, 4s, 8s... (ou ce que demande le serveur), max 20s"""
        if essai > 5:  # plus d'essai apres, inutile d'attendre
            return
        try:
            secondes = float(attente)
        except (TypeError, ValueError):
            secondes = 2 ** (essai - 1)
        time.sleep(min(secondes, 20))

class Agent:
    def __init__(self, question, max_tours, client, prompt_systeme=PROMPT_SYSTEME):
        self.question = question
        self.max_tours = max_tours
        self.client = client
        self.prompt_systeme = prompt_systeme  # modifiable : MBPP a besoin d'un prompt plus court
        self.succes = False  # passe a True si le llm donne une reponse finale

    def agent_algo(self) -> tuple[str, list[StepMetrics]]:
        """fait tourner la boucle think->act->observe jusqu'a la reponse"""
        memoire=[
            {"role": "system", "content": self.prompt_systeme},
            {"role": "user", "content": self.question}
        ]
        steps: list[StepMetrics] = []  # une fiche par tour, pour solution.json
        namespace = dict(OUTILS)  # garde les variables du llm d'un tour a l'autre

        for tour in range(1, self.max_tours + 1):
            message = self.client.appel_llm(memoire) # parti de thinking
            if message is None:  # si le llm ne repond pas on sort de la boucle
                return "le llm ne repond pas", steps
            contenu = message.get("content") or ""
            memoire.append({"role": "assistant", "content": contenu}) # je sauvegarde la reponse du llm en mémoire

            # "Final Answer:" est prioritaire : le llm recopie parfois du code dans son raisonnement final
            code = None if "Final Answer:" in contenu else p_mardown(contenu)  # parti code
            observation = ""
            if code is not None:
                observation = executer_code(code, namespace)  # parti observe
                memoire.append({"role": "user", "content": f"Observation:\n{observation}"})

            steps.append(StepMetrics(
                step=tour,
                input_tokens=self.client.input_tokens,
                output_tokens=self.client.output_tokens,
                request_time_ms=self.client.temps_ms,
                retries=self.client.retries,
                api_url=self.client.adress,
                model_name=self.client.modele,
                llm_output=contenu,
                sandbox_input=code or "",
                sandbox_output=observation,
            ))

            if code is None:  # pas de code = reponse finale
                self.succes = True
                return contenu.split("Final Answer:")[-1].strip(), steps

        return "nombre maximum de tours atteint", steps

if __name__ == "__main__":
    try:
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        client = ClientLLM(adress=URL["gemini"]["url"]
                        , modele=URL["gemini"]["modele"], key=api_key)
        test = Agent(question="combien font 2 + 2", max_tours=6, client=client)
        res = test.agent_algo()
        print(res)
    except Exception as e:
        logging.error(f"Erreur lors de l'exécution de l'agent: {e}")
    
