"""Rejilla de la tira de acordes (draw_karaoke): snap y celdas por compás."""
import pytest

from bass_karaoke.ui import draw_karaoke

# Caso real (Ayer Hable Con Dios): 3/4 a 93 BPM, 12 dieciseisavos por compás.
SEC_PER_16 = 0.16125                    # 1.935 s por compás de negra con puntillo
MEASURES   = [(1, 0), (2, 12), (3, 24), (4, 36), (5, 48)]
# El primer evento se guardó con el offset del MP3 (2.1 s = inicio del compás 2).
EVENTS     = [(2.1, "Fam"), (3.87, "Dom"), (7.74, "Sibm")]


class FakeView:
    viewport_x     = 0.0
    _score_total16 = 48


class FakeApp:
    """Solo lo que usan snapped_chord_events/chord_measure_cells."""

    measure_starts = MEASURES
    beats_per_bar  = 3
    view           = FakeView()

    def __init__(self, events):
        self.chord_events = list(events)

    def _song_seconds(self, s16):
        return float(s16) * SEC_PER_16

    def grid_phase16(self):
        return 0.0

    def px_of(self, s16):
        return float(s16) * 30.0


def test_snapped_events_align_the_mp3_offset_change():
    out = draw_karaoke.snapped_chord_events(FakeApp(EVENTS))
    assert out[0][0] == pytest.approx(1.935, abs=1e-6)   # 2.1 s → compás 2
    assert out[0][1] == "Fam"
    assert out[1][0] == pytest.approx(3.87, abs=1e-6)    # ya estaba en la rejilla
    assert out[2][1] == "Sibm"


def test_snapped_events_keep_mid_measure_changes():
    out = draw_karaoke.snapped_chord_events(FakeApp([(2.9, "Dom")]))
    assert out == [[2.9, "Dom"]]


def test_snapped_events_without_events_or_measures():
    assert draw_karaoke.snapped_chord_events(FakeApp([])) == []
    app = FakeApp(EVENTS)
    app.measure_starts = []
    assert draw_karaoke.snapped_chord_events(app) == [[2.1, "Fam"],
                                                      [3.87, "Dom"],
                                                      [7.74, "Sibm"]]


def test_cells_show_the_chord_where_the_bass_enters():
    cells = draw_karaoke.chord_measure_cells(FakeApp(EVENTS))
    assert [c[1] for c in cells] == [1, 2, 3, 4, 5]
    assert cells[0][7] == ""          # compás 1: todavía no hay acorde
    assert cells[1][7] == "Fam"       # el bajo entra en el compás 2
    assert cells[1][8] is True        # y ahí hay cambio de acorde
    assert cells[2][7] == "Dom"       # el acorde se mantiene hasta el siguiente
    assert cells[4][7] == "Sibm"


def test_cells_without_snapping_miss_the_bass_entry():
    """Regresión: sin alinear, el evento de 2.1 s no entraba en el compás 2."""
    raw = [(float(s), n) for s, n in EVENTS]
    cells = draw_karaoke.chord_measure_cells(FakeApp([]), raw)
    assert cells[1][7] == ""
    assert cells[1][8] is False


def test_cells_fall_back_to_bars_from_the_score_length():
    app = FakeApp([])
    app.measure_starts = []
    cells = draw_karaoke.chord_measure_cells(app)
    assert [c[1] for c in cells] == [1, 2, 3, 4]
    assert [c[2] for c in cells] == [0.0, 12.0, 24.0, 36.0]


def test_cells_keep_the_gap_after_a_cleared_chord():
    """Un evento vacío deja el compás sin acorde (no hereda el anterior)."""
    evs = [(1.935, "Fam"), (5.805, ""), (7.74, "Dom")]
    cells = draw_karaoke.chord_measure_cells(FakeApp(evs))
    assert cells[1][7] == "Fam"
    assert cells[2][7] == "Fam"
    assert cells[3][7] == ""        # hueco propio: compás 4 sin acorde
    assert cells[3][8] is True      # y está marcado como cambio
    assert cells[4][7] == "Dom"
