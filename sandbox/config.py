"""Configuration de la sandbox : les limites, décrites avec Pydantic.

Pydantic valide les valeurs et sait charger la config depuis un fichier JSON
(voir cli.load_config). C'est cet objet que le parent passe à l'enfant au démarrage.

Les valeurs par défaut sont celles imposées par le sujet (section V.2).
"""

from pydantic import BaseModel, Field
from typing import List


class SandboxConfig(BaseModel):
    # Temps de calcul maximum pour UN bloc de code, en secondes (au-delà : timeout)
    max_execution_time_seconds: int = 30

    # Mémoire maximale du processus sandbox, en Mo (appliquée sur Linux)
    max_memory_mb: int = 512

    # Dossiers que le code du LLM a le droit de lire/écrire ; tout le reste est refusé
    allowed_directories: List[str] = Field(default_factory=lambda: [
        "/testbed", "/tmp/agent"
    ])

    # Modules que le LLM a le droit d'importer. Un suffixe ".*" autorise aussi les
    # sous-modules (ex : "collections.*" permet "collections.abc").
    authorized_imports: List[str] = Field(default_factory=lambda: [
        "math", "math.*", "collections", "collections.*",
        "itertools", "re", "json", "typing", "typing.*",
        "functools", "operator", "heapq", "bisect", "copy",
        "string", "random", "datetime", "datetime.*",
        "array", "cmath",
    ])
