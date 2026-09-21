import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODELE = "llama2"
SYSTEM = "Tu es un agent intelligent capable d'utiliser des outils pour répondre aux questions."
SCHEMA = 

def addition(a: float, b: float) -> float:
    """Additionne deux nombres."""
    return float(a) + float(b)

def multiplication(a: float, b: float) -> float:
    """Multiplie deux nombres."""
    return float(a) * float(b)

OUTILS = {"addition": addition, "multiplication": multiplication}


class agent:
    def __init__(self, messages, question, max_tours):
        self.messages = messages
        self.question = question
        self.max_tours = max_tours

    def appel_llm(messages: list[dict]) -> dict:
        """Envoie la conversation au modèle et renvoie son message de réponse. c'est la parti thinking du ReAct"""
        corps = json.dump(
            {"model": MODELE, "message": messages, "tools": SCHEMA, "stream": False }
        ).encode()
        requete = urllib.request.Request(
            OLLAMA_URL, data=corps, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(requete, timeout=300) as response: #envoie la requete au serveur ollama
            return json.load(response)["message"]

    def agent(question: str, max_tours: int = 6) -> tuple[str, list[str]]:
        """fait tourner la boucle think->act->observe jusqu'a la reponse"""
        memoire=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question}  
        ]
        trace: list[str] = []

        for _ in range(max_tours):
            message = agent.appel_llm(memoire) # parti de thinking
            memoire.append(message) # je sauvegarde la reponse du llm en mémoire

            appels = message.get("tool_calls") # 
            if not appels:  # si aucun outil n'est appelé on a donc notre reponse finale
                return message["content"], trace

            for appel in appels: # Act : execute les outils appelés par le llm
                nom = appel["function"]["name"]
                arguments = appel["function"]["arguments"]
                resultat = OUTILS[nom](**arguments)
                trace.append(f"{nom}({arguments}) = {resultat}")
                memoire.append(
                    {"role": "tool", "tool_name": nom, "content": str(resultat)}
                )
        return "nombre maximum de tours atteint", trace

