"""Les 7 familles de tests d'exam_sandbox.sh (sujet, tableau VI.1), rejouées en local."""
import os
import sys

import pytest

from mcp_bridge import build_tools
from mcp_client import SyncMcpClient
from sandbox.config import SandboxConfig
from sandbox.parent import Sandbox

CONFIG = SandboxConfig(authorized_imports=["math"], allowed_directories=["/tmp/agent"],
                       max_execution_time_seconds=3, max_memory_mb=256)


@pytest.fixture(scope="module")
def sandbox():
    # une seule sandbox pour tous les tests : démarrer un processus prend du temps
    os.makedirs("/tmp/agent", exist_ok=True)
    with Sandbox(config=CONFIG) as sb:
        yield sb


def erreur(sandbox, code):
    """Exécute le code et renvoie le message d'erreur ("" si aucune erreur)."""
    return sandbox.execute(code).error


@pytest.mark.parametrize("code", ["import os", "import subprocess", "__import__('os')",
                                  "from os import path"])
def test_import_block(sandbox, code):
    assert "Import blocked" in erreur(sandbox, code)


@pytest.mark.parametrize("code", ["eval('1')", "exec('x = 1')", "compile('1', 'f', 'eval')",
                                  "vars()", "breakpoint()"])
def test_builtin_block(sandbox, code):
    assert "NameError" in erreur(sandbox, code)


@pytest.mark.parametrize("code", ["import socket", "import urllib.request", "import http.client"])
def test_network_block(sandbox, code):
    assert "Import blocked" in erreur(sandbox, code)


@pytest.mark.parametrize("chemin", ["/etc/passwd", "/tmp/agent/../../etc/passwd", "/tmp/agentX/f"])
def test_path_restrict(sandbox, chemin):
    assert "File access blocked" in erreur(sandbox, f"open({chemin!r})")


def test_path_autorise(sandbox):
    assert erreur(sandbox, "open('/tmp/agent/t.txt', 'w').write('ok')") == ""


def test_timeout_puis_redemarrage(sandbox):
    # la sandbox est limitée à 3 s : une boucle infinie doit être arrêtée...
    assert "Timeout" in erreur(sandbox, "while True: pass")
    # ...et la sandbox doit redémarrer et rester utilisable
    assert sandbox.execute("print(1 + 1)").output == "2\n"


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS ne marche que sous Linux")
def test_memory_limit(sandbox):
    # 1 Go demandé alors que la limite est de 256 Mo
    message = erreur(sandbox, "x = bytearray(1024 * 1024 * 1024)")
    assert "MemoryError" in message or "restarted" in message


def test_mcp_protocol():
    # même serveur MCP que l'agent MBPP : l'outil doit être appelable comme une fonction Python
    commande = f"{sys.executable} mcp_tools_mbpp.py"
    with SyncMcpClient(commande) as client, Sandbox(config=CONFIG, tools=build_tools(client)) as sb:
        result = sb.execute("print(run_tests(code='def f(): return 1', test_list=['assert f() == 1']))")
        assert '"success": true' in result.output
        assert sb.execute("final_answer('fini')").final_answer == "fini"
        # les LLM écrivent aussi les arguments sans leur nom, dans l'ordre du schéma
        result = sb.execute("print(run_tests('def f(): return 1', ['assert f() == 1']))")
        assert '"success": true' in result.output
        assert "positional" in sb.execute("run_tests('a', ['b'], 'c')").error
        assert "multiple values" in sb.execute("run_tests('a', code='a', test_list=[])").error
