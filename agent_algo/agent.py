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
from sandbox.protocol import ExecutionResult
from sandbox.parent import Sandbox

MAX_OBSERVATION = 5000  # sert a couper les observations trop longues pour ne pas exploser le contexte

# Sent when the LLM replies with neither a code block nor a final answer
FORMAT_REMINDER = ("Your reply contained no ```python block and no final answer. "
                   "Reply with ONE ```python block, or give your final answer.")

# The tools are no longer listed here: they come from the connected MCP server,
# and their manual (mcp_bridge.build_manual) is passed to Agent as tools_manual
PROMPT_SYSTEME = """Tu es un agent qui resout des taches de code.
A chaque tour :
1. Thought: tu expliques ce que tu vas faire.
2. Code: tu ecris UN bloc ```python ... ``` qui sera execute. Utilise print() pour voir les resultats.
3. Tu recois ensuite une Observation avec ce qui a ete affiche (ou l'erreur).
Les variables sont conservees d'un tour a l'autre.

Quand tu as la reponse finale, appelle final_answer(reponse) dans ton code,
ou reponds SANS bloc ```python```, en commencant par "Final Answer:".
"""
FOURNISSEUR = [{"nom" : "groq", "url": "https://api.groq.com/openai/v1/chat/completions", "modele": "openai/gpt-oss-120b", "key_env": "GROQ_API_KEY"},
       {"nom":"gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "modele": "gemini-3.6-flash", "key_env": "GEMINI_API_KEY"}]

def creer_client(index):
    """créé un nv client LLM à partir de l'index dans la liste LLM"""
    fournisseur = FOURNISSEUR[index]
    nom_variable = fournisseur["key_env"]
    api_key = os.getenv(nom_variable)
    if not api_key:
        raise ValueError(f"Clé API manquante pour {fournisseur['nom']}. Veuillez définir la variable d'environnement {nom_variable}.")
    return ClientLLM(adress=fournisseur["url"], modele=fournisseur["modele"], key=api_key)

def format_observation(result: ExecutionResult) -> str:
    """What the LLM sees after its code ran: printed output, then the error if any."""
    observation = result.output + result.error
    if not observation.strip():
        observation = "(the code ran without error and printed nothing)"
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
                with urllib.request.urlopen(requete, timeout=40) as response: #envoie la requete au serveur
                    reponse = json.load(response)
                self.temps_ms = (time.perf_counter() - debut) * 1000
                usage = reponse.get("usage") or {}  # nombre de tokens renvoye par l'API
                self.input_tokens = usage.get("prompt_tokens", 0)
                self.output_tokens = usage.get("completion_tokens", 0)
                return reponse["choices"][0]["message"], None # retourne la reponse du serveur
            except urllib.error.HTTPError as e:
                logging.error(f"Echec HTTP. Code {e.code}, Raison {e.reason}")
                # je distingue les erreurs 400 et 404 pour ne pas réessayer inutilement (erreures de requete ou ressource non trouvée)
                if e.code == 429:
                    logging.error(f"Trop de requetes {e.code}. Attente avant de reessayer...")
                    return None, e.code
                if e.code in(400, 404):
                    logging.error(f"Erreur critique {e.code}, arret de l'agent.")
                    return None, e.code
                attente = e.headers.get("Retry-After") if e.headers else None  # le serveur peut dire combien attendre
                i = i + 1
                self.attendre(i, attente)
            except urllib.error.URLError as e:
                logging.error(f"Echec URL. Raison {e.reason}")
                i = i + 1
                self.attendre(i)
            except TimeoutError as e:
                logging.error(f"Timeout. Raison {e}")
                i = i + 1
                self.attendre(i)
        return None, None  # si on a fait 5 essais sans succes, on renvoie None


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
    def __init__(self, question, max_tours, client, sandbox: Sandbox,
                 prompt_systeme=PROMPT_SYSTEME, tools_manual: str = ""):
        """sandbox: created by the caller, who chooses its MCP tools.
        tools_manual: tool documentation appended to the system prompt."""
        self.question = question
        self.max_tours = max_tours
        self.client = client
        self.sandbox = sandbox
        self.prompt_systeme = prompt_systeme  # modifiable : MBPP a besoin d'un prompt plus court
        if tools_manual:
            self.prompt_systeme += "\n\n" + tools_manual
        self.succes = False  # passe a True si le llm donne une reponse finale
        self.index_fournisseur = 0  # index du fournisseur actuel dans la liste FOURNISSEUR


    def agent_algo(self) -> tuple[str, list[StepMetrics]]:
        """fait tourner la boucle think->act->observe jusqu'a la reponse"""
        memoire=[
            {"role": "system", "content": self.prompt_systeme},
            {"role": "user", "content": self.question}
        ]
        steps: list[StepMetrics] = []  # une fiche par tour, pour solution.json

        for tour in range(1, self.max_tours + 1):
            message, code_erreur = self.client.appel_llm(memoire) # parti de thinking
            if message is None:  # si le llm ne repond pas on sort de la boucle
                if code_erreur == 429:
                    self.index_fournisseur += 1
                    if self.index_fournisseur >= len(FOURNISSEUR):
                        return f"Plus de fournisseurs disponibles, arret de l'agent.", steps
                    client = FOURNISSEUR[self.index_fournisseur]  # on change de fournisseur si trop de requetes
                    self.client = creer_client(self.index_fournisseur)
                    memoire.append({"role": "user", "content": f"Erreur 429 du serveur {client['nom']}, je change de fournisseur et reessaye."})
                    continue
                if code_erreur is None:
                    return f"Erreur du serveur, arret de l'agent.", steps
                if code_erreur in (400, 404):
                    return f"Erreur critique {code_erreur} du serveur, arret de l'agent.", steps
                return f"Erreur du serveur, arret de l'agent.", steps
            contenu = message.get("content") or ""
            # some APIs reject an empty assistant message, so store a placeholder
            memoire.append({"role": "assistant", "content": contenu or "(empty reply)"}) # je sauvegarde la reponse du llm en mémoire

            # "Final Answer:" est prioritaire : le llm recopie parfois du code dans son raisonnement final
            code = None if "Final Answer:" in contenu else p_mardown(contenu)  # parti code
            observation = ""
            result = None
            if code is not None:
                # the sandbox keeps the LLM's variables from one step to the next
                result = self.sandbox.execute(code)  # parti observe
                observation = format_observation(result)
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

            if result is not None and result.final_answer is not None:
                self.succes = True  # the code called final_answer()
                return result.final_answer, steps

            if "Final Answer:" in contenu:
                self.succes = True
                return contenu.split("Final Answer:")[-1].strip(), steps

            if code is None:
                # Neither code nor final answer (e.g. an empty reply): do not
                # stop, remind the format. max_tours still bounds the loop
                memoire.append({"role": "user", "content": FORMAT_REMINDER})

        return "nombre maximum de tours atteint", steps

if __name__ == "__main__":
    try:
        load_dotenv()
        client = creer_client(0)  # crée un client LLM pour le fournisseur à l'index 0
        with Sandbox() as sandbox:
            test = Agent(question="combien font 2 + 2", max_tours=6, client=client, sandbox=sandbox)
            res = test.agent_algo()
        print(res)
    except Exception as e:
        logging.error(f"Erreur lors de l'exécution de l'agent: {e}")
    
