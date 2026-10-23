"""Messages échangés entre le parent (parent.py) et l'enfant (child.py).

Les deux processus communiquent par un Pipe. Ce fichier définit le "langage"
qu'ils parlent : chaque message est une petite dataclass (RunCode, ToolCall...).

Les messages voyagent en JSON, jamais en pickle. Dépickler des données peut
exécuter du code, et le code du LLM a accès au Pipe depuis l'enfant : un enfant
malveillant pourrait donc envoyer un pickle piégé. En JSON, le pire qu'il puisse
envoyer est un message mal formé, que le parent rejette (ProtocolError).

Déroulé d'un bloc de code (une "conversation") :
    parent -> enfant   RunCode        (voici le code à exécuter)
    enfant -> parent   ToolCall       (0 ou plusieurs fois : le code appelle un outil)
    parent -> enfant   ToolReply      (une réponse par ToolCall)
    enfant -> parent   ExecutionResult ou ExitSignal   (le résultat final)
"""

import json
from dataclasses import asdict, dataclass

MAX_MESSAGE_BYTES = 10 * 1024 * 1024  # un message plus gros est rejeté


class ProtocolError(Exception):
    """Un message reçu n'est pas du JSON valide, ou pas un message connu."""


@dataclass
class RunCode:
    """Parent -> enfant : exécute ce bloc de code."""
    code: str
    interactive: bool = False  # mode REPL : affiche aussi la valeur de la dernière expression


@dataclass
class ToolCall:
    """Enfant -> parent : appelle cet outil MCP (hors de la sandbox)."""
    name: str
    arguments: dict


@dataclass
class ToolReply:
    """Parent -> enfant : réponse à un ToolCall, soit une valeur, soit une erreur."""
    value: str | None = None
    error: str | None = None


@dataclass
class ExecutionResult:
    """Enfant -> parent : résultat d'un bloc de code."""
    success: bool
    output: str  # tout ce qui a été affiché (stdout + stderr)
    error: str   # la traceback si le code a levé une exception, "" sinon
    final_answer: str | None = None  # rempli quand le code a appelé final_answer()


@dataclass
class ExitSignal:
    """Enfant -> parent : le code a levé SystemExit ou KeyboardInterrupt.

    Le sujet impose que ces deux exceptions remontent jusqu'à la boucle de
    l'agent. L'enfant ne peut pas les envoyer telles quelles (elles ne passent
    pas en JSON), donc il envoie ce signal et le parent les relève de son côté.
    """
    exception_name: str  # "SystemExit" ou "KeyboardInterrupt"
    args: list


# Table {nom de la classe -> classe}, pour reconstruire un message à la réception
_MESSAGE_TYPES = {cls.__name__: cls
                  for cls in (RunCode, ToolCall, ToolReply, ExecutionResult, ExitSignal)}


def send_message(conn, message):
    # On ajoute "type" pour que l'autre côté sache quelle dataclass reconstruire
    payload = {"type": type(message).__name__, **asdict(message)}
    conn.send_bytes(json.dumps(payload).encode())


def receive_message(conn):
    """Lit un message. Lève EOFError si l'autre processus a fermé le Pipe."""
    try:
        payload = json.loads(conn.recv_bytes(MAX_MESSAGE_BYTES))
        message_class = _MESSAGE_TYPES[payload.pop("type")]
        return message_class(**payload)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        # OSError : message trop gros / ValueError : JSON invalide
        # KeyError, TypeError, AttributeError : ce n'est pas un message connu
        raise ProtocolError(f"Message invalide reçu de l'autre processus : {e}") from e
