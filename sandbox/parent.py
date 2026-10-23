"""Sandbox persistante : exécute le code du LLM dans un processus enfant isolé.

Ce fichier, c'est le côté PARENT (le chef d'orchestre). Il démarre le processus
enfant (child.py), lui envoie le code par un Pipe et attend le résultat.

L'enfant reste vivant pendant toute la tâche : les variables sont donc conservées
d'un bloc de code à l'autre, sans avoir à rejouer tout l'historique à chaque fois.

Pendant que le code tourne, l'enfant peut demander au parent d'appeler un outil
MCP (voir protocol.py) : c'est le parent qui exécute le vrai outil, ICI, hors de
la sandbox. L'outil n'est donc pas soumis aux restrictions ni au timeout.

Utilisation :
    tools = build_tools(mcp_client)          # {nom: fonction}, voir mcp_bridge.py
    with Sandbox(config, tools) as sandbox:
        sandbox.execute("x = 2")
        sandbox.execute("print(x * 21)")     # ExecutionResult(success=True, output="42\n", ...)
"""

import multiprocessing
import time

from .child import child_main
from .config import SandboxConfig
from .protocol import (ExecutionResult, ExitSignal, ProtocolError, RunCode,
                       ToolCall, ToolReply, receive_message, send_message)

# "spawn" démarre un interpréteur Python tout neuf pour l'enfant. "fork" serait
# dangereux ici : le parent a des threads (SyncMcpClient), et fork + threads
# peut bloquer l'enfant au démarrage.
_CONTEXT = multiprocessing.get_context("spawn")

# Pour retrouver la classe d'exception à partir de son nom (voir ExitSignal)
_EXIT_EXCEPTIONS = {"SystemExit": SystemExit, "KeyboardInterrupt": KeyboardInterrupt}


class _ChildTimeout(Exception):
    """Interne : l'enfant n'a pas répondu dans le temps imparti."""


class Sandbox:
    """Pilote le processus enfant : démarrage, exécution, timeout, arrêt."""

    def __init__(self, config: SandboxConfig | None = None, tools: dict | None = None):
        """tools : {nom_outil: fonction}, exécutées dans le parent quand le code les appelle."""
        self.config = config or SandboxConfig()
        self.tools = tools or {}
        self._process = None   # le processus enfant (None tant qu'il n'est pas démarré)
        self._conn = None      # notre bout du Pipe pour lui parler

    # cycle de vie

    def start(self):
        # On n'envoie à l'enfant que les NOMS et les descriptions des outils :
        # les vraies fonctions restent ici, dans le parent (sécurité).
        tool_docs = {name: function.__doc__ for name, function in self.tools.items()}
        parent_conn, child_conn = _CONTEXT.Pipe()
        self._process = _CONTEXT.Process(
            target=child_main, args=(child_conn, self.config, tool_docs), daemon=True
        )
        self._process.start()
        child_conn.close()  # seul l'enfant garde son bout du Pipe
        self._conn = parent_conn

    def close(self):
        # Tue l'enfant sans ménagement : c'est voulu, car son code peut être
        # bloqué (boucle infinie) et ne pas répondre à une demande polie.
        if self._process is None:
            return
        self._process.kill()
        self._process.join()
        self._conn.close()
        self._process = None
        self._conn = None

    def restart(self):
        # Repart d'un enfant neuf : toutes les variables du LLM sont perdues.
        self.close()
        self.start()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    # exécution

    def execute(self, code: str, interactive: bool = False) -> ExecutionResult:
        """Exécute `code` dans le namespace persistant.

        interactive : affiche aussi la valeur de la dernière expression (mode REPL).
        """
        if self._process is None:
            self.start()
        try:
            return self._run(code, interactive)
        except (SystemExit, KeyboardInterrupt):
            # exit() dans le code, ou Ctrl+C alors que l'enfant est peut-être
            # encore occupé : on l'arrête. Le prochain execute() en relancera un neuf.
            self.close()
            raise

    def _run(self, code: str, interactive: bool) -> ExecutionResult:
        # On envoie le code, puis on écoute : l'enfant peut répondre plusieurs fois
        # (un ToolCall à chaque fois qu'il appelle un outil) avant le résultat final.
        send_message(self._conn, RunCode(code, interactive))

        # Seul le temps passé à exécuter le code du LLM compte, pas les appels d'outils :
        # on décompte time_left uniquement pendant l'attente de l'enfant.
        time_left = self.config.max_execution_time_seconds
        while True:
            try:
                message, time_left = self._wait_for_child(time_left)
            except _ChildTimeout:
                timeout = self.config.max_execution_time_seconds
                return self._state_lost(f"Timeout: the code ran for more than {timeout}s and was stopped.")
            except EOFError:
                # Le Pipe s'est fermé tout seul : l'enfant est mort (souvent la RAM dépassée).
                return self._state_lost("The sandbox process crashed (memory limit exceeded?).")
            except ProtocolError as e:
                return self._state_lost(str(e))

            if isinstance(message, ToolCall):
                # L'enfant demande un outil : on l'exécute ici et on lui renvoie la réponse.
                send_message(self._conn, self._call_tool(message))
            elif isinstance(message, ExitSignal):
                # Le code a fait exit()/Ctrl+C : on relève la vraie exception côté parent.
                raise _EXIT_EXCEPTIONS[message.exception_name](*message.args)
            elif isinstance(message, ExecutionResult):
                return message  # résultat final : c'est fini pour ce bloc
            else:
                return self._state_lost(f"Unexpected message from the sandbox: {type(message).__name__}")

    def _wait_for_child(self, time_left: float):
        """Attend le prochain message au plus `time_left` secondes.

        Renvoie (message, temps restant). Lève _ChildTimeout si rien n'arrive à temps.
        """
        started = time.monotonic()
        if not self._conn.poll(time_left):  # poll() attend qu'un message soit prêt
            raise _ChildTimeout()
        message = receive_message(self._conn)
        return message, time_left - (time.monotonic() - started)

    def _call_tool(self, call: ToolCall) -> ToolReply:
        # Exécute le vrai outil ICI, dans le parent, hors de la sandbox.
        tool = self.tools.get(call.name)
        if tool is None:
            return ToolReply(error=f"Unknown tool: {call.name}")
        if not isinstance(call.arguments, dict):
            return ToolReply(error="Tool arguments must be passed by keyword")
        try:
            value = tool(**call.arguments)
        except Exception as e:
            return ToolReply(error=f"{type(e).__name__}: {e}")
        # Les outils MCP renvoient du texte ; str() garde la réponse compatible JSON
        # pour n'importe quel autre type d'outil.
        return ToolReply(value=value if isinstance(value, str) else str(value))

    def _state_lost(self, reason: str) -> ExecutionResult:
        # Problème grave (timeout, crash...) : on repart d'un enfant neuf et on
        # prévient clairement que les variables sont perdues.
        self.restart()
        error = f"{reason} The sandbox was restarted: all variables were lost."
        return ExecutionResult(success=False, output="", error=error)
