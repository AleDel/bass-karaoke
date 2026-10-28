"""Sincronía del primer play tras cargar una canción.

El renderizado del bajo (y el arranque del MP3) puede tardar cientos de ms.
`_play_mp3` debe reiniciar el reloj de frames al terminar para que ese tiempo
de preparación no se sume al siguiente `dt` y adelante el playhead.
"""
from bass_karaoke.app import BassKaraoke


class FakeClock:
    def __init__(self, events):
        self.events = events

    def tick(self, *_args):
        self.events.append("clock")


class FakeApp(BassKaraoke):
    """BassKaraoke sin __init__: solo el camino de `_play_mp3` sin audio real."""

    def __init__(self):
        self.events = []
        self.clock = FakeClock(self.events)
        self._use_vsp = False
        self._pgm_loaded = False
        self._vsp = None

    def _want_vsp(self):
        return False

    def _prepare_bass(self, offset_sec=0.0):
        self.events.append("bass")

    def _prepare_band(self, offset_sec=0.0):
        self.events.append("band")

    def _start_bass(self):
        self.events.append("start_bass")

    def _start_band(self):
        self.events.append("start_band")

    def _apply_mix(self):
        self.events.append("mix")


def test_play_mp3_reinicia_el_reloj_despues_de_arrancar_el_audio():
    app = FakeApp()

    app._play_mp3(0.0)

    assert app.events == [
        "bass", "band", "start_bass", "start_band", "mix", "clock",
    ]
