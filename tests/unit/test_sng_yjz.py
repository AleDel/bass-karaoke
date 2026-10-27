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

    res = sng.build_song(str(_SNG_FILES[0]), out_dir=str(tmp_path), force=True,
                         engine="internal")

    notes, _sections, bpm, _tmap, stats = parse_musicxml(res["musicxml"])
    assert notes
    assert bpm > 0
    assert stats.get("beats_per_bar") in (3, 4)
    assert Path(res["chords_json"]).exists()
    assert res["engine"] == "yjz"
    assert res["mid"] is None


# ── motor real de JJazzLab (puente Java) ───────────────────────────────────
def _write_bass_midi(path, ppq=480):
    """MIDI mínimo con una pista de bajo (canal 10) y dos notas."""
    import mido

    mid = mido.MidiFile(ticks_per_beat=ppq)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    track.append(mido.MetaMessage("track_name", name="Fake-Bass-channel11/16",
                                  time=0))
    track.append(mido.Message("program_change", channel=10, program=33, time=0))
    track.append(mido.Message("note_on", channel=10, note=40, velocity=90,
                              time=0))
    track.append(mido.Message("note_off", channel=10, note=40, velocity=0,
                              time=ppq))
    track.append(mido.Message("note_on", channel=10, note=45, velocity=80,
                              time=0))
    track.append(mido.Message("note_off", channel=10, note=45, velocity=0,
                              time=ppq))
    mid.save(path)
    return path


def test_midi_tracks_reads_bass_track(tmp_path):
    from bass_karaoke import jjazz

    path = _write_bass_midi(str(tmp_path / "bass.mid"))
    tracks = jjazz.midi_tracks(path)
    assert tracks[0]["name"].startswith("Fake-Bass")
    assert tracks[0]["channel"] == 10
    assert [n[2] for n in tracks[0]["notes"]] == [40, 45]
    assert jjazz.bass_track(path)["notes"] == tracks[0]["notes"]


def test_jjazz_marker_roundtrip(tmp_path):
    from bass_karaoke import jjazz

    track = {"name": "Fake-Bass", "channel": 10, "notes": [(0, 1, 40, 90)]}
    path = jjazz.write_marker(str(tmp_path), "tema", "tema.mid", track)
    data = jjazz.read_marker(path)
    assert data["bass_channel"] == 10
    assert data["bass_track"] == "Fake-Bass"
    assert data["bass_notes"] == 1
    assert data["midi"] == "tema.mid"


@pytest.mark.skipif(not _SNG_FILES, reason="sin ficheros .sng de JJazzLab")
def test_build_song_auto_uses_jjazz_midi(monkeypatch, tmp_path):
    """Con el motor disponible, build_song usa su MIDI y deja el marcador."""
    import shutil

    from bass_karaoke import jjazz

    src = _write_bass_midi(str(tmp_path / "src.mid"))
    monkeypatch.setattr(jjazz, "available", lambda: True)
    monkeypatch.setattr(jjazz, "sng_to_midi",
                        lambda _sng, mid: (shutil.copy(src, mid), True)[1])

    res = sng.build_song(str(_SNG_FILES[0]), out_dir=str(tmp_path), force=True)

    assert res["engine"] == "jjazzlab"
    assert Path(res["mid"]).is_file()
    marker = jjazz.read_marker(
        str(tmp_path / (res["song"]["name"] + ".jjazz.json")))
    assert marker["bass_channel"] == 10
    assert marker["bass_notes"] == 2
    assert res["notes"] == [(0, 4, 40), (4, 4, 45)]


@pytest.mark.skipif(not _SNG_FILES, reason="sin ficheros .sng de JJazzLab")
def test_build_song_auto_falls_back_without_engine(monkeypatch, tmp_path):
    from bass_karaoke import jjazz

    monkeypatch.setattr(jjazz, "available", lambda: False)
    res = sng.build_song(str(_SNG_FILES[0]), out_dir=str(tmp_path), force=True)
    assert res["engine"] == "yjz"
    assert res["mid"] is None
    assert not Path(res["musicxml"]).with_suffix(".jjazz.json").exists()
