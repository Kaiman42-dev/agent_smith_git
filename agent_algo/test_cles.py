"""Tests de plusieurs clés API par fournisseur, avec rotation (AS-33), sans réseau."""
import io
import json
import math
import urllib.error
import urllib.request

import pytest

from agent_algo.agent import ClientLLM, cles_api

OK = json.dumps({"choices": [{"message": {"content": "ok"}}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()


@pytest.fixture
def env(monkeypatch):
    for nom in ("CLE", "CLE_1", "CLE_2", "CLE_10", "CLE_X", "AUTRE_CLE"):
        monkeypatch.delenv(nom, raising=False)
    return monkeypatch


def test_cles_api_lit_toutes_les_variables_dans_l_ordre(env):
    env.setenv("CLE_2", "c")
    env.setenv("CLE", "a")
    env.setenv("CLE_10", "d")
    env.setenv("CLE_1", "b")
    env.setenv("CLE_X", "pas-une-cle")  # suffixe non numérique : ignoré
    env.setenv("AUTRE_CLE", "pas-une-cle")
    assert cles_api("CLE") == ["a", "b", "c", "d"]


def test_cles_api_virgules_et_doublons(env):
    env.setenv("CLE", "a, b,,a")
    env.setenv("CLE_1", "b")
    assert cles_api("CLE") == ["a", "b"]
    assert cles_api("ABSENTE") == []


class FauxServeur:
    """Remplace urlopen : répond selon la clé reçue dans l'en-tête Authorization."""

    def __init__(self, reponses):
        self.reponses = reponses  # clé -> liste de codes HTTP (200 = succès), consommés dans l'ordre
        self.cles_recues = []

    def __call__(self, requete, timeout=None):
        cle = requete.get_header("Authorization").removeprefix("Bearer ")
        self.cles_recues.append(cle)
        code = self.reponses[cle].pop(0)
        if code == 200:
            return io.BytesIO(OK)
        corps = b'{"error": {"details": [{"retryDelay": "30s"}]}}' if code == 429 else b"{}"
        raise urllib.error.HTTPError("https://faux.test", code, "erreur", {}, io.BytesIO(corps))


def client(monkeypatch, reponses):
    serveur = FauxServeur(reponses)
    monkeypatch.setattr(urllib.request, "urlopen", serveur)
    return ClientLLM("https://faux.test/v1/chat/completions", "m", list(reponses)), serveur


def test_429_passe_a_la_cle_suivante_sans_attendre(monkeypatch):
    llm, serveur = client(monkeypatch, {"k1": [429], "k2": [200]})
    message, code = llm.appel_llm([{"role": "user", "content": "x"}])
    assert message["content"] == "ok" and code is None
    assert serveur.cles_recues == ["k1", "k2"] and llm.key == "k2"
    assert llm.erreurs == ["429"]  # la rotation reste visible dans les métriques


def test_la_cle_epuisee_n_est_pas_reprise_au_prochain_appel(monkeypatch):
    llm, serveur = client(monkeypatch, {"k1": [429], "k2": [200, 200]})
    llm.appel_llm([{"role": "user", "content": "x"}])
    llm.appel_llm([{"role": "user", "content": "x"}])
    assert serveur.cles_recues == ["k1", "k2", "k2"]


def test_toutes_les_cles_epuisees_l_agent_sait_combien_attendre(monkeypatch):
    llm, serveur = client(monkeypatch, {"k1": [429], "k2": [429], "k3": [429]})
    message, code = llm.appel_llm([{"role": "user", "content": "x"}])
    assert (message, code) == (None, 429)
    assert serveur.cles_recues == ["k1", "k2", "k3"]  # chaque clé essayée une fois, pas de boucle
    assert 29 < llm.attente_quota <= 30  # la première clé se libère dans ~30 s (retryDelay)


def test_cle_refusee_ecartee_pour_toujours(monkeypatch):
    llm, serveur = client(monkeypatch, {"k1": [401], "k2": [200, 200]})
    assert llm.appel_llm([{"role": "user", "content": "x"}])[0]["content"] == "ok"
    assert llm.cle_disponible[0] == math.inf
    llm.appel_llm([{"role": "user", "content": "x"}])
    assert serveur.cles_recues == ["k1", "k2", "k2"]


def test_toutes_les_cles_refusees(monkeypatch):
    llm, serveur = client(monkeypatch, {"k1": [401], "k2": [403]})
    assert llm.appel_llm([{"role": "user", "content": "x"}]) == (None, 403)


def test_une_seule_cle_comme_avant(monkeypatch):
    llm, serveur = client(monkeypatch, {"k1": [429]})
    assert llm.appel_llm([{"role": "user", "content": "x"}]) == (None, 429)
    assert llm.attente_quota == 30 and serveur.cles_recues == ["k1"]
