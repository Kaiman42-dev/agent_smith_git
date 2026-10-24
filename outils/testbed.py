"""Où est le dépôt de la tâche SWE-bench, et comment y accéder sans en sortir (AS-41).

Le dépôt est toujours un dossier de l'hôte, donné par TESTBED_PATH :
- tests isolés des outils : la moulinette définit TESTBED_PATH avant de lancer le
  serveur MCP (sujet, p. 18) ;
- agent SWE-bench : /testbed est copié de l'image vers un dossier de l'hôte, monté
  sur /testbed dans le conteneur (agent_swebench). Les deux voient les mêmes fichiers.

Les outils tournent dans le serveur MCP, hors de la sandbox : c'est ici qu'on les
empêche de lire, écrire ou exécuter quoi que ce soit en dehors du dépôt.
"""

import os
import subprocess
from pathlib import Path

# Le dépôt vu depuis le conteneur, et les chemins qu'écrit le LLM (le prompt parle de /testbed)
CHEMIN_CONTENEUR = "/testbed"


def racine() -> Path:
    """Le dossier du dépôt sur l'hôte. PermissionError si TESTBED_PATH est absent ou n'existe pas."""
    valeur = os.environ.get("TESTBED_PATH")
    if not valeur:
        raise PermissionError("TESTBED_PATH is not set")
    dossier = Path(valeur).resolve()
    if not dossier.is_dir():
        raise PermissionError(f"the repository {valeur} does not exist")
    return dossier


def dans_le_depot(chemin: Path, base: Path | None = None) -> bool:
    """True si le chemin, liens symboliques suivis, reste dans le dépôt."""
    base = base or racine()
    reel = chemin.resolve()
    return reel == base or base in reel.parents


def chemin_local(chemin: str | None) -> Path:
    """Traduit un chemin donné par le LLM en chemin de l'hôte, dans le dépôt.

    Accepte /testbed/x (chemin du conteneur), x (relatif au dépôt) ou un chemin
    absolu dans TESTBED_PATH. Tout le reste lève PermissionError.
    """
    base = racine()
    if not chemin:
        return base
    texte = str(chemin)
    if texte == CHEMIN_CONTENEUR or texte.startswith(CHEMIN_CONTENEUR + "/"):
        texte = texte[len(CHEMIN_CONTENEUR):].lstrip("/")
    complet = Path(texte) if Path(texte).is_absolute() else base / texte
    if not dans_le_depot(complet, base):
        raise PermissionError(f"access denied: {chemin} is outside the repository")
    return complet.resolve()


def conteneur() -> str | None:
    """Le conteneur de la tâche (défini par agent_swebench), None pendant les tests isolés."""
    return os.environ.get("CONTAINER_NAME") or None


def chemin_affiche(chemin: Path) -> str:
    """Le chemin à montrer au LLM : /testbed/... s'il travaille avec un conteneur
    (ses commandes y tournent), sinon le chemin réel."""
    if conteneur() is None:
        return str(chemin)
    relatif = chemin.resolve().relative_to(racine())
    return CHEMIN_CONTENEUR if str(relatif) == "." else f"{CHEMIN_CONTENEUR}/{relatif}"


def executer(commande: str, workdir: str | None, timeout: int) -> subprocess.CompletedProcess:
    """Lance une commande shell dans le dépôt : dans le conteneur s'il y en a un,
    sinon dans TESTBED_PATH (tests isolés). workdir doit être dans le dépôt."""
    dossier = chemin_local(workdir)
    nom = conteneur()
    if nom is not None:
        dans_conteneur = chemin_affiche(dossier)
        cmd = ["docker", "exec", "-w", dans_conteneur, nom, "bash", "-c", commande]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return subprocess.run(["bash", "-c", commande], cwd=dossier, capture_output=True, text=True, timeout=timeout)
