"""Tests du raccourcissement des anciennes observations (observations_completes), sans réseau."""
import pytest

from agent_algo import agent as agent_module
from agent_algo.agent import (DEBUT_ANCIENNE, FIN_ANCIENNE, OLD_NOTE, Agent,
                              raccourcir_anciennes_observations)
from agent_algo.test_bascule import FauxClient
from sandbox.protocol import ExecutionResult

LONGUE = "Observation:\n" + "a" * 2000 + "Traceback: fin"


def memoire_avec(n):
    """Une conversation avec n longues observations numérotées."""
    memoire = [{"role": "system", "content": "prompt"}, {"role": "user", "content": "question"}]
    for i in range(n):
        memoire.append({"role": "assistant", "content": f"code {i}"})
        memoire.append({"role": "user", "content": f"{LONGUE} {i}"})
    return memoire


def test_garde_les_dernieres_entieres_et_raccourcit_les_autres():
    memoire = memoire_avec(5)
    raccourcir_anciennes_observations(memoire, garder=2)
    observations = [m["content"] for m in memoire if m["content"].startswith("Observation:")]
    assert all(OLD_NOTE in o for o in observations[:3])
    assert observations[3:] == [f"{LONGUE} 3", f"{LONGUE} 4"]
    # la fin est gardée : c'est là qu'est la traceback d'une sortie de tests
    assert observations[0].endswith("Traceback: fin 0")
    assert len(observations[0]) == DEBUT_ANCIENNE + len(OLD_NOTE) + FIN_ANCIENNE


def test_ne_touche_ni_la_question_ni_les_reponses_du_llm_ni_les_courtes():
    memoire = memoire_avec(3)
    memoire.append({"role": "user", "content": "Observation:\ncourte"})
    memoire.append({"role": "user", "content": "Observation:\nderniere"})
    raccourcir_anciennes_observations(memoire, garder=1)
    assert memoire[1]["content"] == "question"
    assert [m["content"] for m in memoire if m["role"] == "assistant"] == ["code 0", "code 1", "code 2"]
    assert {"role": "user", "content": "Observation:\ncourte"} in memoire


def test_deux_passages_donnent_le_meme_resultat():
    memoire = memoire_avec(4)
    raccourcir_anciennes_observations(memoire, garder=1)
    avant = [dict(m) for m in memoire]
    raccourcir_anciennes_observations(memoire, garder=1)
    assert memoire == avant


class SandboxLongue:
    """Imite Sandbox : chaque code affiche une longue sortie."""

    def execute(self, code):
        return ExecutionResult(success=True, output="x" * 2000, error="")


@pytest.fixture(autouse=True)
def sans_pause(monkeypatch):
    # agent_algo attend 12 s entre deux tours (quota Gemini) : inutile sans vrai LLM
    monkeypatch.setattr(agent_module.time, "sleep", lambda secondes: None)


def lancer(observations_completes):
    """4 tours qui lisent une longue sortie, puis la réponse finale : la dernière conversation envoyée."""
    code = ({"content": "Thought: je lis\n```python\nprint(1)\n```"}, None)
    client = FauxClient("A", [code] * 4 + [({"content": "Final Answer: fini"}, None)])
    agent = Agent("question", max_tours=10, client=client, sandbox=SandboxLongue(),
                  observations_completes=observations_completes)
    agent.agent_algo()
    return client.appels[-1]


def test_l_agent_envoie_une_conversation_plus_courte():
    complete, raccourcie = lancer(None), lancer(2)
    assert sum(map(len, raccourcie)) < sum(map(len, complete))
    observations = [m for m in raccourcie if m.startswith("Observation:")]
    assert [OLD_NOTE in o for o in observations] == [True, True, False, False]


def test_sans_option_rien_ne_change():
    assert all(OLD_NOTE not in m for m in lancer(None))
