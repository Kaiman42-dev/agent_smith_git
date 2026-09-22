from builtins import float
import json
import urllib.request


class ClientLLM:
    def __init__(self, adress, modele):
        self.adress = adress
        self.modele = modele
    
    def appel_llm(self, messages):
        """Envoie la conversation au modèle et renvoie son message de réponse. c'est la parti thinking du ReAct"""
        corps = json.dumps(
            {"model": self.modele, "messages": messages, "stream": False }
        ).encode()
        requete = urllib.request.Request(
            self.adress, data=corps, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(requete, timeout=300) as response: #envoie la requete au serveur ollama
            return json.load(response)["message"]

class Agent:
    def __init__(self, question, max_tours, client):
        self.question = question
        self.max_tours = max_tours
        self.client = client

    def agent_algo(self) -> tuple[str, list[str]]:
        """fait tourner la boucle think->act->observe jusqu'a la reponse"""
        memoire=[
            {"role": "system", "content": "tu doit repondre au question de code"},
            {"role": "user", "content": self.question}  
        ]
        trace: list[str] = []

        for _ in range(self.max_tours):
            message = self.client.appel_llm(memoire) # parti de thinking
            memoire.append(message) # je sauvegarde la reponse du llm en mémoire

            appels = message.get("tool_calls") # 
            if not appels:  # si aucun outil n'est appelé on a donc notre reponse finale
                return message["content"], trace

            
        print(message)
        return "nombre maximum de tours atteint", trace

if __name__ == "__main__":
    
    client = ClientLLM(adress="http://localhost:11434/api/chat", modele="qwen3:1.7b")
    test = Agent(question="combien font 2 +2", max_tours=6, client=client)
    res = test.agent_algo()
    print(res)
    
