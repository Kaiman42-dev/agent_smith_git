import argparse
import json
import os
import shlex
import sys
import time
import subprocess
import signal
import uuid
from pathlib import Path

from dotenv import load_dotenv # type: ignore

from agent_algo.agent import Agent, creer_client_cli, creer_clients_secours
from agent_algo.config import charger_config
from mcp_bridge import build_manual, build_tools
from mcp_client import SyncMcpClient
from models_public import SWEBenchTaskInput, SolutionOutput
from sandbox.parent import Sandbox

# limites de la moulinette pour SWE-bench (sujet, VI.1)
MAX_TOURS = 30
MAX_INPUT_TOKENS = 300_000
MAX_OUTPUT_TOKENS = 10_000
TIMEOUT = 900
# On s'arrête avant : un tour lancé juste avant l'heure limite peut encore appeler run_tests()
# (jusqu'à 300 s, l'outil n'est pas soumis au timeout de la sandbox), puis il faut
# supprimer le conteneur et écrire solution.json
MARGE = 330

# Our SWE-bench MCP server
SWEBENCH_SERVER = Path(__file__).resolve().parent.parent / "mcp_tools_swebench.py"
SWEBENCH_SERVER_COMMAND = f"{shlex.quote(sys.executable)} {shlex.quote(str(SWEBENCH_SERVER))}"

PROMPT_SWEBENCH = """You are an expert software engineer resolving a bug in a codebase located at `/testbed`.
Your goal is to locate the bug, fix it minimally, verify the fix, and submit the patch.

CRITICAL RULES:
- NEVER modify the test files. Only edit the source code to fix the bug.
- Be concise in your reasoning to save tokens (you have a strict global limit).

METHODOLOGY:
1. Search the codebase to locate the faulty code.
2. Run `run_tests()` to reproduce the bug and observe the failing tests.
3. Make a minimal fix using `edit_file()`.
4. Run `run_tests()` again to ensure the tests pass.
5. Submit your solution by calling `final_answer(get_patch())`.

FORMAT EXPECTED:
Each turn, you must provide a "Thought:" explaining your reasoning, followed by ONE ```python block of code to execute.

--- EXAMPLE OF A GOOD REASONING LOOP ---

Thought: I need to find where the email validation logic is defined to fix the "@" symbol bug.
```python
result = search_code("def validate_email", "*.py")
print(result)"""

CONTAINER_NAME = f"swebench_agent_{uuid.uuid4().hex[:8]}"

def cleanup_container(signum=None, frame=None):
    """Toujours supprimer le conteneur, même en cas de timeout de la moulinette."""
    print(f"\n[*] Nettoyage : Suppression du conteneur {CONTAINER_NAME}...")
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)
    if signum is not None:
        print(f"[*] Agent stoppé brutalement (Signal {signum}). Timeout de 900s atteint[cite: 27, 28].")
        sys.exit(1)

def main():
    fin = time.monotonic() + TIMEOUT - MARGE  # tout au début : le chrono de la moulinette tourne déjà
    # Gestion du SIGTERM envoyé par la moulinette[cite: 28]
    signal.signal(signal.SIGTERM, cleanup_container)
    signal.signal(signal.SIGINT, cleanup_container)

    parser = argparse.ArgumentParser()
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-name", default=None, help="par défaut : default_model de models.json")
    parser.add_argument("--provider-url", default=None, help="par défaut : url de default_provider de models.json")
    parser.add_argument("--api-key-env", default=None,
                        help="variable d'environnement de la clé (par défaut : déduite de --provider-url)")
    parser.add_argument("--no-fallback", action="store_true",
                        help="ne jamais changer de fournisseur (benchmark : un seul modèle par run)")
    args = parser.parse_args()

    debut = time.time()
    load_dotenv()

    with open(args.task_file) as f:
        tache = SWEBenchTaskInput.model_validate(json.load(f))

    try:
        config = charger_config()
        provider_url = args.provider_url or config.fournisseur(config.default_provider).url
        client = creer_client_cli(provider_url, args.model_name or config.default_model, args.api_key_env, config)
    except ValueError as e:
        sys.exit(f"Erreur de configuration : {e}")
    secours = [] if args.no_fallback else creer_clients_secours(client, config)

    erreur = None
    reponse, steps, agent_succes = "", [], False
    system_prompt = PROMPT_SWEBENCH
    patch = ""

    # docker
    image_name = tache.docker_image
    check_img = subprocess.run(["docker", "images", "-q", image_name], capture_output=True, text=True)
    if not check_img.stdout.strip():
        print(f"[*] Image {image_name} absente. Téléchargement en cours...[cite: 20]")
        subprocess.run(["docker", "pull", image_name], check=True)

    print(f"[*] Lancement du conteneur {CONTAINER_NAME}...")
    subprocess.run(["docker", "run", "-d", "--name", CONTAINER_NAME, image_name, "tail", "-f", "/dev/null"], check=True)

    os.environ["CONTAINER_NAME"] = CONTAINER_NAME
    os.environ["TESTBED_PATH"] = "/testbed" 

    try:
        with SyncMcpClient(SWEBENCH_SERVER_COMMAND) as mcp_client:
            with Sandbox(tools=build_tools(mcp_client)) as sandbox:
                
                question = f"Issue to solve:\n{tache.problem_statement}\n\n"
                if tache.hints_text:
                    question += f"Hints:\n{tache.hints_text}\n"

                agent = Agent(question=question, max_tours=MAX_TOURS, client=client,
                              sandbox=sandbox, prompt_systeme=PROMPT_SWEBENCH,
                              tools_manual=build_manual(mcp_client.list_tools()), secours=secours,
                              max_input_tokens=MAX_INPUT_TOKENS, max_output_tokens=MAX_OUTPUT_TOKENS,
                              fin=fin)
                
                system_prompt = agent.prompt_systeme
                reponse, steps = agent.agent_algo()
                agent_succes = agent.succes
                

        if agent_succes and reponse and "diff --git" in reponse:
            patch = reponse
        else:
            diff_cmd = ["docker", "exec", "-w", "/testbed", CONTAINER_NAME, "git", "-c", "core.fileMode=false", "diff"]
            diff_res = subprocess.run(diff_cmd, capture_output=True, text=True)
            patch = diff_res.stdout
            if patch.strip():
                agent_succes = True

    except Exception as e:
        erreur = f"crash de l'agent : {e}"
        
    finally:
        cleanup_container()

    succes = agent_succes and bool(patch)
    if not succes and erreur is None:
        erreur = "L'agent n'a pas réussi à résoudre l'issue ou le patch est vide."

    sortie = SolutionOutput(
        task_id=tache.instance_id,
        benchmark="swebench",
        success=succes,
        solution=patch,
        iterations=len(steps),
        total_requests=client.total_requetes + sum(c.total_requetes for c in secours),
        total_input_tokens=sum(s.input_tokens for s in steps),
        total_output_tokens=sum(s.output_tokens for s in steps),
        total_time_seconds=time.time() - debut,
        steps=steps,
        system_prompt=system_prompt,
        error=erreur,
    )
    
    with open(args.output, "w") as f:
        f.write(sortie.model_dump_json(indent=2))
        
    print(f"[*] Solution écrite dans {args.output} (succès={succes}, tours={len(steps)})")

if __name__ == "__main__":
    main()