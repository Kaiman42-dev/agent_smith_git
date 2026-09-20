import json


def addition(a: float, b: float) -> float:
    """Additionne deux nombres."""
    return float(a) + float(b)

def multiplication(a: float, b: float) -> float:
    """Multiplie deux nombres."""
    return float(a) * float(b)

OUTILS = {"addition": addition, "multiplication": multiplication}


def appel_llm(messages: list[dict]) -> dict:
    """Envoie la conversation au modèle et renvoie son message de réponse."""
    corps = json.dump(
        {"model": MODELE, "message": messages, "tools": SCHEMA, "stream": False }
    ).encode()
    requete = urllib.request.Request(
        OLLAMA_URL, data=corps, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(requete, timeout=300) as response:
        return json.loap(response)["message"]