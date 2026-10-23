"""Tableaux Markdown du benchmark (pour BENCHMARK_REPORT.md) à partir des runs de l'agent.

    uv run python -m agent_algo.rapport cache/bench [autres dossiers ou fichiers...]

Lit chaque solution.json et, s'il existe, le solution.metrics.json écrit à côté par les CLI.
Pour un ancien run sans fichier de métriques, elles sont recalculées depuis solution.json,
mais sans les erreurs des fournisseurs ni les bascules (qui n'y sont pas enregistrées).
"""

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

from agent_algo.config import charger_config
from agent_algo.metriques import calculer_metriques, chemin_metriques
from models_public import SolutionOutput

INCONNU = "(inconnu)"


def charger_runs(chemins) -> list[dict]:
    """Les métriques de chaque solution.json trouvé (les autres fichiers JSON sont ignorés)."""
    config = charger_config()
    fichiers = []
    for chemin in map(Path, chemins):
        fichiers += sorted(chemin.rglob("*.json")) if chemin.is_dir() else [chemin]

    runs = []
    for fichier in fichiers:
        if fichier.name.endswith(".metrics.json"):
            continue
        try:
            sortie = SolutionOutput.model_validate_json(fichier.read_text())
        except (OSError, ValueError):  # pas un solution.json (task.json...), ValidationError compris
            continue
        metriques = chemin_metriques(fichier)
        if metriques.exists():
            runs.append(json.loads(metriques.read_text()))
        else:
            premier = sortie.steps[0] if sortie.steps else None
            modele = premier.model_name if premier else INCONNU
            fournisseur = config.nom_pour_url(premier.api_url) if premier else INCONNU
            runs.append(calculer_metriques(sortie, modele, fournisseur))
    return runs


def moyenne(valeurs) -> str:
    valeurs = [v for v in valeurs if v is not None]
    return f"{mean(valeurs):.1f}" if valeurs else "-"


def case(valeur) -> str:
    return "-" if valeur is None else str(valeur)


def tableau(entetes, lignes) -> str:
    md = ["| " + " | ".join(entetes) + " |", "|" + "---|" * len(entetes)]
    md += ["| " + " | ".join(case(c) for c in ligne) + " |" for ligne in lignes]
    return "\n".join(md)


def tableau_par_modele(runs) -> str:
    groupes = {}
    for r in runs:
        groupes.setdefault((r["benchmark"], r["model"], r["provider"]), []).append(r)
    lignes = []
    for (benchmark, modele, fournisseur), rs in sorted(groupes.items()):
        temps_llm = [t for r in rs for t in r["request_time_ms_per_step"]]
        lignes.append([
            benchmark, modele, fournisseur,
            f"{sum(r['success'] for r in rs)}/{len(rs)}",
            moyenne(r["iterations"] for r in rs),
            moyenne(r["total_input_tokens"] for r in rs),
            moyenne(r["total_output_tokens"] for r in rs),
            moyenne(r["total_time_seconds"] for r in rs),
            moyenne(temps_llm),
            sum(r["total_retries"] for r in rs),
            sum(len(r["provider_errors"]) for r in rs),
            sum(len(r["fallbacks"]) for r in rs),
        ])
    return tableau(["Benchmark", "Modèle", "Fournisseur", "Réussites", "Itérations moy.",
                    "Tokens entrée moy.", "Tokens sortie moy.", "Durée moy. (s)",
                    "Réponse LLM moy. (ms)", "Retries", "Erreurs fournisseur", "Bascules"], lignes)


def tableau_par_run(runs) -> str:
    lignes = [[
        r["benchmark"], r["task_id"], r["model"], "oui" if r["success"] else "non",
        r["iterations"], r["total_input_tokens"], r["total_output_tokens"],
        f"{r['total_time_seconds']:.1f}", r["first_patch_file_step"],
        r["first_failure_drop_step"], r["tests_pass_step"], r["steps_after_tests_pass"],
    ] for r in sorted(runs, key=lambda r: (r["benchmark"], str(r["task_id"]), r["model"]))]
    return tableau(["Benchmark", "Tâche", "Modèle", "Réussite", "Itérations", "Tokens entrée",
                    "Tokens sortie", "Durée (s)", "1er fichier du patch (étape)",
                    "1re baisse des échecs (étape)", "Tests OK (étape)", "Tours ensuite"], lignes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("chemins", nargs="+", help="dossiers ou fichiers solution.json")
    args = parser.parse_args(argv)

    runs = charger_runs(args.chemins)
    if not runs:
        sys.exit("Aucun solution.json trouvé.")
    print("## Résultats par modèle\n")
    print(tableau_par_modele(runs))
    print("\n## Détail des runs\n")
    print(tableau_par_run(runs))


if __name__ == "__main__":
    main()
