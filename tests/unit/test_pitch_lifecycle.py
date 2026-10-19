"""Ciclo de vida del hilo de PitchEngine, sin hardware de audio."""
import time

from bass_karaoke.audio.pitch_engine import PitchEngine


class _StubEngine(PitchEngine):
    """Sustituye el bucle real (micrófono) por uno que solo espera."""

    def __init__(self):
        super().__init__("mpm", 0, on_update=lambda *_: None)
        self.loops = 0

    def _loop(self):
        self.loops += 1
        while not self._stop_evt.is_set():
            time.sleep(0.01)


def test_start_is_idempotent():
    engine = _StubEngine()
    try:
        engine.start()
        engine.start()
        time.sleep(0.05)
        assert engine.is_running
        assert engine.loops == 1
    finally:
        engine.stop()


def test_stop_terminates_the_thread():
    engine = _StubEngine()
    engine.start()
    engine.stop()
    assert not engine.is_running


def test_stop_without_start_is_safe():
    engine = _StubEngine()
    engine.stop()
    assert not engine.is_running


def test_engine_can_be_restarted_after_stop():
    engine = _StubEngine()
    try:
        engine.start()
        engine.stop()
        engine.start()
        assert engine.is_running
    finally:
        engine.stop()
