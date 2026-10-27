"""Tests de la bascule entre fournisseurs LLM (Agent.appeler_llm), sans réseau."""
import email.message
import io
import time
import urllib.error

import pytest

from agent_algo import agent as agent_module
from agent_algo.agent import Agent, delai_quota, en_secondes

REPONSE_OK = ({"content": "Final Answer: 42"}, None)


class FauxClient:
    """Imite ClientLLM : renvoie des réponses écrites à l'avance, et note chaque appel."""

    def __init__(self, modele, reponses):
        self.modele = modele
        self.adress = f"https://{modele}.test"
        self.reponses = list(reponses)
        self.appels = []  # la conversation reçue à chaque appel
        self.input_tokens = self.output_tokens = self.retries = 0
        self.temps_ms = 0.0
        self.erreurs = []
        self.attente_quota = None  # délai annoncé après un 429, comme ClientLLM

    def appel_llm(self, memoire, **options):
        self.appels.append([m["content"] for m in memoire])
        message, code = self.reponses.pop(0)
        self.erreurs = [] if message is not None else [str(code)]  # comme ClientLLM
        return message, code


def lancer(principal, secours):
    # "Final Answer:" termine la tâche sans exécuter de code : pas besoin de sandbox
    agent = Agent("question", max_tours=10, client=principal, sandbox=None, secours=secours)
    reponse, steps = agent.agent_algo()
    return reponse, steps


def test_bascule_sur_le_secours_si_le_principal_est_surcharge():
    principal, secours = FauxClient("A", [(None, 503)]), FauxClient("B", [REPONSE_OK])
    reponse, steps = lancer(principal, [secours])
    assert reponse == "42"
    assert len(steps) == 1                  # la bascule ne consomme pas de tour
    assert steps[0].model_name == "B"


def test_la_bascule_reste_invisible_pour_le_llm():
    principal, secours = FauxClient("A", [(None, 429)]), FauxClient("B", [REPONSE_OK])
    lancer(principal, [secours])
    assert secours.appels[0] == principal.appels[0]  # même conversation, aucun message ajouté


def test_bascule_en_chaine():
    a, b, c = FauxClient("A", [(None, 429)]), FauxClient("B", [(None, None)]), FauxClient("C", [REPONSE_OK])
    reponse, steps = lancer(a, [b, c])
    assert reponse == "42" and steps[0].model_name == "C"


def test_pas_de_bascule_si_la_requete_est_fausse():
    principal, secours = FauxClient("A", [(None, 400)]), FauxClient("B", [REPONSE_OK])
    reponse, steps = lancer(principal, [secours])
    assert secours.appels == []             # B n'est jamais appelé
    assert "400" in reponse and steps == []


def test_arret_propre_si_tout_le_monde_est_en_panne():
    reponse, steps = lancer(FauxClient("A", [(None, 503)]), [FauxClient("B", [(None, 503)])])
    assert "503" in reponse and steps == []


# AS-43 : 429 sans fournisseur de secours -> attendre que le quota se recharge

@pytest.fixture
def attentes(monkeypatch):
    """Remplace time.sleep : les tests n'attendent pas vraiment, ils notent les durées."""
    durees = []
    monkeypatch.setattr(time, "sleep", durees.append)
    return durees


def test_quota_depasse_sans_secours_on_attend_puis_on_reessaie(attentes):
    client = FauxClient("A", [(None, 429), REPONSE_OK])
    client.attente_quota = 12.0
    reponse, steps = lancer(client, [])
    assert reponse == "42" and len(steps) == 1     # l'attente ne consomme pas de tour
    assert attentes == [13.0]                      # le délai du fournisseur, plus 1 s de marge


def test_quota_avec_secours_on_bascule_sans_attendre(attentes):
    reponse, steps = lancer(FauxClient("A", [(None, 429)]), [FauxClient("B", [REPONSE_OK])])
    assert reponse == "42" and attentes == []


def test_pas_d_attente_au_dela_de_l_heure_limite(attentes):
    client = FauxClient("A", [(None, 429)])
    client.attente_quota = 50.0
    agent = Agent("question", max_tours=10, client=client, sandbox=None, fin=time.monotonic() + 20)
    reponse, steps = agent.agent_algo()
    assert attentes == [] and "429" in reponse     # arrêt propre plutôt que dépasser la limite


def test_nombre_d_attentes_limite(attentes, monkeypatch):
    monkeypatch.setattr(agent_module, "MAX_ATTENTES_QUOTA", 2)
    reponse, steps = lancer(FauxClient("A", [(None, 429)] * 5), [])
    assert len(attentes) == 2 and "429" in reponse
    assert attentes == [6, 11]                     # sans délai annoncé : 5 s, 10 s (+1 s de marge)


def entetes(**valeurs):
    m = email.message.Message()
    for cle, valeur in valeurs.items():
        m[cle.replace("_", "-")] = valeur
    return m


def erreur_429(corps="", **valeurs):
    return urllib.error.HTTPError("https://faux.test", 429, "Too Many Requests", entetes(**valeurs),
                                  io.BytesIO(corps.encode()))


def test_delai_quota_selon_le_fournisseur():
    assert delai_quota(erreur_429(Retry_After="7")) == 7                                  # Groq
    assert delai_quota(erreur_429(x_ratelimit_reset_tokens="1m2.5s")) == 62.5             # Groq
    gemini = '[{"error": {"code": 429, "details": [{"retryDelay": "49s"}]}}]'
    assert delai_quota(erreur_429(gemini)) == 49                                          # Gemini
    assert delai_quota(erreur_429('{"message": "Please retry in 49.06s."}')) == 49.06
    assert delai_quota(erreur_429()) is None


def test_en_secondes():
    assert en_secondes("39.877s") == 39.877 and en_secondes("8m38.4s") == 518.4
    assert en_secondes("120ms") == 0.12 and en_secondes("7") == 7 and en_secondes(None) is None
