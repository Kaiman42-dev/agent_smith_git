from agent_algo import agent
import agent_algo.agent as module_agent


class FauxClient:
    def __init__(self):
        pass

    def appel_llm(self, messages):
        return None, 429  # Simule une erreur 429 pour tester le basculement

class FauxClientFinal:
    def __init__(self):
        self.input_tokens = 10
        self.output_tokens = 20
        self.temps_ms = 100
        self.retries = 0
        self.adress = "https://api.openai.com/v1/chat/completions"
        self.modele = "gpt-4"

    def appel_llm(self, messages):
        return {"content": "Final Answer: Voici la réponse finale."}, None
    
def test_bascule(monkeypatch):

    def faux_creer_client(index_fournisseur):
        if index_fournisseur == 0:
            return FauxClient()  # Premier fournisseur qui échoue
        else:
            return FauxClientFinal()  # Deuxième fournisseur qui réussit
        
    monkeypatch.setattr(module_agent, "creer_client", faux_creer_client)
    agent = module_agent.Agent("Quelle est la capitale de la France?", 3, FauxClient())
    reponse, steps = agent.agent_algo()
    assert reponse == "Voici la réponse finale."
    assert agent.index_fournisseur == 1  # Vérifie que le basculement a eu lieu

