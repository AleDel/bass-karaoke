"""Tests del parser MusicXML (parser.py) — sin pygame, con fixtures XML."""
import zipfile

import pytest

from bass_karaoke import parser, utils

_TAB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Bass</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>4</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <direction placement="above">
        <direction-type>
          <metronome>
            <beat-unit>quarter</beat-unit>
            <per-minute>120</per-minute>
          </metronome>
        </direction-type>
      </direction>
      <note>
        <pitch><step>G</step><octave>1</octave></pitch>
        <duration>4</duration>
        <type>quarter</type>
        <staff>2</staff>
        <notations>
          <technical><string>4</string><fret>3</fret></technical>
        </notations>
      </note>
    </measure>
  </part>
</score-partwise>
"""

_PITCH_ONLY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>4</divisions>
        <time><beats>3</beats><beat-type>4</beat-type></time>
      </attributes>
      <note>
        <pitch><step>A</step><octave>2</octave></pitch>
        <duration>4</duration>
        <type>quarter</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def test_parse_tab_like_musicxml(tmp_path):
    path = tmp_path / "tab.musicxml"
    path.write_text(_TAB_XML, encoding="utf-8")

    notes, sections, bpm, tempo_map, stats = parser.parse_musicxml(str(path))

    assert len(notes) == 1
    note = notes[0]
    assert (note["string"], note["fret"]) == (4, 3)
    assert note["start16"] == 0
    assert note["dur"] == 4
    assert note["hz"] == pytest.approx(utils.fret_to_hz(3, 4))
    assert note["note_name"] == "G1"

    assert bpm == pytest.approx(120.0)
    assert tempo_map == [(0, pytest.approx(120.0), "quarter")]
    assert stats["has_tab"] is True
    assert stats["beats_per_bar"] == 4
    assert sections == []


def test_parse_pitch_only_uses_the_fallback(tmp_path):
    path = tmp_path / "pitch.musicxml"
    path.write_text(_PITCH_ONLY_XML, encoding="utf-8")

    notes, _sections, bpm, tempo_map, stats = parser.parse_musicxml(str(path))

    assert stats["has_tab"] is False
    assert stats["total_pitch"] == 1
    assert stats["in_range"] == 1
    assert stats["transposed"] == 0
    assert stats["dropped"] == 0
    assert stats["beats_per_bar"] == 3

    note = notes[0]
    assert note["step"] == "A"
    assert note["transposed"] == 0
    assert bpm == pytest.approx(113.0)
    assert tempo_map == [(0, pytest.approx(113.0), "quarter")]


def test_fret_string_from_pitch_finds_the_lowest_fret():
    assert parser._fret_string_from_pitch("E", 1, 0) == (0, 4, 0)


def test_fret_string_from_pitch_transposes_high_notes_down():
    fret, string, down = parser._fret_string_from_pitch("C", 5, 0)
    assert down == 2
    assert (string, fret) == (1, 5)
    assert parser._fret_string_from_pitch("C", 5, 0, max_down_octaves=1) is None


def _write_tg(path, content):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("content.xml", content)


def test_parse_grace_notes_maps_to_main_note_index(tmp_path):
    path = tmp_path / "song.tg"
    _write_tg(path, """
<TGTrack>
  <TGMeasure>
    <TGBeat>
      <voice>
        <note value="3" string="4">
          <grace fret="2" transition="slide"/>
        </note>
      </voice>
    </TGBeat>
  </TGMeasure>
</TGTrack>
""")
    notes = [{"start16": 0}, {"start16": 4}]

    graces = parser.parse_grace_notes(str(path), notes)

    assert len(graces) == 1
    g = graces[0]
    assert g["fret"] == 2
    assert g["string"] == 4
    assert g["transition"] == "slide"
    assert g["main_note_idx"] == 0
    assert g["main_start16"] == 0


def test_parse_grace_notes_missing_file_returns_empty(tmp_path):
    assert parser.parse_grace_notes(str(tmp_path / "nope.tg"), []) == []
