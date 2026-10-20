"""Tests de acordes/letra del modo karaoke (chords.py) — sin audio."""
import json

from bass_karaoke import chords


def test_chord_name_uses_spanish_note_names():
    assert chords.chord_name(0, False) == "Do"
    assert chords.chord_name(1, True) == "Do#m"
    assert chords.chord_name(3, True) == "Mibm"
    assert chords.chord_name(6, False) == "Fa#"
    assert chords.chord_name(8, False) == "Lab"


def test_chord_at_picks_the_last_event_before_time():
    events = [(0.0, "C"), (5.0, "G")]
    assert chords.chord_at(events, -1.0) == "—"
    assert chords.chord_at(events, 0.0) == "C"
    assert chords.chord_at(events, 3.0) == "C"
    assert chords.chord_at(events, 5.0) == "G"
    assert chords.chord_at(events, 99.0) == "G"


def test_lyric_at_picks_the_current_line():
    events = [(0.0, "uno"), (2.0, "dos")]
    assert chords.lyric_at(events, 1.0) == "uno"
    assert chords.lyric_at(events, 2.5) == "dos"
    assert chords.lyric_at(events, -1.0) == ""


def test_map_lyrics_spreads_lines_across_segments_in_order():
    segments = [(0.0, 1.0), (4.0, 5.0)]
    out = chords.map_lyrics(segments, ["a", "b", "c"])
    assert out == [(0.0, "a"), (0.0, "b"), (4.0, "c")]


def test_map_lyrics_ignores_blank_lines():
    segments = [(0.0, 1.0)]
    assert chords.map_lyrics(segments, ["  ", "hola", ""]) == [(0.0, "hola")]


def test_map_lyrics_edge_cases():
    assert chords.map_lyrics([], []) == []
    assert chords.map_lyrics([], ["solo"]) == [(0.0, "solo")]


def test_save_and_load_song_map_roundtrip(tmp_path):
    path = str(tmp_path / "song.chords.json")
    chords.save_song_map(path, [(0.0, "Do"), (4.5, "Sol")],
                         [(0.0, "hola"), (4.5, "mundo")], barlen=3)
    loaded_chords, loaded_lyrics = chords.load_song_map(path)
    assert loaded_chords == [(0.0, "Do"), (4.5, "Sol")]
    assert loaded_lyrics == [(0.0, "hola"), (4.5, "mundo")]


def test_load_song_map_missing_or_corrupt_returns_empty(tmp_path):
    assert chords.load_song_map(str(tmp_path / "nope.json")) == ([], [])
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert chords.load_song_map(str(bad)) == ([], [])


def test_suggest_chords_filters_by_prefix_and_prioritises_song_chords():
    out = chords.suggest_chords("Fam", used=["Fam", "Dom"])
    assert out[0] == "Fam"
    assert all(n.startswith("Fam") for n in out[1:])
    assert len(out) <= 8


def test_suggest_chords_empty_query_lists_song_chords_first():
    out = chords.suggest_chords("", used=["Dom", "Sibm"])
    assert out[:2] == ["Dom", "Sibm"]
    assert out[2] == chords.chord_vocabulary()[0]


def test_suggest_chords_matches_anywhere_with_two_letters():
    assert "Fam7" in chords.suggest_chords("am7")
    assert chords.suggest_chords("zz") == []


def test_snap_events_to_grid_realigns_small_offsets():
    # Compases de 1.94 s; el acorde se guardó con el offset del MP3 (2.1).
    grid = [0.0, 1.935, 3.871, 5.806]
    assert chords.snap_events_to_grid([(2.1, "Fam")], grid) == [[1.935, "Fam"]]


def test_snap_events_to_grid_keeps_mid_measure_changes():
    grid = [0.0, 1.935, 3.871, 5.806]
    # Medio compás exacto (≈0.97 s) queda donde está.
    assert chords.snap_events_to_grid([(2.9, "Dom")], grid) == [[2.9, "Dom"]]


def test_snap_events_to_grid_without_grid_returns_original():
    evs = [(1.0, "Do"), (2.0, "Re")]
    assert chords.snap_events_to_grid(evs, []) == [[1.0, "Do"], [2.0, "Re"]]


def test_snap_events_to_grid_keeps_closest_when_two_collide():
    # Ambos caen cerca del compás 2: gana el más próximo (Sol).
    out = chords.snap_events_to_grid([(1.9, "Do"), (1.98, "Sol")], [0.0, 2.0])
    assert out == [[2.0, "Sol"]]


def test_load_song_barlen_accepts_valid_and_falls_back(tmp_path):
    path = tmp_path / "bar.json"

    path.write_text(json.dumps({"barlen": 3}), encoding="utf-8")
    assert chords.load_song_barlen(str(path)) == 3

    path.write_text(json.dumps({"barlen": 5}), encoding="utf-8")
    assert chords.load_song_barlen(str(path), default=4) == 4

    assert chords.load_song_barlen(str(tmp_path / "missing.json"), default=6) == 6


def _note(start16, dur, step, octave=1, alter=0, hz=None):
    n = {"start16": start16, "dur": dur, "step": step, "octave": octave,
         "alter": alter}
    if hz is not None:
        n["hz"] = hz
    return n


def test_note_pitch_class_uses_step_and_alter():
    assert chords.note_pitch_class(_note(0, 4, "F")) == 5
    assert chords.note_pitch_class(_note(0, 4, "B", alter=-1)) == 10   # Sib
    assert chords.note_pitch_class(_note(0, 4, "A", alter=-1)) == 8    # Lab


def test_note_pitch_class_falls_back_to_hz():
    assert chords.note_pitch_class({"hz": 87.31}) == 5      # F2
    assert chords.note_pitch_class({"hz": 0}) is None
    assert chords.note_pitch_class({}) is None


def test_chords_from_notes_derives_roots_and_minor_quality():
    # 3/4: compás 1 = Fa (con Lab, 3ª menor), compás 2 = Do, compás 3 = Fa.
    notes = [
        _note(0,  6, "F"), _note(0, 6, "A", alter=-1),
        _note(6,  6, "F"),
        _note(12, 6, "C", octave=2), _note(12, 6, "E", alter=-1),
        _note(18, 6, "C", octave=2),
        _note(24, 12, "F"),
    ]
    out = chords.chords_from_notes(notes, barlen=3)
    assert out == [(0, "Fam"), (12, "Dom"), (24, "Fam")]


def test_chords_from_notes_detects_major_when_the_third_is_major():
    notes = [_note(0, 8, "C"), _note(8, 8, "E")]
    assert chords.chords_from_notes(notes, barlen=3) == [(0, "Do")]


def test_chords_from_notes_merges_repeated_chords():
    notes = [_note(0, 12, "F"), _note(12, 12, "F"), _note(24, 12, "F")]
    assert chords.chords_from_notes(notes, barlen=3) == [(0, "Fam")]


def test_chords_from_notes_groups_several_bars():
    notes = [_note(0, 12, "F"), _note(12, 4, "C")]
    assert chords.chords_from_notes(notes, barlen=3, bars_per_chord=2) == [
        (0, "Fam")]


def test_chords_from_notes_without_notes_returns_empty():
    assert chords.chords_from_notes([]) == []
    assert chords.chords_from_notes([{"start16": 0, "dur": 4}]) == []
