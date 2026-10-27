"""Tests du confinement des outils SWE-bench au dépôt (AS-41), sans Docker ni réseau."""
import subprocess

import pytest

from outils import code_search_tools, execution_tools, file_systeme_tool, testbed


@pytest.fixture
def depot(tmp_path, monkeypatch):
    """Un faux dépôt dans TESTBED_PATH, et un secret à côté qu'aucun outil ne doit atteindre."""
    racine = tmp_path / "depot"
    (racine / "pkg").mkdir(parents=True)
    (racine / "pkg" / "mod.py").write_text("def cible():\n    return 1\n")
    (tmp_path / "secret.txt").write_text("SECRET\n")
    (racine / "lien.py").symlink_to(tmp_path / "secret.txt")  # lien qui sort du dépôt
    monkeypatch.setenv("TESTBED_PATH", str(racine))
    monkeypatch.delenv("CONTAINER_NAME", raising=False)
    return racine


def test_sans_testbed_path_tout_est_refuse(monkeypatch):
    monkeypatch.delenv("TESTBED_PATH", raising=False)
    with pytest.raises(PermissionError):
        testbed.racine()
    assert file_systeme_tool.read_file("/etc/hosts", 1, 5).startswith("Error")


def test_chemins_acceptes(depot):
    attendu = (depot / "pkg" / "mod.py").resolve()
    assert testbed.chemin_local("/testbed/pkg/mod.py") == attendu  # chemin du conteneur
    assert testbed.chemin_local("pkg/mod.py") == attendu
    assert testbed.chemin_local(str(depot / "pkg" / "mod.py")) == attendu
    assert testbed.chemin_local(None) == depot.resolve()


@pytest.mark.parametrize("chemin", ["/etc/passwd", "../secret.txt", "/testbed/../secret.txt",
                                    "pkg/../../secret.txt", "lien.py"])
def test_chemins_hors_du_depot_refuses(depot, chemin):
    with pytest.raises(PermissionError):
        testbed.chemin_local(chemin)


def test_read_file(depot, tmp_path):
    assert file_systeme_tool.read_file("/testbed/pkg/mod.py", 1, 1) == "1: def cible():"
    assert "outside the repository" in file_systeme_tool.read_file(str(tmp_path / "secret.txt"), 1, 1)
    assert "SECRET" not in file_systeme_tool.read_file("lien.py", 1, 1)


def test_edit_file_hors_du_depot_ne_touche_a_rien(depot, tmp_path):
    reponse = file_systeme_tool.edit_file(str(tmp_path / "secret.txt"), "SECRET", "PIRATE")
    assert reponse.startswith("Error") and (tmp_path / "secret.txt").read_text() == "SECRET\n"


def test_edit_file_dans_le_depot_garde_l_avertissement_de_syntaxe(depot):
    reponse = file_systeme_tool.edit_file("/testbed/pkg/mod.py", "return 1", "return (")
    assert reponse.startswith("File updated successfully.") and "Syntax error" in reponse
    assert "return (" in (depot / "pkg" / "mod.py").read_text()


def test_list_files_et_recherches_ignorent_le_lien_sortant(depot):
    assert "lien.py" not in file_systeme_tool.list_files("/testbed", "*.py")
    assert "SECRET" not in code_search_tools.search_code("SECRET", "*")
    assert "mod.py:1" in code_search_tools.search_function_or_class_definition_in_code("cible")
    assert "Error" not in code_search_tools.find_references("cible", "pkg/mod.py", 1)


def test_list_files_hors_du_depot_refuse(depot):
    assert "outside the repository" in file_systeme_tool.list_files("/", "*")


def test_chemins_affiches_selon_le_mode(depot, monkeypatch):
    assert code_search_tools.search_code("def cible", "*.py").startswith(str((depot / "pkg").resolve()))
    monkeypatch.setenv("CONTAINER_NAME", "c1")  # avec conteneur : le LLM voit /testbed
    assert code_search_tools.search_code("def cible", "*.py") == "/testbed/pkg/mod.py:1 def cible():"


def test_commandes_sans_conteneur_dans_le_depot(depot):
    assert str(depot.resolve()) in execution_tools.run_command("pwd")
    assert "outside the repository" in execution_tools.run_command("pwd", workdir="/")


def test_run_tests_lance_eval_sh_du_depot(depot):
    (depot / "eval.sh").write_text("echo tests-ok\n")
    assert "tests-ok" in execution_tools.run_tests()


def test_avec_conteneur_tout_passe_par_docker_exec(depot, monkeypatch):
    monkeypatch.setenv("CONTAINER_NAME", "c1")
    lances = []

    def faux_run(cmd, **options):
        lances.append((cmd, options))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", faux_run)
    execution_tools.run_command("ls", workdir="/testbed/pkg")
    execution_tools.get_patch()
    assert [c[:5] for c, _ in lances] == [["docker", "exec", "-w", "/testbed/pkg", "c1"],
                                         ["docker", "exec", "-w", "/testbed", "c1"]]
    assert all("cwd" not in options for _, options in lances)  # jamais exécuté sur l'hôte
