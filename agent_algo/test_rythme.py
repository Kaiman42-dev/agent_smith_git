"""Tests de la pause calculée (rpm par clé) qui remplace la pause fixe de 12 s, sans réseau ni vraie attente."""
import io
import json
import math
import time
import urllib.request

import pytest

from agent_algo.agent import ClientLLM

OK = json.dumps({"choices": [{"message": {"content": "ok"}}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
MESSAGES = [{"role": "user", "content": "x"}]


class Horloge:
    """Remplace time.monotonic et time.sleep : le temps n'avance que quand on le dit."""

    def __init__(self):
        self.t = 1000.0
        self.pauses = []

    def monotonic(self):
        return self.t

    def sleep(self, secondes):
        self.pauses.append(round(secondes, 3))
        self.t += secondes


@pytest.fixture
def horloge(monkeypatch):
    h = Horloge()
    monkeypatch.setattr(time, "monotonic", h.monotonic)
    monkeypatch.setattr(time, "sleep", h.sleep)
    return h


@pytest.fixture
def cles_recues(monkeypatch):
    recues = []

    def urlopen(requete, timeout=None):
        recues.append(requete.get_header("Authorization").removeprefix("Bearer "))
        return io.BytesIO(OK)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return recues


def test_sans_rpm_aucune_pause(horloge, cles_recues):
    llm = ClientLLM("https://faux.test/v1/chat/completions", "m", "k1")
    for _ in range(3):
        llm.appel_llm(MESSAGES)
    assert horloge.pauses == []


def test_une_cle_attend_seulement_le_temps_qui_manque(horloge, cles_recues):
    llm = ClientLLM("https://faux.test/v1/chat/completions", "m", "k1", rpm=5)  # 12 s entre deux envois
    llm.appel_llm(MESSAGES)        # premier envoi : tout de suite
    horloge.t += 8                 # 8 s passées à exécuter le code de l'agent
    llm.appel_llm(MESSAGES)
    horloge.t += 20                # exécution plus longue que l'intervalle
    llm.appel_llm(MESSAGES)
    assert horloge.pauses == [4.0]  # 12 - 8 ; puis rien, 20 s > 12 s


def test_plusieurs_cles_se_relaient_sans_attendre(horloge, cles_recues):
    llm = ClientLLM("https://faux.test/v1/chat/completions", "m", ["k1", "k2", "k3"], rpm=5)
    for _ in range(3):
        llm.appel_llm(MESSAGES)
    assert horloge.pauses == []                    # 3 clés neuves : chacune envoie tout de suite
    assert sorted(cles_recues) == ["k1", "k2", "k3"]
    llm.appel_llm(MESSAGES)                        # 4e envoi : la clé la plus ancienne se libère en premier
    assert horloge.pauses == [12.0] and cles_recues[-1] == cles_recues[0]


def test_une_cle_refusee_est_ignoree(horloge, cles_recues):
    llm = ClientLLM("https://faux.test/v1/chat/completions", "m", ["k1", "k2"], rpm=5)
    llm.cle_disponible[0] = math.inf               # k1 refusée (401/403)
    llm.appel_llm(MESSAGES)
    llm.appel_llm(MESSAGES)
    assert cles_recues == ["k2", "k2"] and horloge.pauses == [12.0]


def test_la_pause_ne_depasse_pas_l_heure_limite(horloge, cles_recues):
    llm = ClientLLM("https://faux.test/v1/chat/completions", "m", "k1", rpm=5)
    llm.appel_llm(MESSAGES)
    llm.appel_llm(MESSAGES, fin=horloge.t + 3)     # il ne reste que 3 s pour toute la tâche
    assert horloge.pauses == [3.0]
