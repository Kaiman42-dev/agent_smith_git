"""Tests du REPL de la sandbox (sandbox/cli.py) : le code envoyé par un tube, comme pendant l'examen."""
import builtins

import pytest

import sandbox.cli as cli


class FausseSandbox:
    """Note le code reçu au lieu de l'exécuter."""

    def __init__(self):
        self.recu = []

    def execute(self, source, interactive=False):
        self.recu.append(source)


@pytest.fixture
def console(monkeypatch):
    monkeypatch.setattr(cli, "print_result", lambda resultat: None)
    return cli.SandboxConsole(FausseSandbox())


def envoyer(monkeypatch, console, lignes):
    """Simule `cat fichier | sandbox` : input() rend les lignes une par une, puis EOFError."""
    restantes = iter(lignes)

    def faux_input(prompt=""):
        try:
            return next(restantes)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(builtins, "input", faux_input)
    console.interact(banner="", exitmsg="")
    return console.sandbox.recu


def test_un_bloc_non_ferme_en_fin_d_entree_est_execute(monkeypatch, console):
    # comme les tests MCP de l'examen : le fichier finit dans un if, sans ligne vide après
    recu = envoyer(monkeypatch, console, ["x = 1", "if x:", "    print('fin')"])
    assert recu == ["x = 1", "if x:\n    print('fin')\n"]


def test_un_bloc_ferme_par_une_ligne_vide_n_est_execute_qu_une_fois(monkeypatch, console):
    recu = envoyer(monkeypatch, console, ["if True:", "    y = 2", ""])
    assert recu == ["if True:\n    y = 2\n"]  # la ligne vide qui ferme le bloc est gardée


def test_entree_vide(monkeypatch, console):
    assert envoyer(monkeypatch, console, []) == []
