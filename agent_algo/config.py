"""Configuration des modèles et fournisseurs LLM, décrite avec Pydantic (sujet, chapitre VIII).

Chargée depuis models.json, à la racine du projet, comme sandbox_template.json pour la sandbox.
L'ordre de `providers` est l'ordre de bascule quand un fournisseur ne répond plus.
"""

from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, model_validator

MODELS_JSON = Path(__file__).resolve().parent.parent / "models.json"


class Provider(BaseModel):
    name: str
    # URL de base compatible OpenAI, sans /chat/completions (comme --provider-url)
    url: str
    # Variable d'environnement qui contient la clé API (jamais la clé elle-même)
    api_key_env: str
    # Modèle utilisé quand l'agent bascule sur ce fournisseur
    fallback_model: str

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or ""


class ModelsConfig(BaseModel):
    # Utilisés quand --provider-url / --model-name ne sont pas donnés
    default_provider: str
    default_model: str
    providers: list[Provider]

    @model_validator(mode="after")
    def verifier(self):
        noms = [p.name for p in self.providers]
        if len(set(noms)) != len(noms):
            raise ValueError(f"noms de fournisseurs en double : {noms}")
        if self.default_provider not in noms:
            raise ValueError(f"default_provider '{self.default_provider}' absent de providers {noms}")
        return self

    def fournisseur(self, nom: str) -> Provider:
        return next(p for p in self.providers if p.name == nom)

    def fournisseur_pour_url(self, url: str) -> Provider | None:
        """Le fournisseur qui a le même domaine que l'URL, ou None s'il est inconnu."""
        host = urlparse(url).hostname or ""
        return next((p for p in self.providers if p.host == host), None)

    def nom_pour_url(self, url: str) -> str:
        """Le nom du fournisseur de l'URL, ou son domaine s'il n'est pas dans models.json."""
        fournisseur = self.fournisseur_pour_url(url)
        return fournisseur.name if fournisseur else urlparse(url).hostname or ""


def charger_config(path: Path | str = MODELS_JSON) -> ModelsConfig:
    """Lit et valide models.json. Lève ValueError si le fichier est illisible ou invalide."""
    try:
        texte = Path(path).read_text()
    except OSError as e:
        raise ValueError(f"impossible de lire {path} : {e.strerror}") from e
    # ValidationError de Pydantic est une sous-classe de ValueError
    return ModelsConfig.model_validate_json(texte)
