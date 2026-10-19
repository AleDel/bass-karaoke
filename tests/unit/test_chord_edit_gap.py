"""Borrar un acorde en la barra deja hueco (no hereda el anterior)."""
from bass_karaoke.app import BassKaraoke

# Caso real (Ayer Hable Con Dios): 3/4 a 93 BPM, 12 dieciseisavos por compás.
SEC_PER_16 = 0.16125
MEASURES   = [(1, 0), (2, 12), (3, 24), (4, 36), (5, 48)]


class FakeView:
    viewport_x     = 0.0
    _score_total16 = 48


class FakeApp(BassKaraoke):
    """BassKaraoke sin __init__ (sin ventana ni audio)."""

    def __init__(self, events):
        self.chord_events             = [list(e) for e in events]
        self.lyric_events             = []
        self.measure_starts           = list(MEASURES)
        self.beats_per_bar            = 3
        self.view                     = FakeView()
        self.beat_time                = 0
        self.chord_bar_sel_measure    = None
        self.chord_bar_msg            = ""
        self.chord_bar_typing         = False
        self.chord_bar_buf            = ""
        self.chord_bar_target_sec     = None
        self.chord_bar_target_end_sec = None
        self.chord_bar_sugg_idx       = -1
        self.chord_bar_sugg_cache     = []
        self.chord_bar_replace        = False
        self.chord_edit_dirty         = False

    def _song_seconds(self, s16):
        return float(s16) * SEC_PER_16

    def grid_phase16(self):
        return 0.0

    def px_of(self, s16):
        return float(s16) * 30.0


def _names(app):
    return app._chord_bar_cells()


def test_delete_of_a_change_leaves_a_gap():
    app = FakeApp([(1.935, "Fam"), (5.805, "Dom")])
    app.chord_bar_sel_measure = 1            # compás 2: "Fam"
    app._chord_bar_delete()
    assert app.chord_events == [[1.935, ""], [5.805, "Dom"]]
    cells = _names(app)
    assert [c[7] for c in cells[:3]] == ["", "", ""]
    assert cells[3][7] == "Dom"              # el hueco dura hasta el siguiente
    assert cells[1][8] is True               # el compás 2 marca el hueco
    assert app.chord_edit_dirty is True
    assert "sin acorde" in app.chord_bar_msg


def test_delete_of_an_inherited_bar_creates_the_gap():
    app = FakeApp([(1.935, "Fam"), (5.805, "Dom")])
    app.chord_bar_sel_measure = 2            # compás 3 hereda "Fam"
    app._chord_bar_delete()
    assert app.chord_events == [[1.935, "Fam"], [3.87, ""], [5.805, "Dom"]]
    cells = _names(app)
    assert cells[1][7] == "Fam"
    assert cells[2][7] == ""                 # compás 3 en blanco
    assert cells[3][7] == "Dom"              # el cambio siguiente se respeta


def test_delete_again_on_a_gap_restores_inheritance():
    app = FakeApp([(1.935, "Fam"), (3.87, ""), (5.805, "Dom")])
    app.chord_bar_sel_measure = 2
    app._chord_bar_delete()
    assert app.chord_events == [[1.935, "Fam"], [5.805, "Dom"]]
    assert _names(app)[2][7] == "Fam"        # vuelve a heredar
    assert "hereda" in app.chord_bar_msg


def test_delete_on_an_inherited_gap_does_nothing():
    app = FakeApp([(1.935, "")])
    app.chord_bar_sel_measure = 3            # compás 4 sigue sin acorde
    app._chord_bar_delete()
    assert app.chord_events == [[1.935, ""]]
    assert "ya está sin acorde" in app.chord_bar_msg


def test_commit_with_empty_text_leaves_a_gap():
    app = FakeApp([(1.935, "Fam"), (5.805, "Dom")])
    app.chord_bar_sel_measure    = 2
    app.chord_bar_target_sec     = 3.87
    app.chord_bar_target_end_sec = 5.805
    app.chord_bar_buf            = ""
    app._chord_bar_commit()
    assert app.chord_events == [[1.935, "Fam"], [3.87, ""], [5.805, "Dom"]]


def test_modal_delete_leaves_a_gap():
    app = FakeApp([(1.935, "Fam"), (5.805, "Dom")])
    app._chord_edit_apply(24, "")            # Supr en el compás 3
    assert app.chord_events == [[1.935, "Fam"], [3.87, ""], [5.805, "Dom"]]
    assert app._chord_edit_name_at(3.87) == "—"
    assert app.chord_edit_dirty is True
