"""lance l'agent sur une tache MBPP : python -m agent_mbpp --task-file task.json --output solution.json"""
import argparse
import ast
import json
import os
import shlex
import sys
import time
from pathlib import Path

from dotenv import load_dotenv # type: ignore

from agent_algo.agent import Agent, ClientLLM
from mcp_bridge import build_manual, build_tools
from mcp_client import SyncMcpClient
from models_public import MBPPTaskInput, SolutionOutput
from sandbox.parent import Sandbox

MAX_TOURS = 10  # limite de la moulinette pour MBPP

# Our MBPP MCP server, started over stdio with the current Python interpreter
MBPP_SERVER = Path(__file__).resolve().parent.parent / "mcp_tools_mbpp.py"
MBPP_SERVER_COMMAND = f"{shlex.quote(sys.executable)} {shlex.quote(str(MBPP_SERVER))}"

# prompt en anglais et court : la limite MBPP est de 6000 tokens d'entree sur TOUS les tours
PROMPT_MBPP = """You solve Python tasks.
Each turn: "Thought:" in ONE sentence, then ONE ```python block like this:
    code = '''def f(x):
        ...'''
    result = run_tests(code=code, test_list=tests)
    print(result)
    if '"success": true' in result:
        final_answer(code)
`tests` is already defined: it holds the task's test assertions.
If the tests fail, read the Observation and fix the function.
Be concise, do not repeat code."""


def construire_question(tache: MBPPTaskInput) -> str:
    """transforme la tache MBPP en question pour le llm"""
    tests = "\n".join(tache.test_imports + tache.test_list)
    return (f"Task: {tache.task_definition}\n"
            f"Signature: {tache.function_definition}\n"
            f"Tests:\n{tests}")


def nettoyer_code(code: str) -> str:
    """garde seulement les imports, fonctions et classes (enleve les asserts et print de test)"""
    arbre = ast.parse(code)
    garde = [n for n in arbre.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef))]
    return "\n\n".join(ast.unparse(n) for n in garde)


def extraire_solution(steps, nom_fonction: str) -> str:
    """cherche le dernier code qui definit la fonction, en priorite celui qui a tourne sans erreur"""
    candidats = [s for s in steps if f"def {nom_fonction}" in s.sandbox_input]
    sans_erreur = [s for s in candidats if "Traceback" not in s.sandbox_output]
    for s in reversed(sans_erreur or candidats):
        try:
            return nettoyer_code(s.sandbox_input)
        except SyntaxError:
            continue
    return ""


def solution_from_answer(answer: str, steps, function_name: str) -> str:
    """final_answer(code) gives the solution directly; otherwise search the steps."""
    if f"def {function_name}" in answer:
        try:
            return nettoyer_code(answer)
        except SyntaxError:
            pass
    return extraire_solution(steps, function_name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-name", default="gemini-3.6-flash")
    parser.add_argument("--provider-url", default="https://generativelanguage.googleapis.com/v1beta/openai")
    args = parser.parse_args()

    debut = time.time() # pour mesurer le temps total de l'agent
    load_dotenv()

    with open(args.task_file) as f:
        tache = MBPPTaskInput.model_validate(json.load(f))

    url = args.provider_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    client = ClientLLM(adress=url, modele=args.model_name, key=os.getenv("GEMINI_API_KEY"))

    erreur = None
    reponse, steps, agent_succes = "", [], False
    system_prompt = PROMPT_MBPP
    try:
        # The MBPP MCP server provides run_tests. One sandbox process for the
        # whole task, so variables persist between steps
        with SyncMcpClient(MBPP_SERVER_COMMAND) as mcp_client: # demarre le serveur MBPP
            with Sandbox(tools=build_tools(mcp_client)) as sandbox: 
                # `tests` lets the LLM call run_tests without copying the asserts
                sandbox.execute(f"tests = {tache.test_imports + tache.test_list!r}")
                agent = Agent(question=construire_question(tache), max_tours=MAX_TOURS, client=client,
                              sandbox=sandbox, prompt_systeme=PROMPT_MBPP,
                              tools_manual=build_manual(mcp_client.list_tools()))
                system_prompt = agent.prompt_systeme  # includes the tools manual
                reponse, steps = agent.agent_algo()
                agent_succes = agent.succes
    except Exception as e:  # on ecrit quand meme solution.json pour ne pas perdre les metriques
        reponse = str(e)
        erreur = f"crash de l'agent : {e}"

    # nom de la fonction a partir de "def add(a, b):"
    nom_fonction = tache.function_definition.split("def ")[-1].split("(")[0].strip()
    solution = solution_from_answer(reponse, steps, nom_fonction)
    succes = agent_succes and bool(solution)
    if not succes and erreur is None:
        erreur = reponse

    sortie = SolutionOutput(
        task_id=str(tache.task_id),
        benchmark="mbpp",
        success=succes,
        solution=solution,
        iterations=len(steps),
        total_requests=client.total_requetes,
        total_input_tokens=sum(s.input_tokens for s in steps),
        total_output_tokens=sum(s.output_tokens for s in steps),
        total_time_seconds=time.time() - debut,
        steps=steps,
        system_prompt=system_prompt,
        error=erreur,
    )
    with open(args.output, "w") as f:
        f.write(sortie.model_dump_json(indent=2))
    print(f"solution ecrite dans {args.output} (succes={succes}, tours={len(steps)})")


if __name__ == "__main__":
    main()
