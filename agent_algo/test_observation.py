"""Tests de la coupure des observations inventées par le LLM, sans réseau ni vraie sandbox."""
from agent_algo.agent import CUT_NOTE, Agent, couper_observation_inventee
from agent_algo.test_bascule import FauxClient
from sandbox.protocol import ExecutionResult

INVENTEE = "Thought: test\n```python\nprint(2)\n```\nObservation: 2\n```python\nprint(3)\n```"


class FausseSandbox:
    """Imite Sandbox : note le code reçu et renvoie toujours "2"."""

    def __init__(self):
        self.codes = []

    def execute(self, code):
        self.codes.append(code)
        return ExecutionResult(success=True, output="2\n", error="")


def test_coupe_a_la_ligne_observation():
    assert couper_observation_inventee(INVENTEE) == "Thought: test\n```python\nprint(2)\n```\n"


def test_ne_coupe_pas_observation_au_milieu_d_une_ligne():
    texte = "Thought: I will read the Observation: carefully"
    assert couper_observation_inventee(texte) == texte


def test_le_code_invente_n_est_pas_execute_et_le_llm_est_prevenu():
    client = FauxClient("A", [({"content": INVENTEE}, None), ({"content": "Final Answer: 2"}, None)])
    sandbox = FausseSandbox()
    agent = Agent("question", max_tours=10, client=client, sandbox=sandbox)
    reponse, steps = agent.agent_algo()
    assert reponse == "2"
    assert [c.strip() for c in sandbox.codes] == ["print(2)"]  # seul le vrai bloc tourne, pas print(3)
    assert steps[0].llm_output == INVENTEE          # solution.json garde la sortie brute
    memoire = client.appels[1]                      # conversation envoyée au 2e appel
    assert "print(3)" not in memoire[2]             # l'invention n'est pas gardée en mémoire
    assert memoire[3].endswith(CUT_NOTE)            # et le LLM sait pourquoi
