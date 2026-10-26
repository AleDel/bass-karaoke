"""Tests del estilo de bajo ``yjz`` (frases de jjSwing de JJazzLab)."""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from bass_karaoke import sng
from bass_karaoke.audio import band

_ROOT = Path(__file__).resolve().parents[2]
_SNG_FILES = sorted((_ROOT / "JJazzLab-Jazz-1460").glob("*.sng"))


def test_part_variation_reads_rpvariationid():
    xml = """<SongPartImpl spName="A">
      <spHashMapRpIdValue>
        <entry><string>RP_SYS_DrumsTransformId</string><string>[x#]</string></entry>
        <entry><string>rpVariationID</string><string>Main B-1</string></entry>
      </spHashMapRpIdValue>
    </SongPartImpl>"""
    assert sng._part_variation(ET.fromstring(xml)) == "Main B-1"
    assert sng._part_variation(ET.fromstring("<SongPartImpl/>")) == ""


@pytest.mark.skipif(not _SNG_FILES, reason="sin ficheros .sng de JJazzLab")
def test_parse_sng_exposes_variations():
    song = sng.parse_sng(str(_SNG_FILES[0]))
    assert song["sections"]
    assert all(s.get("variation") for s in song["sections"])
    assert song["chords"]


@pytest.mark.skipif(not _SNG_FILES, reason="sin ficheros .sng de JJazzLab")
def test_yjz_style_generates_playable_line():
    song = sng.parse_sng(str(_SNG_FILES[0]))
    notes = sng.generate_line(song, "yjz")
    assert notes
    assert all(sng._TAB_MIN <= p <= sng._TAB_MAX for _, _, p in notes)
    assert all(d16 >= 1 for _, d16, _ in notes)
    assert notes == sorted(notes)


@pytest.mark.skipif(not _SNG_FILES, reason="sin ficheros .sng de JJazzLab")
def test_yjz_falls_back_to_jjazz_without_band_data(monkeypatch):
    song = sng.parse_sng(str(_SNG_FILES[0]))
    monkeypatch.setitem(band._CACHE, "data", None)
    assert sng.generate_line(song, "yjz") == sng.generate_line(song, "jjazz")


@pytest.mark.skipif(not _SNG_FILES, reason="sin ficheros .sng de JJazzLab")
def test_build_song_writes_loadable_musicxml(tmp_path):
    """El flujo de F7 (build_song) deja un MusicXML que el parser puede leer."""
    from bass_karaoke.parser import parse_musicxml

    res = sng.build_song(str(_SNG_FILES[0]), out_dir=str(tmp_path), force=True)

    notes, _sections, bpm, _tmap, stats = parse_musicxml(res["musicxml"])
    assert notes
    assert bpm > 0
    assert stats.get("beats_per_bar") in (3, 4)
    assert Path(res["chords_json"]).exists()
