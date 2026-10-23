"""Tests des métriques du benchmark (AS-31) : calcul, fichier metrics.json et rapport, sans réseau."""
import json

from agent_algo import rapport
from agent_algo.agent import Agent
from agent_algo.metriques import (calculer_metriques, echecs_tests, ecrire_metriques,
                                  fichiers_du_patch, metriques_intermediaires)
from agent_algo.test_bascule import REPONSE_OK, FauxClient
from models_public import SolutionOutput, StepMetrics

PATCH = "diff --git a/sympy/core/expr.py b/sympy/core/expr.py\n--- a/sympy/core/expr.py\n+++ b/sympy/core/expr.py\n"


def step(n, code="", sortie="", **champs):
    valeurs = dict(step=n, input_tokens=100 * n, output_tokens=10 * n, request_time_ms=500.0,
                   model_name="m", api_url="https://openrouter.ai/api/v1/chat/completions",
                   sandbox_input=code, sandbox_output=sortie)
    valeurs.update(champs)
    return StepMetrics(**valeurs)


def solution(steps, benchmark="swebench", succes=True, patch=PATCH):
    return SolutionOutput(task_id="sympy__sympy-1", benchmark=benchmark, success=succes, solution=patch,
                          iterations=len(steps), total_requests=len(steps),
                          total_input_tokens=sum(s.input_tokens for s in steps),
                          total_output_tokens=sum(s.output_tokens for s in steps),
                          total_time_seconds=12.5, steps=steps)


# un run SWE-bench typique : chercher, lire le bon fichier, corriger jusqu'à ce que les tests passent
RUN = solution([
    step(1, "print(read_file('/testbed/README.md'))", "..."),
    step(2, "print(read_file('/testbed/sympy/core/expr.py'))", "..."),
    step(3, "print(run_tests())", "tests finished: 5 passed, 3 failed, in 2.1 seconds"),
    step(4, "replace_in_file(...)\nprint(run_tests())", "===== 1 failed, 7 passed in 1.2s ====="),
    step(5, "print(run_tests())", "===== 8 passed in 1.1s =====", retries=2),
    step(6, "final_answer(get_patch())", ""),
])


def test_echecs_tests_mbpp():
    assert echecs_tests('{"success": true, "output": ""}') == 0
    assert echecs_tests('{"success": false, "output": "AssertionError"}') == 1
    assert echecs_tests("{'success': False, 'output': ''}") == 1  # dict affiché par print()


def test_echecs_tests_pytest_et_sympy():
    assert echecs_tests("== 2 failed, 1 error, 10 passed in 3s ==") == 3
    assert echecs_tests("tests finished: 12 passed, in 0.5 seconds") == 0


def test_echecs_tests_sortie_illisible():
    assert echecs_tests("Error: Timeout after 300 seconds.") is None


def test_fichiers_du_patch():
    patch = PATCH + "diff --git a/sympy/tests/test_expr.py b/sympy/tests/test_expr.py\n"
    assert fichiers_du_patch(patch) == ["sympy/core/expr.py", "sympy/tests/test_expr.py"]


def test_metriques_intermediaires_swebench():
    m = metriques_intermediaires(RUN)
    assert m["first_patch_file_step"] == 2
    assert m["test_failures"] == [{"step": 3, "failures": 3}, {"step": 4, "failures": 1},
                                  {"step": 5, "failures": 0}]
    assert m["first_failure_drop_step"] == 4
    assert m["tests_pass_step"] == 5
    assert m["steps_after_tests_pass"] == 1


def test_pas_de_tours_apres_si_le_run_echoue():
    m = metriques_intermediaires(RUN.model_copy(update={"success": False}))
    assert m["tests_pass_step"] == 5 and m["steps_after_tests_pass"] is None


def test_mbpp_sans_fichier_de_patch():
    run = solution([step(1, "print(run_tests(code, tests))", '{"success": true, "output": ""}')],
                   benchmark="mbpp", patch="def f(): pass")
    m = metriques_intermediaires(run)
    assert m["patch_files"] == [] and m["first_patch_file_step"] is None
    assert m["tests_pass_step"] == 1 and m["steps_after_tests_pass"] == 0


def test_calculer_metriques():
    m = calculer_metriques(RUN, "m", "openrouter", incidents=[{"step": 2, "model": "m", "error": "503"}])
    assert m["input_tokens_per_step"] == [100, 200, 300, 400, 500, 600]
    assert m["total_input_tokens"] == 2100 and m["total_retries"] == 2
    assert m["provider_errors"] == [{"step": 2, "model": "m", "error": "503"}] and m["fallbacks"] == []
    json.dumps(m)  # doit pouvoir s'écrire en JSON


def test_l_agent_note_les_erreurs_et_les_bascules():
    principal, secours = FauxClient("A", [(None, 503)]), FauxClient("B", [REPONSE_OK])
    agent = Agent("question", max_tours=5, client=principal, sandbox=None, secours=[secours])
    agent.agent_algo()
    assert agent.incidents == [{"step": 1, "model": "A", "error": "503"}]
    assert agent.bascules == [{"step": 1, "from": "A", "to": "B", "code": 503}]


def test_ecrire_metriques_a_cote_de_la_solution(tmp_path):
    chemin = ecrire_metriques(tmp_path / "solution.json", {"a": 1})
    assert chemin == tmp_path / "solution.metrics.json"
    assert json.loads(chemin.read_text()) == {"a": 1}


def test_ecrire_metriques_ne_plante_jamais(tmp_path):
    assert ecrire_metriques(tmp_path / "absent" / "solution.json", {}) is None


def test_rapport(tmp_path, capsys):
    # un ancien run (sans metrics.json), un run récent (avec), et un task.json à ignorer
    (tmp_path / "ancien.json").write_text(RUN.model_dump_json())
    (tmp_path / "recent.json").write_text(RUN.model_dump_json())
    recent = calculer_metriques(RUN, "modele-recent", "groq", bascules=[{"step": 1}])
    (tmp_path / "recent.metrics.json").write_text(json.dumps(recent))
    (tmp_path / "task.json").write_text('{"task_id": 1}')

    runs = rapport.charger_runs([tmp_path])
    assert sorted((r["model"], r["provider"]) for r in runs) == [("m", "openrouter"), ("modele-recent", "groq")]

    rapport.main([str(tmp_path)])
    sortie = capsys.readouterr().out
    assert "| swebench | modele-recent | groq | 1/1 |" in sortie
    assert "| swebench | sympy__sympy-1 | m | oui | 6 |" in sortie
