"""Tests de l'extraction multi-format (sujet, V.1) : Python, XML, JSON/Hermes, ReAct, sans réseau."""
import io
import json
import urllib.error
import urllib.request

from Extraction_llm import extraire_code
from agent_algo.agent import Agent, ClientLLM, generation_refusee
from agent_algo.test_bascule import FauxClient
from agent_algo.test_observation import FausseSandbox

XML = """Thought: je lis le fichier
<invoke name="read_file">
<parameter name="filepath">/testbed/a.py</parameter>
<parameter name="start_line">1</parameter>
<parameter name="end_line">20</parameter>
</invoke>"""

HERMES = '<tool_call>{"name": "read_file", "arguments": {"filepath": "/testbed/a.py", "start_line": 1}}</tool_call>'

REACT = """Thought: je cherche
Action: search_code
Action Input: {"pattern": "def main", "path": "/testbed"}
Thought: (le LLM continue d'écrire)"""


def executer(code):
    """Exécute le code produit avec un faux outil, renvoie les appels reçus."""
    appels = []
    outil = lambda *args, **kwargs: appels.append((args, kwargs)) or "ok"
    exec(code, {"read_file": outil, "search_code": outil, "print": lambda *a: None})
    return appels


def test_bloc_python():
    assert extraire_code("Thought: x\n```python\nprint(1)\n```") == "print(1)\n"


def test_bloc_py_suivi_de_end_code():
    assert extraire_code("Code:\n```py\nprint(1)\n```<end_code>") == "print(1)\n"


def test_end_code_dans_le_bloc_est_retire():
    assert extraire_code("```python\nprint(1)\n<end_code>\n```") == "print(1)\n\n"


def test_sans_code_renvoie_none():
    assert extraire_code("Thought: je réfléchis encore") is None
    assert extraire_code("") is None


def test_xml_converti_avec_les_bons_types():
    assert executer(extraire_code(XML)) == [((), {"filepath": "/testbed/a.py", "start_line": 1, "end_line": 20})]


def test_xml_parametre_contenant_du_code_garde_tel_quel():
    texte = '<invoke name="read_file"><parameter name="filepath">if a < b and c > d:</parameter></invoke>'
    assert executer(extraire_code(texte)) == [((), {"filepath": "if a < b and c > d:"})]


def test_xml_plusieurs_appels():
    texte = XML + "\n" + XML.replace("a.py", "b.py")
    chemins = [kw["filepath"] for _, kw in executer(extraire_code(texte))]
    assert chemins == ["/testbed/a.py", "/testbed/b.py"]


def test_json_generique_pour_n_importe_quel_outil():
    texte = '<tool_call>{"name": "search_code", "arguments": {"pattern": "x", "max_results": 5}}</tool_call>'
    assert executer(extraire_code(texte)) == [((), {"pattern": "x", "max_results": 5})]


def test_json_lit_read_file():
    assert executer(extraire_code(HERMES)) == [((), {"filepath": "/testbed/a.py", "start_line": 1})]


def test_json_arguments_en_chaine():
    texte = '<tool_call>{"name": "search_code", "arguments": "{\\"pattern\\": \\"x\\"}"}</tool_call>'
    assert executer(extraire_code(texte)) == [((), {"pattern": "x"})]


def test_json_mal_forme_renvoie_none_et_pas_error():
    assert extraire_code('<tool_call>{"name": "read_file", "arguments": </tool_call>') is None


def test_react_ignore_le_texte_apres_le_json():
    assert executer(extraire_code(REACT)) == [((), {"pattern": "def main", "path": "/testbed"})]


def test_react_entree_en_texte_simple():
    assert executer(extraire_code("Action: search_code\nAction Input: def main")) == [(("def main",), {})]


def test_python_prioritaire_sur_les_autres_formats():
    assert extraire_code("```python\nprint(1)\n```\n" + XML) == "print(1)\n"


def test_le_code_produit_affiche_le_resultat():
    assert extraire_code(HERMES).endswith("print(result)\n")


def test_nom_d_outil_non_identifiant_refuse():
    # sans ce contrôle, le nom serait du code arbitraire dans la sandbox
    assert extraire_code('<tool_call>{"name": "__import__(\'os\').system", "arguments": {}}</tool_call>') is None
    assert extraire_code('<invoke name="x); import os; (y"></invoke>') is None
    assert extraire_code("Action: import\nAction Input: {}") is None


def test_cle_d_argument_non_identifiant_refusee():
    assert extraire_code('<tool_call>{"name": "read_file", "arguments": {"a=1, b": 2}}</tool_call>') is None


def test_valeur_malveillante_reste_une_chaine():
    texte = '<tool_call>{"name": "read_file", "arguments": {"filepath": "\\"); import os; (\\""}}</tool_call>'
    assert executer(extraire_code(texte)) == [((), {"filepath": '"); import os; ("'})]


def test_l_agent_execute_un_appel_xml():
    client = FauxClient("A", [({"content": XML}, None), ({"content": "Final Answer: fini"}, None)])
    sandbox = FausseSandbox()
    reponse, steps = Agent("question", max_tours=5, client=client, sandbox=sandbox).agent_algo()
    assert reponse == "fini"
    assert sandbox.codes == [extraire_code(XML)]
    assert steps[0].sandbox_input.startswith("result = read_file(")


# AS-38 : appel d'outil natif refusé par Groq (400 tool_use_failed)

NATIF = '{"name": "run_tests", "arguments": {"code": "def f():\\n    return 1", "test_list": ["assert f() == 1"]}}'


def test_json_sans_balises():
    assert executer_run_tests(extraire_code(NATIF)) == [((), {"code": "def f():\n    return 1",
                                                              "test_list": ["assert f() == 1"]})]


def test_json_sans_balises_liste_d_appels():
    assert len(executer_run_tests(extraire_code(f"[{NATIF}, {NATIF}]"))) == 2


def test_json_ordinaire_n_est_pas_un_appel():
    assert extraire_code('{"answer": 42}') is None
    assert extraire_code('Thought: {"name": "run_tests"} dans une phrase') is None


def executer_run_tests(code):
    appels = []
    exec(code, {"run_tests": lambda *a, **k: appels.append((a, k)), "print": lambda *a: None})
    return appels


def erreur_http(code, corps):
    return urllib.error.HTTPError("https://faux.test", code, "Bad Request", {}, io.BytesIO(corps.encode()))


def test_generation_refusee():
    corps = json.dumps({"error": {"code": "tool_use_failed", "failed_generation": NATIF}})
    assert generation_refusee(erreur_http(400, corps)) == NATIF
    assert generation_refusee(erreur_http(400, '{"error": {"code": "invalid_request_error"}}')) is None
    assert generation_refusee(erreur_http(400, "pas du json")) is None


def test_le_client_garde_le_texte_refuse(monkeypatch):
    corps = json.dumps({"error": {"code": "tool_use_failed", "failed_generation": NATIF}})

    def urlopen(*args, **kwargs):
        raise erreur_http(400, corps)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    client = ClientLLM("https://faux.test/v1/chat/completions", "m", "cle")
    message, code = client.appel_llm([{"role": "user", "content": "x" * 300}])
    assert (message["content"], code) == (NATIF, None)
    assert client.input_tokens == 100 and client.output_tokens == len(NATIF) // 3  # estimés
    assert client.erreurs == ["400"]  # reste visible dans les métriques
