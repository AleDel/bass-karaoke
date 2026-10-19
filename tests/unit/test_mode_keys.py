"""Teclados de los modos (mixins) — sin abrir ventana ni audio real."""
import pygame
import pytest

from bass_karaoke.modes import (
    CorridosModeMixin,
    EarModeMixin,
    ModeManagerMixin,
    SequencesModeMixin,
    TrainingModeMixin,
    WalkingLabMixin,
)


class _Tone:
    def play(self):
        pass


class _Host(
    TrainingModeMixin,
    WalkingLabMixin,
    CorridosModeMixin,
    EarModeMixin,
    SequencesModeMixin,
    ModeManagerMixin,
):
    def __init__(self):
        self._init_training_state()
        self._init_walking_lab_state()
        self._init_corridos_state()
        self._init_ear_state()
        self._init_sequences_state()

    def _midi_to_hz(self, midi):
        return 440.0 * 2 ** ((midi - 69) / 12)

    def _build_tone(self, hz):
        return _Tone()


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, unicode="", mod=0)


@pytest.fixture
def host():
    return _Host()


def test_training_keys(host):
    host._training_open()
    first = host.tr_target_name
    assert host._key_training(key(pygame.K_n)) is True
    assert host.tr_total == 1
    assert host.tr_target_name != first or host.tr_total == 1
    host._key_training(key(pygame.K_h))
    assert host.tr_hint is True
    host._key_training(key(pygame.K_2))
    assert host.tr_level == 2
    host._key_training(key(pygame.K_ESCAPE))
    assert host.training_open is False and host.tr_hint is False


def test_walking_lab_keys(host):
    host._lab_open()
    assert host.lab_steps
    host._key_lab(key(pygame.K_SPACE))
    assert host.lab_running is True
    idx = host.lab_idx
    host._key_lab(key(pygame.K_n))
    assert host.lab_idx == (idx + 1) % 12
    bpm = host.lab_bpm
    host._key_lab(key(pygame.K_UP))
    assert host.lab_bpm == bpm + 5
    host._key_lab(key(pygame.K_ESCAPE))
    assert host.lab_open is False and host.lab_running is False


def test_corridos_keys(host):
    host._cor_open()
    assert host.cor_steps
    host._key_cor(key(pygame.K_q))
    assert host.cor_fifth == "up"
    orn = host.cor_ornament
    host._key_cor(key(pygame.K_f))
    assert host.cor_ornament is not orn
    host._key_cor(key(pygame.K_SPACE))
    assert host.cor_running is True
    host._key_cor(key(pygame.K_k))
    assert host.cor_open is False and host.cor_running is False


def test_ear_keys(host):
    host._ear_open()
    host._key_ear(key(pygame.K_n))
    assert host.ear_revealed is True and host.ear_total == 1
    host._key_ear(key(pygame.K_2))
    assert host.ear_level == 2
    host._key_ear(key(pygame.K_o))
    assert host.ear_open is False


@pytest.mark.parametrize("prefix,key_open", [("tx", pygame.K_x),
                                             ("ar", pygame.K_a),
                                             ("sc", pygame.K_v)])
def test_sequence_keys(host, prefix, key_open):
    host._seq_open(prefix)
    assert getattr(host, f"{prefix}_steps")
    host._key_seq(prefix, key(pygame.K_1))
    assert getattr(host, f"{prefix}_sel") == 1
    pos = getattr(host, f"{prefix}_pos")
    host._key_seq(prefix, key(pygame.K_UP))
    assert getattr(host, f"{prefix}_pos") == min(12, pos + 1)
    host._key_seq(prefix, key(pygame.K_n))
    assert getattr(host, f"{prefix}_step") == 0
    host._key_seq(prefix, key(key_open))
    assert getattr(host, f"{prefix}_open") is False


def test_seq_ignores_invalid_variant(host):
    host._seq_open("tx")
    host._key_seq("tx", key(pygame.K_3))
    assert host.tx_sel in (1, 2)
