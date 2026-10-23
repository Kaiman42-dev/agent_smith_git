"""Tests de l'extraction de la solution MBPP (AS-39) à partir de la réponse et des étapes, sans réseau."""
from agent_mbpp.__main__ import solution_from_answer
from models_public import StepMetrics

BONNE = "def multiply_int(x, y):\n    return x * y"
FAUSSE = "def multiply_int(x, y):\n    return x + y"


def step(n, code, sortie):
    return StepMetrics(step=n, input_tokens=0, output_tokens=0, request_time_ms=0.0,
                       sandbox_input=code, sandbox_output=sortie)


def dans_une_chaine(fonction):
    """le format demandé par PROMPT_MBPP"""
    return (f"code = '''{fonction}'''\n"
            "result = run_tests(code=code, test_list=tests)\nprint(result)\n")


def test_final_answer_avec_le_code():
    reponse = BONNE + "\n\nassert multiply_int(2, 3) == 6"
    assert solution_from_answer(reponse, [], "multiply_int") == BONNE  # l'assert est retiré


def test_code_dans_une_chaine_et_final_answer_inutilisable():
    # le cas de laguna (tâche 127) : tests réussis, mais final_answer reçoit autre chose que le code
    steps = [step(1, dans_une_chaine(BONNE), '{"success": true, "output": ""}')]
    assert solution_from_answer('""', steps, "multiply_int") == BONNE


def test_priorite_au_code_dont_les_tests_ont_reussi():
    steps = [
        step(1, dans_une_chaine(FAUSSE), '{"success": false, "output": "AssertionError"}'),
        step(2, dans_une_chaine(BONNE), '{"success": true, "output": ""}'),
        step(3, dans_une_chaine(FAUSSE), "(the code ran without error and printed nothing)"),
    ]
    assert solution_from_answer("", steps, "multiply_int") == BONNE


def test_fonction_definie_directement():
    steps = [step(1, BONNE + "\nprint(multiply_int(2, 3))", "6\n")]
    assert solution_from_answer("", steps, "multiply_int") == BONNE


def test_une_etape_sans_solution_n_arrete_pas_la_recherche():
    # avant AS-39, la première étape examinée renvoyait "" et la recherche s'arrêtait
    steps = [
        step(1, BONNE, "(the code ran without error and printed nothing)"),
        step(2, "print('def multiply_int est prêt')", "def multiply_int est prêt\n"),
    ]
    assert solution_from_answer("", steps, "multiply_int") == BONNE


def test_chaine_qui_ne_compile_pas_ignoree():
    steps = [
        step(1, dans_une_chaine(BONNE), '{"success": true, "output": ""}'),
        step(2, dans_une_chaine("def multiply_int(x, y) return"), '{"success": false, "output": ""}'),
    ]
    assert solution_from_answer("", steps, "multiply_int") == BONNE


def test_rien_trouve():
    assert solution_from_answer("Final Answer: 42", [step(1, "print(1)", "1\n")], "multiply_int") == ""
