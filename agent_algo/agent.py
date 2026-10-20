import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
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

# Added to the next observation when the LLM's reply had to be cut
CUT_NOTE = ("\n(Note: your reply was cut at 'Observation:'. Observations come "
            "from the sandbox: never write them yourself.)")

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
# Fournisseurs de secours, essayés dans cet ordre si le fournisseur choisi ne répond plus
FOURNISSEUR = [
    {"nom": "groq", "url": "https://api.groq.com/openai/v1/chat/completions",
     "modele": "openai/gpt-oss-120b", "key_env": "GROQ_API_KEY"},
    {"nom": "openrouter", "url": "https://openrouter.ai/api/v1/chat/completions",
     "modele": "poolside/laguna-s-2.1:free", "key_env": "OPENROUTER_API_KEY"},
    {"nom": "gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     "modele": "gemini-3.6-flash", "key_env": "GEMINI_API_KEY"},
]

def creer_client(index):
    """créé un nv client LLM à partir de l'index dans la liste LLM"""
    fournisseur = FOURNISSEUR[index]
    nom_variable = fournisseur["key_env"]
    api_key = os.getenv(nom_variable)
    if not api_key:
        raise ValueError(f"Clé API manquante pour {fournisseur['nom']}. Veuillez définir la variable d'environnement {nom_variable}.")
    return ClientLLM(adress=fournisseur["url"], modele=fournisseur["modele"], key=api_key)


# Variable d'environnement de la clé API, selon le domaine de l'URL du fournisseur
KEY_ENV_BY_HOST = {
    "api.groq.com": "GROQ_API_KEY",
    "generativelanguage.googleapis.com": "GEMINI_API_KEY",
    "openrouter.ai": "OPENROUTER_API_KEY",
}


def creer_client_cli(provider_url: str, modele: str, api_key_env: str | None = None) -> "ClientLLM":
    """Crée le client LLM à partir des options --provider-url, --model-name et --api-key-env.

    Sans --api-key-env, la variable de la clé est déduite du domaine de l'URL.
    """
    # --provider-url est l'url de base, ClientLLM veut l'url complete
    url = provider_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"

    if api_key_env is None:
        host = urllib.parse.urlparse(url).hostname or ""
        if host not in KEY_ENV_BY_HOST:
            raise ValueError(f"Fournisseur inconnu ({host}) : indique la variable de la clé avec --api-key-env")
        api_key_env = KEY_ENV_BY_HOST[host]

    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError(f"Clé API manquante : la variable d'environnement {api_key_env} n'est pas définie")
    return ClientLLM(adress=url, modele=modele, key=api_key)


def creer_clients_secours(principal: "ClientLLM") -> list["ClientLLM"]:
    """Les clients de secours, dans l'ordre de FOURNISSEUR.

    On saute le fournisseur du client principal (s'il est en panne, ses autres modèles
    aussi, en général) et ceux dont la clé manque : on les ignore ici, au lieu de
    planter au moment de basculer.
    """
    secours = []
    for fournisseur in FOURNISSEUR:
        if fournisseur["url"] == principal.adress:
            continue
        api_key = os.getenv(fournisseur["key_env"])
        if api_key:
            secours.append(ClientLLM(adress=fournisseur["url"], modele=fournisseur["modele"], key=api_key))
    return secours

def couper_observation_inventee(texte: str) -> str:
    """Coupe la réponse du LLM là où il commence à inventer le résultat de son code (sujet, V.6).

    On ne passe pas par le paramètre "stop" de l'API : chez les modèles raisonneurs,
    il coupe aussi leur réflexion cachée dès qu'elle cite "Observation:", et la
    réponse arrive vide.
    """
    return re.split(r"^Observation:", texte, maxsplit=1, flags=re.MULTILINE)[0]

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
            self.adress, data=corps,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.key}",  # c'est ce qui est envoyé a l'API, avec la clé
                # Cloudflare (devant Groq) refuse l'identifiant par défaut "Python-urllib" : erreur 403
                "User-Agent": "agent-smith/0.1",
            },
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
                if e.code == 429:
                    logging.error("Trop de requetes (429) : on passe au fournisseur suivant.")
                    return None, e.code
                # Erreurs définitives, réessayer ne changera rien :
                # 400/404 = requête fausse (modèle inconnu...), 401/403 = clé refusée ou accès interdit
                if e.code in (400, 401, 403, 404):
                    logging.error(f"Erreur definitive {e.code}, inutile de reessayer.")
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
                 prompt_systeme=PROMPT_SYSTEME, tools_manual: str = "",
                 secours: list | None = None):
        """sandbox: created by the caller, who chooses its MCP tools.
        tools_manual: tool documentation appended to the system prompt.
        secours: clients LLM de secours, essayés dans l'ordre si le client actuel ne répond plus."""
        self.question = question
        self.max_tours = max_tours
        self.client = client
        self.sandbox = sandbox
        self.prompt_systeme = prompt_systeme  # modifiable : MBPP a besoin d'un prompt plus court
        if tools_manual:
            self.prompt_systeme += "\n\n" + tools_manual
        self.succes = False  # passe a True si le llm donne une reponse finale
        self.secours = list(secours or [])  # copie : on la vide au fur et à mesure des bascules


    def appeler_llm(self, memoire):
        """Appelle le LLM ; si le fournisseur ne répond plus, bascule sur le client de secours suivant.

        Renvoie (message, None), ou (None, code_erreur) quand plus aucun fournisseur ne répond.
        """
        while True:
            message, code_erreur = self.client.appel_llm(memoire)
            if message is not None:
                return message, None
            # 400/404 : notre requête est fausse (modèle inconnu...), changer de fournisseur n'y changera rien
            if code_erreur in (400, 404) or not self.secours:
                return None, code_erreur
            ancien, self.client = self.client, self.secours.pop(0)
            logging.warning(f"{ancien.modele} indisponible (code {code_erreur}), bascule sur {self.client.modele}")


    def agent_algo(self) -> tuple[str, list[StepMetrics]]:
        """fait tourner la boucle think->act->observe jusqu'a la reponse"""
        memoire=[
            {"role": "system", "content": self.prompt_systeme},
            {"role": "user", "content": self.question}
        ]
        steps: list[StepMetrics] = []  # une fiche par tour, pour solution.json

        for tour in range(1, self.max_tours + 1):
            message, code_erreur = self.appeler_llm(memoire) # parti de thinking
            if message is None:  # plus aucun fournisseur ne repond : on arrete
                return f"Le LLM ne répond plus (dernier code : {code_erreur}), arret de l'agent.", steps
            brut = message.get("content") or ""
            contenu = couper_observation_inventee(brut)  # on garde seulement ce qui précède l'observation inventée
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
                note = CUT_NOTE if contenu != brut else ""  # le LLM ne doit jamais deviner pourquoi
                memoire.append({"role": "user", "content": f"Observation:\n{observation}{note}"})

            steps.append(StepMetrics(
                step=tour,
                input_tokens=self.client.input_tokens,
                output_tokens=self.client.output_tokens,
                request_time_ms=self.client.temps_ms,
                retries=self.client.retries,
                api_url=self.client.adress,
                model_name=self.client.modele,
                llm_output=brut,  # le sujet veut la sortie brute du LLM
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
    
