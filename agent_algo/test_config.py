"""Tests de models.json (sujet, chapitre VIII) : chargement, validation et création des clients LLM."""
import json

import pytest

from agent_algo.agent import ClientLLM, creer_client_cli, creer_clients_secours, url_chat
from agent_algo.config import ModelsConfig, charger_config

CLES = ("GROQ_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY")


def config(**modifs):
    """Une config valide à 3 fournisseurs, avec des champs remplacés si besoin."""
    data = {
        "default_provider": "b",
        "default_model": "modele-b",
        "providers": [
            {"name": "a", "url": "https://a.test/v1", "api_key_env": "CLE_A", "fallback_model": "modele-a"},
            {"name": "b", "url": "https://b.test/v1/", "api_key_env": "CLE_B", "fallback_model": "modele-b"},
            {"name": "c", "url": "https://c.test/v1", "api_key_env": "CLE_C", "fallback_model": "modele-c"},
        ],
    }
    data.update(modifs)
    return ModelsConfig.model_validate(data)


@pytest.fixture
def cles(monkeypatch):
    """Aucune vraie clé : on part d'un environnement vide, chaque test définit les siennes."""
    for nom in CLES + ("CLE_A", "CLE_B", "CLE_C"):
        monkeypatch.delenv(nom, raising=False)
    return monkeypatch


def test_le_models_json_du_depot_est_valide():
    conf = charger_config()
    assert [p.name for p in conf.providers] == ["groq", "openrouter", "gemini"]  # ordre de bascule
    assert conf.fournisseur(conf.default_provider).name == "gemini"
    assert all(p.api_key_env.endswith("_API_KEY") for p in conf.providers)  # des noms, pas des clés


def test_default_provider_inconnu_refuse():
    with pytest.raises(ValueError, match="default_provider"):
        config(default_provider="z")


def test_noms_en_double_refuses():
    with pytest.raises(ValueError, match="double"):
        config(providers=[config().providers[1].model_dump()] * 2)


def test_champ_manquant_refuse(tmp_path):
    fichier = tmp_path / "models.json"
    fichier.write_text(json.dumps({"default_provider": "a", "providers": []}))
    with pytest.raises(ValueError, match="default_model"):
        charger_config(fichier)


def test_fichier_absent_donne_une_valueerror(tmp_path):
    # les CLI n'attrapent que ValueError pour afficher "Erreur de configuration"
    with pytest.raises(ValueError, match="impossible de lire"):
        charger_config(tmp_path / "absent.json")


def test_url_chat():
    assert url_chat("https://b.test/v1/") == "https://b.test/v1/chat/completions"
    assert url_chat("https://b.test/v1/chat/completions") == "https://b.test/v1/chat/completions"


def test_cle_deduite_du_domaine(cles):
    cles.setenv("CLE_B", "secret-b")
    client = creer_client_cli("https://b.test/v1", "un-modele", None, config())
    assert (client.adress, client.modele, client.key) == ("https://b.test/v1/chat/completions", "un-modele", "secret-b")


def test_api_key_env_explicite_prioritaire(cles):
    cles.setenv("AUTRE", "secret-autre")
    client = creer_client_cli("https://inconnu.test/v1", "m", "AUTRE", config())
    assert client.key == "secret-autre"


def test_fournisseur_inconnu_sans_api_key_env(cles):
    with pytest.raises(ValueError, match="models.json"):
        creer_client_cli("https://inconnu.test/v1", "m", None, config())


def test_cle_manquante(cles):
    with pytest.raises(ValueError, match="CLE_B"):
        creer_client_cli("https://b.test/v1", "m", None, config())


def test_secours_dans_l_ordre_sans_le_principal_ni_les_cles_manquantes(cles):
    cles.setenv("CLE_A", "x")
    cles.setenv("CLE_C", "x")
    principal = ClientLLM("https://a.test/v1/chat/completions", "autre-modele-de-a", "x")
    secours = creer_clients_secours(principal, config())
    assert [(c.adress, c.modele) for c in secours] == [("https://c.test/v1/chat/completions", "modele-c")]
