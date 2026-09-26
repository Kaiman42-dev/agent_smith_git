import json
import urllib.request
import urllib.error
from dotenv import load_dotenv
import os
import logging

class ClientLLM:
    def __init__(self, adress, modele, key):
        self.adress = adress
        self.modele = modele
        self.key = key
    
    def appel_llm(self, messages):
        """Envoie la conversation au modèle et renvoie son message de réponse"""
        corps = json.dumps(
            {"model": self.modele, "messages": messages, "stream": False }
        ).encode()
        requete = urllib.request.Request(
            self.adress, data=corps, headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"} # c'est ce qui est envoyé a l'API, avec la clé
        )
        i = 0
        while i <= 5:
            try:
                with urllib.request.urlopen(requete, timeout=300) as response: #envoie la requete au serveur
                    return json.load(response)["choices"][0]["message"] # retourne la reponse du serveur
            except urllib.error.HTTPError as e:
                logging.error(f"Echec HTTP. Code {e.code}, Raison {e.reason}")
                # je distingue les erreurs 400 et 404 pour ne pas réessayer inutilement (erreures de requete ou ressource non trouvée)
                if e.code in(400, 404): 
                    return None
                i = i + 1
                pass
            except urllib.error.URLError as e:
                logging.error(f"Echec URL. Raison {e.reason}")
                i = i + 1
                pass
        return None

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
            if message is None:  # si le llm ne repond pas on sort de la boucle
                return "le llm ne repond pas", trace
            memoire.append(message) # je sauvegarde la reponse du llm en mémoire

            appels = message.get("tool_calls") 
            if not appels:  # si aucun outil n'est appelé on a donc notre reponse finale
                return message["content"], trace

        return "nombre maximum de tours atteint", trace

if __name__ == "__main__":
    try:
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        client = ClientLLM(adress="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                        , modele="gemini-3.6-flash", key=api_key)
        test = Agent(question="combien font 2 +2", max_tours=6, client=client)
        res = test.agent_algo()
        print(res)
    except Exception as e:
        logging.error(f"Erreur lors de l'exécution de l'agent: {e}")
    
