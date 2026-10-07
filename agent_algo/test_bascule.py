from agent_algo.agent import Agent, creer_client


class FauxClient:
    def __init__(self, message):
        self.message = message
    def appel_llm(self):
        return None, 429  # Simule une erreur 429 pour tester le basculement

def test_bascule():
    pass

    def faux_creer_client(index_fournisseur):
        pass
