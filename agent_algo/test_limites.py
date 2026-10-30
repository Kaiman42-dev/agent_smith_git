"""Tests des limites de la tâche (sujet, VI.1) : tokens et temps, sans réseau."""
import time

import pytest

from agent_algo.agent import Agent, compter_tokens

# ni code ni réponse finale : la boucle continue jusqu'à une limite
REFLEXION = {"content": "Thought: je réfléchis encore"}


class ClientCompteur:
    """Faux client qui « consomme » des tokens et note le max_tokens reçu à chaque appel."""

    def __init__(self, entree, sortie):
        self.modele, self.adress = "faux", "https://faux.test"
        self.entree, self.sortie = entree, sortie  # tokens consommés par appel
        self.max_tokens_recus = []
        self.input_tokens = self.output_tokens = self.retries = 0
        self.temps_ms = 0.0
        self.erreurs = []

    def appel_llm(self, memoire, max_tokens=None, fin=None):
        self.max_tokens_recus.append(max_tokens)
        self.input_tokens = self.entree
        # comme une vraie API : le modèle ne génère jamais plus que max_tokens
        self.output_tokens = self.sortie if max_tokens is None else min(self.sortie, max_tokens)
        return REFLEXION, None


def lancer(client, **limites):
    agent = Agent("question", max_tours=10, client=client, sandbox=None, **limites)
    return agent.agent_algo()


def test_sortie_le_modele_recoit_le_budget_restant_puis_l_agent_s_arrete():
    client = ClientCompteur(entree=100, sortie=600)
    reponse, steps = lancer(client, max_output_tokens=1500)
    assert client.max_tokens_recus == [1500, 900, 300]
    assert sum(s.output_tokens for s in steps) == 1500   # jamais plus que la limite
    assert "sortie" in reponse


def test_entree_s_arrete_avant_l_appel_qui_depasserait():
    client = ClientCompteur(entree=2500, sortie=10)
    reponse, steps = lancer(client, max_input_tokens=6000)
    # 2 appels = 5000 tokens ; un 3e en coûterait au moins 2500 de plus : on s'arrête avant
    assert len(steps) == 2
    assert "entrée" in reponse


def test_temps_ecoule_aucun_appel():
    client = ClientCompteur(entree=100, sortie=10)
    reponse, steps = lancer(client, fin=time.monotonic() - 1)
    assert steps == [] and client.max_tokens_recus == []
    assert "temps" in reponse


def test_sans_limite_rien_ne_change():
    client = ClientCompteur(entree=2500, sortie=600)
    reponse, steps = lancer(client)
    assert len(steps) == 10 and client.max_tokens_recus == [None] * 10


class ClientMemoire(ClientCompteur):
    """Faux client qui garde aussi le dernier message reçu à chaque appel."""

    def __init__(self, entree, sortie):
        super().__init__(entree, sortie)
        self.derniers_messages = []

    def appel_llm(self, memoire, max_tokens=None, fin=None):
        self.derniers_messages.append(memoire[-1]["content"])
        return super().appel_llm(memoire, max_tokens, fin)


@pytest.fixture
def sans_pause(monkeypatch):
    """La boucle attend 12 s entre deux tours (quota Gemini) : inutile sans réseau."""
    monkeypatch.setattr(time, "sleep", lambda secondes: None)


def test_budget_annonce_les_tours_restants_puis_alerte(sans_pause):
    client = ClientMemoire(entree=100, sortie=10)
    lancer(client, alerte_budget=3)
    # le message envoyé à l'appel n+1 se termine par le budget après le tour n
    apres_tour = client.derniers_messages[1:]
    assert "[Budget: step 1/10, about 9 step(s) left]" in apres_tour[0]
    assert "stop exploring" not in apres_tour[5]           # 4 tours restants
    assert "Only 3 step(s) left: stop exploring" in apres_tour[6]


def test_budget_tient_compte_des_tokens_d_entree(sans_pause):
    client = ClientMemoire(entree=1000, sortie=10)
    lancer(client, alerte_budget=1, max_input_tokens=6000)
    # après le tour 1 : 5000 tokens restants, soit 5 appels à 1000 (moins que les 9 tours)
    assert "about 5 step(s) left" in client.derniers_messages[1]


def test_sans_alerte_budget_aucune_note(sans_pause):
    client = ClientMemoire(entree=100, sortie=10)
    lancer(client)
    assert not any("[Budget" in m for m in client.derniers_messages)


def test_compter_tokens_reflexion_gemini():
    # usage réel de gemini-3.6-flash : la réflexion n'est que dans total_tokens
    assert compter_tokens({"completion_tokens": 1, "prompt_tokens": 14, "total_tokens": 408}) == (14, 394)


def test_compter_tokens_reflexion_deja_incluse():
    # usage réel de gpt-oss-120b sur Groq : reasoning_tokens est compris dans completion_tokens
    usage = {"prompt_tokens": 82, "completion_tokens": 57, "total_tokens": 139,
             "completion_tokens_details": {"reasoning_tokens": 46}}
    assert compter_tokens(usage) == (82, 57)


def test_compter_tokens_usage_incomplet():
    assert compter_tokens({}) == (0, 0)
    assert compter_tokens({"prompt_tokens": 10, "completion_tokens": 5}) == (10, 5)
    assert compter_tokens({"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}) == (0, 0)
