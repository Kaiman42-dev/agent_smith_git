"""Tests de la bascule entre fournisseurs LLM (Agent.appeler_llm), sans réseau."""
from agent_algo.agent import Agent

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

    def appel_llm(self, memoire, **options):
        self.appels.append([m["content"] for m in memoire])
        return self.reponses.pop(0)


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
    reponse, steps = lancer(FauxClient("A", [(None, 503)]), [FauxClient("B", [(None, 429)])])
    assert "429" in reponse and steps == []
