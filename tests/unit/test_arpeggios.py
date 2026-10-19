"""Tests de arpegios (arpeggios.py) — tríadas y cuatríadas puras."""
from bass_karaoke import arpeggios, music


def test_arpeggio_goes_up_and_back_in_seven_steps():
    steps = arpeggios.build_arpeggio(1, root_fret=3)
    assert len(steps) == 7
    assert [s["role"] for s in steps] == arpeggios.DEGREES


def test_arpeggio_starts_on_the_requested_root():
    for qid in arpeggios.QUALITIES:
        steps = arpeggios.build_arpeggio(qid, root_fret=3)
        assert steps[0]["string"] == arpeggios.ROOT_STRING
        assert steps[0]["fret"] == 3
        assert steps[0]["midi"] == music.midi_of(arpeggios.ROOT_STRING, 3)


def test_arpeggio_uses_the_quality_intervals():
    expected = {
        1: [0, 4, 7, 11],   # maj7
        2: [0, 3, 7, 10],   # min7
        3: [0, 4, 7, 10],   # dom7
    }
    for qid, iv in expected.items():
        steps = arpeggios.build_arpeggio(qid, root_fret=3)
        root = steps[0]["midi"]
        assert [s["midi"] - root for s in steps[:4]] == iv


def test_arpeggio_descending_half_mirrors_the_ascent():
    steps = arpeggios.build_arpeggio(1, root_fret=3)
    assert (steps[4]["string"], steps[4]["fret"]) == (steps[2]["string"], steps[2]["fret"])
    assert (steps[5]["string"], steps[5]["fret"]) == (steps[1]["string"], steps[1]["fret"])
    assert (steps[6]["string"], steps[6]["fret"]) == (steps[0]["string"], steps[0]["fret"])


def test_root_fret_is_clamped_to_the_safe_window():
    steps = arpeggios.build_arpeggio(1, root_fret=999)
    assert steps[0]["fret"] == 12


def test_step_matches_is_octave_invariant_here():
    step = arpeggios.build_arpeggio(1, root_fret=3)[0]
    assert arpeggios.step_matches(music.midi_to_hz(step["midi"]), step)
    assert arpeggios.step_matches(music.midi_to_hz(step["midi"] + 12), step)
    assert not arpeggios.step_matches(0.0, step)
