"""Teste chaque cle Gemini et Groq du .env et met en commentaire celles qui sont refusees.

    cp .env .env.bak          # sauvegarde d'abord
    uv run python tester_cles.py

Deux tests par cle : lister les modeles (la cle est-elle valide ?), puis une toute petite
generation avec le modele par defaut (la cle a-t-elle le droit de l'utiliser ?).
N'affiche jamais les cles : seulement le nom de la variable et le resultat.
"""
import json
import re
import urllib.error
import urllib.request

from dotenv import dotenv_values

URLS = {
    "GEMINI": "https://generativelanguage.googleapis.com/v1beta/openai",
    "GROQ": "https://api.groq.com/openai/v1",
}
MODELES = {"GEMINI": "gemini-3.6-flash", "GROQ": "openai/gpt-oss-120b"}  # ceux de models.json
REFUSEE = (401, 403)  # cle refusee ; un 429 (quota) ou un 503 (serveur) n'est PAS une raison de la retirer


def tester(url, cle, corps=None):
    """Code HTTP de la requete, et le debut du message d'erreur du fournisseur s'il y en a un."""
    requete = urllib.request.Request(url, data=corps, headers={
        "Authorization": f"Bearer {cle}", "User-Agent": "agent-smith/0.1",
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=60) as reponse:
            return reponse.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace").replace("\n", " ")[:150]


invalides = []
for nom, cle in dotenv_values(".env").items():
    fournisseur = nom.split("_")[0]
    if fournisseur not in URLS or not cle:
        continue
    base, cle = URLS[fournisseur], cle.strip()
    corps = json.dumps({"model": MODELES[fournisseur], "max_tokens": 50,
                        "messages": [{"role": "user", "content": "Reply OK"}]}).encode()
    try:
        liste, _ = tester(base + "/models", cle)
        generation, message = tester(base + "/chat/completions", cle, corps)
    except Exception as e:
        print(f"{nom:20} ERREUR {type(e).__name__} (gardee : peut-etre un souci reseau)")
        continue
    print(f"{nom:20} liste={liste}  generation={generation}  {message}")
    if liste in REFUSEE or generation in REFUSEE:
        invalides.append(nom)

if invalides:
    with open(".env") as f:
        lignes = f.read().splitlines()
    with open(".env", "w") as f:
        for ligne in lignes:
            m = re.match(r"\s*([A-Z_0-9]+)\s*=", ligne)
            f.write(("# INVALIDE " + ligne if m and m.group(1) in invalides else ligne) + "\n")
    print("\nMises en commentaire :", ", ".join(invalides))
else:
    print("\nAucune cle refusee.")
