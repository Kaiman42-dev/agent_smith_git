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

from Extraction_llm import extraire_code
from agent_algo.config import ModelsConfig, charger_config
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
def url_chat(url: str) -> str:
    """--provider-url et models.json donnent l'url de base, ClientLLM veut l'url complete"""
    url = url.rstrip("/")
    return url if url.endswith("/chat/completions") else url + "/chat/completions"


def creer_client(index, config: ModelsConfig | None = None):
    """créé un nv client LLM à partir de l'index du fournisseur dans models.json"""
    fournisseur = (config or charger_config()).providers[index]
    api_key = os.getenv(fournisseur.api_key_env)
    if not api_key:
        raise ValueError(f"Clé API manquante pour {fournisseur.name}. Veuillez définir la variable d'environnement {fournisseur.api_key_env}.")
    return ClientLLM(adress=url_chat(fournisseur.url), modele=fournisseur.fallback_model, key=api_key)


def creer_client_cli(provider_url: str, modele: str, api_key_env: str | None,
                     config: ModelsConfig) -> "ClientLLM":
    """Crée le client LLM à partir des options --provider-url, --model-name et --api-key-env.

    Sans --api-key-env, la variable de la clé est celle du fournisseur de models.json
    qui a le même domaine que l'URL.
    """
    url = url_chat(provider_url)
    if api_key_env is None:
        fournisseur = config.fournisseur_pour_url(url)
        if fournisseur is None:
            host = urllib.parse.urlparse(url).hostname or ""
            raise ValueError(f"Fournisseur inconnu ({host}) : indique la variable de la clé "
                             f"avec --api-key-env, ou ajoute le fournisseur dans models.json")
        api_key_env = fournisseur.api_key_env

    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError(f"Clé API manquante : la variable d'environnement {api_key_env} n'est pas définie")
    return ClientLLM(adress=url, modele=modele, key=api_key)


def creer_clients_secours(principal: "ClientLLM", config: ModelsConfig) -> list["ClientLLM"]:
    """Les clients de secours, dans l'ordre des fournisseurs de models.json.

    On saute le fournisseur du client principal (s'il est en panne, ses autres modèles
    aussi, en général) et ceux dont la clé manque : on les ignore ici, au lieu de
    planter au moment de basculer.
    """
    host_principal = urllib.parse.urlparse(principal.adress).hostname
    secours = []
    for fournisseur in config.providers:
        if fournisseur.host == host_principal:
            continue
        api_key = os.getenv(fournisseur.api_key_env)
        if api_key:
            secours.append(ClientLLM(adress=url_chat(fournisseur.url), modele=fournisseur.fallback_model, key=api_key))
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

    def appel_llm(self, messages, max_tokens=None, fin=None):
        """Envoie la conversation au modèle et renvoie son message de réponse.

        max_tokens : nombre maximal de tokens que le modèle peut générer (budget restant).
        fin : heure limite (time.monotonic()) ; aucun essai ni aucune attente ne la dépasse.
        """
        options = {"model": self.modele, "messages": messages, "stream": False}
        if max_tokens is not None:
            options["max_tokens"] = max_tokens
        corps = json.dumps(options).encode()
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
            reste = None if fin is None else fin - time.monotonic()
            if reste is not None and reste < 1:
                logging.error("Plus de temps pour appeler le LLM (limite de temps de la tâche).")
                return None, None
            self.retries = i
            self.total_requetes += 1
            debut = time.perf_counter()
            try:
                with urllib.request.urlopen(requete, timeout=min(40, reste or 40)) as response: #envoie la requete au serveur
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
                self.attendre(i, attente, fin)
            except urllib.error.URLError as e:
                logging.error(f"Echec URL. Raison {e.reason}")
                i = i + 1
                self.attendre(i, fin=fin)
            except TimeoutError as e:
                logging.error(f"Timeout. Raison {e}")
                i = i + 1
                self.attendre(i, fin=fin)
        return None, None  # si on a fait 5 essais sans succes, on renvoie None


    def attendre(self, essai, attente=None, fin=None):
        """attend avant de reessayer : 1s, 2s, 4s, 8s... (ou ce que demande le serveur), max 20s,
        et jamais au-delà de l'heure limite"""
        if essai > 5:  # plus d'essai apres, inutile d'attendre
            return
        try:
            secondes = float(attente)
        except (TypeError, ValueError):
            secondes = 2 ** (essai - 1)
        if fin is not None:
            secondes = min(secondes, max(0, fin - time.monotonic()))
        time.sleep(min(secondes, 20))


def taille(memoire) -> int:
    """Nombre de caractères de la conversation (sert à estimer les tokens du prochain appel)."""
    return sum(len(m["content"]) for m in memoire)


class Agent:
    def __init__(self, question, max_tours, client, sandbox: Sandbox,
                 prompt_systeme=PROMPT_SYSTEME, tools_manual: str = "",
                 secours: list | None = None, max_input_tokens: int | None = None,
                 max_output_tokens: int | None = None, fin: float | None = None):
        """sandbox: created by the caller, who chooses its MCP tools.
        tools_manual: tool documentation appended to the system prompt.
        secours: clients LLM de secours, essayés dans l'ordre si le client actuel ne répond plus.
        max_input_tokens, max_output_tokens : budget de tokens pour toute la tâche (sujet, VI.1).
        fin : heure limite de la tâche (time.monotonic()). None = pas de limite."""
        self.question = question
        self.max_tours = max_tours
        self.client = client
        self.sandbox = sandbox
        self.prompt_systeme = prompt_systeme  # modifiable : MBPP a besoin d'un prompt plus court
        if tools_manual:
            self.prompt_systeme += "\n\n" + tools_manual
        self.succes = False  # passe a True si le llm donne une reponse finale
        self.secours = list(secours or [])  # copie : on la vide au fur et à mesure des bascules
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.fin = fin
        self.taille_dernier_envoi = 0  # caractères envoyés au dernier appel


    def temps_ecoule(self) -> bool:
        return self.fin is not None and time.monotonic() >= self.fin


    def raison_arret(self, steps, memoire) -> str | None:
        """Avant chaque appel au LLM : pourquoi il faut s'arrêter, ou None s'il reste du budget."""
        if self.temps_ecoule():
            return "limite de temps atteinte"
        sortie = sum(s.output_tokens for s in steps)
        if self.max_output_tokens is not None and sortie >= self.max_output_tokens:
            return f"limite de tokens de sortie atteinte ({sortie}/{self.max_output_tokens})"
        if self.max_input_tokens is not None and steps:
            # chaque appel renvoie toute la conversation : le prochain coûtera autant que le
            # dernier, plus ce qu'on a ajouté depuis (environ 1 token pour 3 caractères)
            prochain = steps[-1].input_tokens + (taille(memoire) - self.taille_dernier_envoi) // 3
            entree = sum(s.input_tokens for s in steps)
            if entree + prochain > self.max_input_tokens:
                return (f"limite de tokens d'entrée atteinte ({entree} utilisés, "
                        f"~{prochain} pour le prochain appel, limite {self.max_input_tokens})")
        return None


    def appeler_llm(self, memoire, max_tokens=None):
        """Appelle le LLM ; si le fournisseur ne répond plus, bascule sur le client de secours suivant.

        Renvoie (message, None), ou (None, code_erreur) quand plus aucun fournisseur ne répond.
        """
        while True:
            message, code_erreur = self.client.appel_llm(memoire, max_tokens=max_tokens, fin=self.fin)
            if message is not None:
                return message, None
            # 400/404 : notre requête est fausse (modèle inconnu...), changer de fournisseur n'y changera rien.
            # Temps écoulé : un autre fournisseur n'aurait pas plus de temps.
            if code_erreur in (400, 404) or not self.secours or self.temps_ecoule():
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
            raison = self.raison_arret(steps, memoire)  # on vérifie le budget AVANT de dépenser
            if raison:
                return f"Arret de l'agent : {raison}.", steps
            self.taille_dernier_envoi = taille(memoire)
            restant = None if self.max_output_tokens is None else \
                self.max_output_tokens - sum(s.output_tokens for s in steps)
            message, code_erreur = self.appeler_llm(memoire, restant) # parti de thinking
            if message is None:  # plus aucun fournisseur ne repond : on arrete
                if self.temps_ecoule():
                    return "Arret de l'agent : limite de temps atteinte pendant l'appel au LLM.", steps
                return f"Le LLM ne répond plus (dernier code : {code_erreur}), arret de l'agent.", steps
            brut = message.get("content") or ""
            contenu = couper_observation_inventee(brut)  # on garde seulement ce qui précède l'observation inventée
            # some APIs reject an empty assistant message, so store a placeholder
            memoire.append({"role": "assistant", "content": contenu or "(empty reply)"}) # je sauvegarde la reponse du llm en mémoire

            # "Final Answer:" est prioritaire : le llm recopie parfois du code dans son raisonnement final
            # bloc python, ou appel XML / JSON / ReAct converti en python
            code = None if "Final Answer:" in contenu else extraire_code(contenu)  # parti code
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
    
