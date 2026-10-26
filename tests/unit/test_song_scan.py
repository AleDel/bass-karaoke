"""El selector incluye canciones que solo tienen un .sng (pendientes de F7)."""
from bass_karaoke import app as app_module
from bass_karaoke.app import BassKaraoke


class _ScanApp(BassKaraoke):
    """BassKaraoke sin __init__: solo se usa _scan_songs()."""


def test_scan_songs_includes_sng_only(monkeypatch, tmp_path):
    song_dir = tmp_path / "tema"
    song_dir.mkdir()
    (song_dir / "tema.sng").write_text("<song/>", encoding="utf-8")
    monkeypatch.setattr(app_module, "SONGS_DIR", str(tmp_path))

    songs = _ScanApp.__new__(_ScanApp)._scan_songs()

    assert len(songs) == 1
    assert songs[0]["sng"].endswith("tema.sng")
    assert songs[0]["musicxml"] is None
    assert songs[0]["audio_only"] is True


def test_scan_songs_prefers_musicxml_over_sng(monkeypatch, tmp_path):
    song_dir = tmp_path / "tema"
    song_dir.mkdir()
    (song_dir / "tema.sng").write_text("<song/>", encoding="utf-8")
    (song_dir / "tema.musicxml").write_text(
        "<score-partwise/>", encoding="utf-8")
    monkeypatch.setattr(app_module, "SONGS_DIR", str(tmp_path))

    songs = _ScanApp.__new__(_ScanApp)._scan_songs()

    assert songs[0]["musicxml"].endswith("tema.musicxml")
    assert songs[0]["sng"].endswith("tema.sng")
    assert songs[0]["audio_only"] is False
