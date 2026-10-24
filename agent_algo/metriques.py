"""Métriques d'un run pour le benchmark (AS-31), écrites dans <solution>.metrics.json.

solution.json suit le format imposé par la moulinette (models_public.py, identique au
sien) : on ne peut pas y ajouter de champs. Ce qui manque va dans un fichier à côté.
"""

import json
import logging
import re
from pathlib import Path

from agent_algo.config import ModelsConfig
from models_public import SolutionOutput


def fichiers_du_patch(patch: str) -> list[str]:
    """Les fichiers modifiés par un patch git ("diff --git a/x b/x")."""
    return re.findall(r"^diff --git a/(\S+) b/", patch, re.MULTILINE)


def echecs_tests(sortie: str) -> int | None:
    """Nombre de tests en échec d'après ce qu'a affiché run_tests(), None si illisible."""
    # MBPP : run_tests renvoie {"success": ..., "output": ...} et s'arrête au premier assert faux
    m = re.search(r"""["']success["']\s*:\s*(true|false)""", sortie, re.IGNORECASE)
    if m:
        return 0 if m.group(1).lower() == "true" else 1
    # SWE-bench : résumé de pytest ("2 failed, 10 passed") ou du lanceur de sympy (même format)
    echecs = sum(int(n) for n in re.findall(r"(\d+) (?:failed|errors?)\b", sortie))
    if echecs or re.search(r"\d+ passed", sortie):
        return echecs
    return None


def metriques_intermediaires(sortie: SolutionOutput) -> dict:
    """Comment l'agent arrive à la solution, étape par étape (sujet, benchmark)."""
    steps = sortie.steps
    fichiers = fichiers_du_patch(sortie.solution) if sortie.benchmark == "swebench" else []
    # première étape dont le code cite un fichier du patch final (lecture ou modification)
    premiere_touche = next((s.step for s in steps if any(f in s.sandbox_input for f in fichiers)), None)

    # nombre d'échecs à chaque appel de run_tests() dont on sait lire la sortie
    runs = [(s.step, echecs_tests(s.sandbox_output)) for s in steps if "run_tests(" in s.sandbox_input]
    runs = [(step, n) for step, n in runs if n is not None]
    premiere_baisse = next((runs[i][0] for i in range(1, len(runs)) if runs[i][1] < runs[i - 1][1]), None)
    tests_ok = next((step for step, n in runs if n == 0), None)
    # la réponse finale est la dernière étape d'un run réussi
    tours_apres = steps[-1].step - tests_ok if tests_ok is not None and sortie.success else None

    return {
        "patch_files": fichiers,
        "first_patch_file_step": premiere_touche,
        "test_failures": [{"step": step, "failures": n} for step, n in runs],
        "first_failure_drop_step": premiere_baisse,
        "tests_pass_step": tests_ok,
        "steps_after_tests_pass": tours_apres,
    }


def calculer_metriques(sortie: SolutionOutput, modele: str, fournisseur: str,
                       incidents: list | None = None, bascules: list | None = None) -> dict:
    """Toutes les métriques d'un run. incidents et bascules viennent de l'Agent (vides si inconnus)."""
    steps = sortie.steps
    return {
        "task_id": sortie.task_id,
        "benchmark": sortie.benchmark,
        "model": modele,
        "provider": fournisseur,
        "models_used": sorted({s.model_name for s in steps}),  # plusieurs si l'agent a basculé
        "success": sortie.success,
        "iterations": sortie.iterations,
        "total_input_tokens": sortie.total_input_tokens,
        "total_output_tokens": sortie.total_output_tokens,
        "input_tokens_per_step": [s.input_tokens for s in steps],
        "output_tokens_per_step": [s.output_tokens for s in steps],
        "total_time_seconds": sortie.total_time_seconds,
        "request_time_ms_per_step": [s.request_time_ms for s in steps],
        "total_requests": sortie.total_requests,
        "total_retries": sum(s.retries for s in steps),
        "provider_errors": list(incidents or []),
        "fallbacks": list(bascules or []),
        **metriques_intermediaires(sortie),
    }


def metriques_du_run(sortie: SolutionOutput, client, config: ModelsConfig, agent=None) -> dict:
    """Métriques d'un run des CLI. client : le client de départ (avant bascule).
    agent vaut None si le run a planté avant sa création."""
    return calculer_metriques(sortie, client.modele, config.nom_pour_url(client.adress),
                              agent.incidents if agent else [], agent.bascules if agent else [])


def chemin_metriques(chemin_solution: str | Path) -> Path:
    """solution.json -> solution.metrics.json"""
    return Path(chemin_solution).with_suffix(".metrics.json")


def ecrire_metriques(chemin_solution: str | Path, metriques: dict) -> Path | None:
    """Écrit les métriques à côté de solution.json. Un échec ne doit jamais faire perdre la solution."""
    chemin = chemin_metriques(chemin_solution)
    try:
        chemin.write_text(json.dumps(metriques, indent=2, ensure_ascii=False))
        return chemin
    except OSError as e:
        logging.warning(f"Métriques non écrites dans {chemin} : {e.strerror}")
        return None
