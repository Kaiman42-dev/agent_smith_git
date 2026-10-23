"""Ligne de commande de la sandbox : `uv run sandbox`.

    uv run sandbox                                     # config par défaut
    uv run sandbox sandbox_template.json               # config personnalisée
    uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json
    uv run sandbox --mcp-server http://127.0.0.1:8000/mcp

Ouvre un REPL : chaque entrée est exécutée dans la sandbox persistante (parent.py),
avec les mêmes restrictions que pour l'agent, les outils MCP et final_answer.
"""

import argparse
import code
import contextlib
import readline  # noqa: F401  (importé pour son effet : flèches et historique dans input())
import sys
from pathlib import Path

from pydantic import ValidationError

from .config import SandboxConfig
from .parent import Sandbox

EXIT_COMMANDS = ("exit", "quit")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="sandbox", description="Interactive Python sandbox with MCP tools.")
    parser.add_argument("config", nargs="?",
                        help="sandbox config JSON file (default config if omitted)")
    # Les deux options MCP s'excluent : on se connecte à UN serveur, pas deux
    server = parser.add_mutually_exclusive_group()
    server.add_argument("--mcp-stdio", metavar="COMMAND",
                        help='start an MCP server with this command, e.g. "python mcp_tools_mbpp.py"')
    server.add_argument("--mcp-server", metavar="URL",
                        help="connect to a streamable HTTP MCP server")
    return parser.parse_args(argv)


def load_config(path: str | None) -> SandboxConfig:
    # Pas de fichier donné -> config par défaut. Sinon on charge et on valide le JSON.
    if path is None:
        return SandboxConfig()
    try:
        return SandboxConfig.model_validate_json(Path(path).read_text())
    except OSError as e:
        sys.exit(f"sandbox: cannot read {path}: {e.strerror}")       # fichier illisible
    except ValidationError as e:
        sys.exit(f"sandbox: invalid config {path}:\n{e}")            # JSON invalide / mauvais champs


def print_result(result):
    """Affiche le résultat d'une entrée : sortie, erreur, réponse finale."""
    if result.output:
        # On garantit un retour à la ligne final sans en ajouter un en trop
        print(result.output, end="" if result.output.endswith("\n") else "\n")
    if result.error:
        print(result.error.rstrip("\n"), file=sys.stderr)
    if result.final_answer is not None:
        print(f"Final answer: {result.final_answer}")


class SandboxConsole(code.InteractiveConsole):
    """Le REPL Python (prompts, blocs, Ctrl+C, Ctrl+D), mais chaque entrée tourne dans la sandbox.

    On hérite de code.InteractiveConsole pour récupérer gratuitement toute la
    mécanique du REPL (prompts >>> / ..., blocs multi-lignes, historique) et on
    ne redéfinit que runsource, l'endroit où le code est réellement exécuté.
    """

    def __init__(self, sandbox: Sandbox):
        super().__init__()
        self.sandbox = sandbox

    def runsource(self, source, filename="<stdin>", symbol="single"):
        """Renvoie True tant que le bloc n'est pas fini (la console redemande une ligne)."""
        if source.strip() in EXIT_COMMANDS:
            raise SystemExit
        try:
            # compile renvoie None quand le bloc est incomplet (ex : un "def" sans corps)
            if self.compile(source, filename, symbol) is None:
                return True
        except (SyntaxError, ValueError, OverflowError):
            pass  # code invalide : on le laisse partir, la sandbox renverra l'erreur
        if source.strip():
            try:
                print_result(self.sandbox.execute(source, interactive=True))
            except KeyboardInterrupt:
                # Ctrl+C pendant l'exécution : la sandbox a déjà été arrêtée côté parent
                print("KeyboardInterrupt: the sandbox was restarted, all variables were lost.",
                      file=sys.stderr)
        return False


def main(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    target = args.mcp_stdio or args.mcp_server  # l'une des deux options, ou None

    # ExitStack ferme proprement le client MCP et la sandbox à la sortie, même sur erreur
    with contextlib.ExitStack() as stack:
        tools = {}
        if target:
            # Importé ici et pas en haut du fichier : `mcp` est lourd, et le
            # processus enfant de la sandbox réimporte ce module à chaque démarrage.
            from mcp_bridge import build_tools
            from mcp_client import SyncMcpClient
            try:
                tools = build_tools(stack.enter_context(SyncMcpClient(target)))
            except Exception as e:
                sys.exit(f"sandbox: {e}")  # ex : serveur injoignable (message clair via SyncMcpClient)
        sandbox = stack.enter_context(Sandbox(config, tools))
        banner = (f"Sandbox ready. MCP tools: {', '.join(tools) or 'none'}.\n"
                  "final_answer() is always available. Type exit or press Ctrl+D to quit.")
        # suppress(SystemExit) : "exit" tapé au prompt, ou exit() dans le code du LLM,
        # font sortir interact() ; on veut quitter proprement, sans traceback.
        with contextlib.suppress(SystemExit):
            SandboxConsole(sandbox).interact(banner=banner, exitmsg="")


if __name__ == "__main__":
    main()
