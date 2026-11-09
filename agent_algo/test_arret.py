"""exit() ou Ctrl+C dans le code du LLM : l'agent s'arrête proprement (sujet, V.2), sans réseau."""
import pytest

from agent_algo.agent import Agent
from agent_algo.test_bascule import FauxClient
from sandbox.parent import Sandbox


@pytest.mark.parametrize("code, exception", [("exit()", "SystemExit"),
                                             ("raise KeyboardInterrupt", "KeyboardInterrupt")])
def test_l_agent_s_arrete_et_garde_le_tour(code, exception):
    client = FauxClient("A", [({"content": f"```python\n{code}\n```"}, None)])
    with Sandbox() as sandbox:
        agent = Agent("question", max_tours=10, client=client, sandbox=sandbox)
        reponse, steps = agent.agent_algo()  # ne lève rien : main() pourra écrire solution.json
    assert exception in reponse
    assert not agent.succes
    assert len(steps) == 1                       # le tour est enregistré...
    assert exception in steps[0].sandbox_output  # ...avec la raison de l'arrêt
