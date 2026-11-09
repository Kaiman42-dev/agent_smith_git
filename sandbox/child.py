"""Code qui tourne À L'INTÉRIEUR du processus sandbox (l'enfant).

Le parent (parent.py) démarre ce processus une fois par tâche. Ici, on commence
par poser les barrières de sécurité, puis on boucle : recevoir du code, l'exécuter
dans un namespace persistant, renvoyer le résultat.

Le namespace donné au LLM contient deux sortes de fonctions (sujet, "Architectural
boundary") :
- les proxys d'outils MCP : ils transmettent l'appel au parent, qui exécute le
  vrai outil hors de la sandbox ;
- final_answer : fournie par la sandbox elle-même, toujours présente.

/!\\ Sécurité : tout ce qui est dans ce fichier est accessible, de près ou de loin,
au code du LLM. C'est pour ça qu'on lui donne des COPIES restreintes des builtins
et des modules, et non les vrais objets.
"""

import ast
import builtins
import contextlib
import io
import linecache
import os
import signal
import sys
import traceback
import types

from .config import SandboxConfig
from .protocol import (ExecutionResult, ExitSignal, RunCode, ToolCall,
                       receive_message, send_message)

# Builtins retirés : eval/exec/compile exécutent du code arbitraire, breakpoint/input
# ouvrent une console, et vars(obj) renvoie obj.__dict__ sans passer par is_attr_allowed
REMOVED_BUILTINS = ("eval", "exec", "compile", "breakpoint", "input", "vars")
MAX_CAPTURED_OUTPUT = 50_000  # nombre de caractères gardés de la sortie print()

# Attributs commençant par "_" que le LLM a quand même le droit d'utiliser.
# Tous les autres "_xxx" sont bloqués : c'est par eux qu'on remonte jusqu'à os
# (final_answer.__globals__, random._os, ().__class__.__subclasses__()...).
ALLOWED_UNDERSCORE_ATTRS = frozenset({
    "__init__", "__name__", "__doc__",            # super().__init__(), f.__name__
    "__len__", "__iter__", "__next__", "__contains__",
    "__getitem__", "__setitem__", "__str__", "__repr__",
    "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__", "__hash__",
    "__add__", "__sub__", "__mul__",
})

# Attributs de frames et de générateurs : ils ne commencent pas par "_",
# mais mènent aux variables globales du code qui appelle (donc à child.py).
FRAME_ATTRS = frozenset({
    "gi_frame", "gi_code", "cr_frame", "cr_code", "ag_frame", "ag_code",
    "f_back", "f_globals", "f_locals", "f_builtins", "f_code",
    "tb_frame", "tb_next",
})

# Fonctions de modules autorisés retirées des copies données au LLM : elles lisent
# un attribut à partir d'une chaîne (comme getattr) ou évaluent du texte.
REMOVED_MODULE_ATTRS = {
    "operator": {"attrgetter", "methodcaller"},
    "string": {"Formatter"},
    "typing": {"get_type_hints"},
}


def is_attr_allowed(name: str) -> bool:
    """La règle unique, utilisée par l'analyse du code ET par getattr."""
    if name in FRAME_ATTRS:
        return False
    if name.startswith("_"):
        return name in ALLOWED_UNDERSCORE_ATTRS  # "_xxx" : seulement la liste blanche
    return True  # attribut normal (append, keys, sqrt...)


def check_attr_name(name):
    """Applique is_attr_allowed à un nom d'attribut reçu sous forme de chaîne."""
    # type(...) is str, et pas isinstance : une sous-classe de str écrite par le LLM
    # pourrait redéfinir startswith() pour tromper is_attr_allowed.
    if type(name) is not str:
        raise TypeError("attribute name must be a plain string")
    if not is_attr_allowed(name):
        raise PermissionError(f"access to attribute '{name}' is blocked by the sandbox")


def safe_getattr(obj, name, *default):
    check_attr_name(name)
    return getattr(obj, name, *default)


def safe_setattr(obj, name, value):
    check_attr_name(name)
    setattr(obj, name, value)


def safe_delattr(obj, name):
    check_attr_name(name)
    delattr(obj, name)


def make_safe_module(module, restrictions, copies=None) -> types.ModuleType:
    """Copie filtrée d'un module autorisé : c'est elle que le LLM reçoit, pas le vrai.

    On ne garde que les noms publics, et les sous-modules eux-mêmes autorisés
    (copiés à leur tour). Les vrais modules restent intacts : la sandbox et les
    autres modules continuent de s'en servir normalement.
    """
    if copies is None:
        copies = {}
    if module.__name__ in copies:   # deux modules peuvent se citer l'un l'autre : on évite de boucler
        return copies[module.__name__]
    safe = types.ModuleType(module.__name__, module.__doc__)
    copies[module.__name__] = safe
    removed = REMOVED_MODULE_ATTRS.get(module.__name__, set())
    for name, value in vars(module).items():
        if name.startswith("_") or name in removed:
            continue  # noms internes (random._os...) et fonctions retirées
        if isinstance(value, types.ModuleType):
            if not restrictions.is_import_allowed(value.__name__):
                continue  # module non autorisé rangé dans un module autorisé (typing.sys...)
            value = make_safe_module(value, restrictions, copies)
        setattr(safe, name, value)
    return safe


class FinalAnswerSignal(BaseException):
    """Levée par final_answer() pour arrêter le bloc de code immédiatement.

    Elle hérite de BaseException et non d'Exception : ainsi, un `except Exception`
    écrit par le LLM ne l'attrape pas par erreur et la réponse finale remonte bien.
    """

    def __init__(self, answer: str):
        super().__init__(answer)
        self.answer = answer


def final_answer(*args, **kwargs):
    """Rend la réponse finale et termine la tâche.

    Prend exactement un argument, positionnel ou nommé : les LLM écrivent aussi
    bien final_answer(code) que final_answer(code=code).
    """
    values = list(args) + list(kwargs.values())
    if len(values) != 1:
        raise TypeError(f"final_answer() takes exactly one argument ({len(values)} given)")
    raise FinalAnswerSignal(str(values[0]))


def make_tool_proxy(conn, tool_name: str, description: str | None):
    """Crée une fonction qui ressemble à l'outil MCP, mais ne fait que relayer l'appel.

    Le vrai outil tourne dans le parent, hors de la sandbox : il n'est donc soumis
    ni aux restrictions, ni au timeout.
    """
    def tool_proxy(*args,**kwargs):
        # On envoie un ToolCall au parent et on attend sa réponse (ToolReply)
        send_message(conn, ToolCall(name=tool_name, arguments=kwargs, args=list(args)))
        reply = receive_message(conn)
        if reply.error is not None:
            raise RuntimeError(reply.error)
        return reply.value

    # __qualname__ est le nom affiché dans les messages d'erreur (ex : TypeError)
    tool_proxy.__name__ = tool_proxy.__qualname__ = tool_name
    tool_proxy.__doc__ = description
    return tool_proxy

class Restrictions:
    """Les règles de la sandbox (imports, fichiers), construites depuis la config."""

    def __init__(self, config: SandboxConfig):
        self.allowed_imports = set(config.authorized_imports)
        # realpath résout "..", les liens symboliques, et /tmp -> /private/tmp sur macOS
        self.allowed_dirs = [os.path.realpath(d) for d in config.allowed_directories]

    def is_import_allowed(self, name: str) -> bool:
        if name in self.allowed_imports:
            return True
        # "collections.abc" est autorisé si "collections.*" est dans la liste
        parts = name.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[:i])
            if parent + ".*" in self.allowed_imports:
                return True
        return False

    def is_path_allowed(self, path: str) -> bool:
        for allowed_dir in self.allowed_dirs:
            # Le test sur os.sep rejette "/tmp/agentevil" quand seul "/tmp/agent" est permis
            if path == allowed_dir or path.startswith(allowed_dir + os.sep):
                return True
        return False

    def safe_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        # Remplace __import__ : c'est par là que passe tout `import ...` du LLM
        if level != 0:
            raise ImportError("Relative imports are blocked by the sandbox")
        if not self.is_import_allowed(name):
            raise ImportError(f"Import blocked by the sandbox: {name}")
        module = builtins.__import__(name, globals, locals, fromlist, level)
        return make_safe_module(module, self)

    def safe_open(self, file, *args, **kwargs):
        # Remplace open() : on n'autorise que les dossiers de la liste blanche
        if not isinstance(file, (str, bytes, os.PathLike)):
            # Un descripteur de fichier (un entier) contournerait la vérif du chemin
            raise PermissionError("File descriptors are blocked by the sandbox")
        path = os.path.realpath(os.fsdecode(file))
        if not self.is_path_allowed(path):
            raise PermissionError(f"File access blocked by the sandbox: {file}")
        return builtins.open(path, *args, **kwargs)

    def build_builtins(self) -> dict:
        """Une COPIE des builtins pour le namespace du LLM.

        On ne modifie PAS le vrai module `builtins` : cette boucle et les modules
        autorisés (json, datetime...) doivent continuer à fonctionner normalement.
        On part d'une copie, on en retire les dangereux, et on remplace import/open.
        """
        restricted = dict(vars(builtins))
        for name in REMOVED_BUILTINS:
            restricted.pop(name, None)
        restricted["__import__"] = self.safe_import
        restricted["open"] = self.safe_open
        restricted["getattr"] = safe_getattr
        restricted["setattr"] = safe_setattr
        restricted["delattr"] = safe_delattr
        return restricted


def apply_process_limits(config: SandboxConfig):
    """Limites qui s'appliquent à tout le processus : Ctrl+C, mémoire, réseau."""
    # Ctrl+C est géré par le parent, qui tue ensuite ce processus : on l'ignore ici.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    try:
        import resource
        max_bytes = config.max_memory_mb * 1024 * 1024
        # RLIMIT_AS limite la mémoire virtuelle que le processus peut réserver
        resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
    except (ImportError, ValueError, OSError) as e:
        # Marche sur Linux (la cible). macOS refuse RLIMIT_AS (ValueError) : on le
        # signale au lieu de l'ignorer, sinon on croit à tort que la limite est active.
        print(f"[sandbox] warning: memory limit not applied ({e})", file=sys.stderr)

    import socket

    # On neutralise la création de sockets : plus aucune connexion réseau possible
    def blocked_socket(*args, **kwargs):
        raise PermissionError("Network access is blocked by the sandbox")

    socket.socket = blocked_socket
    socket.create_connection = blocked_socket


class CappedOutput(io.StringIO):
    """Un StringIO qui arrête de stocker le texte après MAX_CAPTURED_OUTPUT.

    Sans ça, une boucle `print` infinie remplirait la mémoire avant même que le
    timeout n'arrête le code.
    """

    def __init__(self):
        super().__init__()
        self.truncated = False

    def write(self, text):
        room_left = MAX_CAPTURED_OUTPUT - self.tell()
        if len(text) > room_left:
            self.truncated = True
        if room_left > 0:
            super().write(text[:room_left])
        return len(text)


def format_error(error: Exception) -> str:
    # La 1re frame de la traceback est run_code lui-même : on la saute pour que
    # le LLM ne voie que les lignes de SON code.
    llm_frames = error.__traceback__.tb_next
    return "".join(traceback.format_exception(type(error), error, llm_frames))


def check_code(tree: ast.AST) -> str | None:
    """Cherche un attribut interdit dans le code, AVANT de l'exécuter.

    Renvoie le message d'erreur pour le LLM, ou None si le code est accepté.
    Ne voit que les noms écrits en clair (obj.__globals__) : un nom caché dans
    une chaîne (getattr(obj, "__glo" + "bals__")) est géré par safe_getattr.
    """
    for node in ast.walk(tree):  # visite tous les nœuds de l'arbre, à toute profondeur
        if isinstance(node, ast.Attribute):
            names = [node.attr]          # obj.xxx, en lecture comme en écriture
        elif isinstance(node, ast.MatchClass):
            names = node.kwd_attrs       # case Foo(xxx=...) lit aussi l'attribut obj.xxx
        else:
            continue
        for name in names:
            if not is_attr_allowed(name):
                return f"line {node.lineno}: access to attribute '{name}' is blocked by the sandbox"
    return None


def run_code(code: str, namespace: dict, step: int, interactive: bool = False) -> ExecutionResult:
    # Un "nom de fichier" unique enregistré dans linecache permet à la traceback
    # d'afficher les lignes de code du LLM (sinon elles n'existent nulle part sur disque).
    filename = f"<sandbox-step-{step}>"
    linecache.cache[filename] = (len(code), None, code.splitlines(True), filename)

    captured = CappedOutput()
    error = ""
    answer = None
    # On redirige stdout et stderr vers notre buffer : tout ce que le code affiche
    # est capturé au lieu d'aller sur la vraie sortie du processus.
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        try:
            # compile() plutôt qu'ast.parse() : évite une frame en plus dans la traceback
            tree = compile(code, filename, "exec", ast.PyCF_ONLY_AST)
            problem = check_code(tree)
            if problem is not None:
                raise PermissionError(problem)  # rien n'a été exécuté
            last_expression = None
            if interactive and tree.body and isinstance(tree.body[-1], ast.Expr):
                # Mode REPL : on détache la dernière expression pour afficher sa valeur,
                # comme le fait l'interpréteur Python (taper `2 + 2` affiche `4`).
                last_expression = ast.Expression(tree.body.pop().value)
            exec(compile(tree, filename, "exec"), namespace)
            if last_expression is not None:
                value = eval(compile(last_expression, filename, "eval"), namespace)
                if value is not None:
                    print(repr(value))
        except FinalAnswerSignal as final:
            answer = final.answer  # le code a appelé final_answer() : on garde la réponse
        except Exception as e:
            error = format_error(e)  # le code a planté : on garde la traceback

    output = captured.getvalue()
    if captured.truncated:
        output += "\n[output truncated]"
    return ExecutionResult(success=not error, output=output, error=error,
                           final_answer=answer)


def build_namespace(conn, config: SandboxConfig, tool_docs: dict) -> dict:
    """Le namespace du LLM : builtins restreints, proxys d'outils, final_answer."""
    namespace = {
        "__builtins__": Restrictions(config).build_builtins(),
        "__name__": "__sandbox__",
    }
    for tool_name, description in tool_docs.items():
        namespace[tool_name] = make_tool_proxy(conn, tool_name, description)
    namespace["final_answer"] = final_answer  # ajouté en dernier : un outil ne peut pas l'écraser
    return namespace


def child_main(conn, config: SandboxConfig, tool_docs: dict):
    """Point d'entrée du processus sandbox (lancé par le parent).

    tool_docs : {nom_outil: description} des outils MCP à exposer.
    """
    apply_process_limits(config)                         # 1. poser les barrières
    namespace = build_namespace(conn, config, tool_docs)  # 2. préparer l'espace du LLM

    step = 0
    while True:  # 3. boucle : un tour par bloc de code reçu
        try:
            message = receive_message(conn)
        except EOFError:
            return  # le parent a fermé le Pipe : on s'arrête
        if not isinstance(message, RunCode):
            continue  # le parent n'envoie des ToolReply qu'en réponse à un ToolCall

        step += 1
        try:
            result = run_code(message.code, namespace, step, message.interactive)
        except (SystemExit, KeyboardInterrupt) as e:
            # Ces exceptions ne passent pas en JSON : on les transforme en ExitSignal.
            # Les arguments de exit(code) doivent survivre au JSON : on garde int/str, repr sinon.
            args = [arg if isinstance(arg, (int, str)) else repr(arg) for arg in e.args]
            send_message(conn, ExitSignal(type(e).__name__, args))
            return
        send_message(conn, result)
