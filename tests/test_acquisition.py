"""Tests du statut d'acquisition et de l'attente de déclenchement (sans matériel).

Fondation de la future capture conditionnelle : parsers purs (``SAST?``/``INR?``)
et sondage de ``wait_for_trigger`` avec horloge/attente injectées (pas de vraie
temporisation dans les tests).
"""

import pytest

from scope.acquisition import (
    parse_inr,
    parse_sample_status,
    read_inr,
    sample_status,
    triggered,
    wait_for_trigger,
)


# --- parsers purs ----------------------------------------------------------------
@pytest.mark.parametrize(
    "response, expected",
    [
        ("SAST Trig'd", "trig'd"),
        ("SAST Stop", "stop"),
        ("SAST Ready", "ready"),
        ("SAST Armed", "armed"),
    ],
)
def test_parse_sample_status(response, expected):
    assert parse_sample_status(response) == expected


def test_parse_inr():
    assert parse_inr("INR 8913") == 8913
    assert parse_inr("INR 0") == 0


@pytest.mark.parametrize(
    "value, expected",
    [
        (8913, True),   # bit 0 = 1 (impair)
        (8912, False),  # bit 0 = 0 (pair)
        (1, True),
        (0, False),
    ],
)
def test_triggered_bit0(value, expected):
    assert triggered(value) is expected


# --- I/O courtes (scope mocké) ----------------------------------------------------
class FakeScope:
    def __init__(self, responses):
        self._responses = list(responses)
        self.queries = []

    def query(self, command):
        self.queries.append(command)
        return self._responses.pop(0)


def test_sample_status_queries_sast():
    scope = FakeScope(["SAST Trig'd"])
    assert sample_status(scope) == "trig'd"
    assert scope.queries == ["SAST?"]


def test_read_inr_queries_inr():
    scope = FakeScope(["INR 8913"])
    assert read_inr(scope) == 8913
    assert scope.queries == ["INR?"]


# --- wait_for_trigger : sondage avec horloge/attente injectées -------------------
class FakeClock:
    """Horloge fictive : avance de ``step`` à chaque appel."""

    def __init__(self, step=0.05):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


def test_wait_for_trigger_detects_bit_set():
    scope = FakeScope(["INR 8912", "INR 8912", "INR 8913"])
    clock = FakeClock()
    sleeps = []

    ok = wait_for_trigger(scope, timeout_s=10.0, poll_s=0.05, clock=clock, sleep=sleeps.append)

    assert ok is True
    assert len(sleeps) >= 1


def test_wait_for_trigger_detects_bit_already_set_on_first_poll():
    """Régression : sur signal rapide/propre, le trigger peut déjà être latché dès
    le premier ``INR?`` après l'armement (mode SINGLE, pas de ré-armement auto).
    ``wait_for_trigger`` ne doit PAS faire de lecture de purge après l'armement —
    ça consommerait ce déclenchement réel et ferait timeout à tort (bug constaté
    sur matériel : SDS1204X-E, signal carré ~1kHz, déclenché en <1ms)."""
    scope = FakeScope(["INR 8913"])  # bit 0 déjà à 1 dès le tout premier appel
    clock = FakeClock()

    ok = wait_for_trigger(scope, timeout_s=10.0, poll_s=0.05, clock=clock, sleep=lambda _s: None)

    assert ok is True
    assert scope.queries == ["INR?"]  # une seule lecture, aucune purge gaspillée


def test_wait_for_trigger_times_out():
    # Ne se déclenche jamais : la boucle doit s'arrêter une fois le timeout dépassé.
    scope = FakeScope(["INR 8912"] * 1000)
    clock = FakeClock(step=1.0)  # avance vite pour dépasser le timeout tout de suite

    ok = wait_for_trigger(scope, timeout_s=2.0, poll_s=0.05, clock=clock, sleep=lambda _s: None)

    assert ok is False
