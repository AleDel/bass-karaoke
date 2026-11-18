"""Configuración persistente sin pygame ni ventana."""
import json
from types import SimpleNamespace

import pytest

from bass_karaoke.settings import (
    SCORE_RENDERERS,
    Settings,
    parse_settings,
    read_settings,
    settings_to_dict,
    write_settings,
)
from bass_karaoke.state import MixerState

EXPECTED_KEYS = {
    "bpm", "bpm_map", "mp3_offset_sec", "mp3_offset_map", "song_start_map",
    "tempo_maps", "device_idx", "muted", "mix_song", "mix_bass", "mix_band",
    "mix_click", "muted_bass", "muted_band", "muted_click", "pitch_method",
    "countdown_enabled", "score_renderer", "gen_barlen", "gen_bars_per_chord",
    "song",
}


def _custom_settings() -> Settings:
    return Settings(
        bpm=97.5,
        mp3_offset_sec=1.25,
        song="A Foggy Day",
        device_idx=2,
        pitch_method="pesto",
        countdown_enabled=False,
        score_renderer="music21",
        gen_barlen=4,
        gen_bars_per_chord=3,
        mixer=MixerState(
            song_vol=0.8, bass_vol=0.5, band_vol=0.25, click_vol=0.9,
            song_muted=True, bass_muted=False, band_muted=True,
            click_muted=False,
        ),
        bpm_map={"A Foggy Day": 97.5},
        offset_map={"A Foggy Day": 1.25},
        song_start_map={"A Foggy Day": 0.5},
        tempo_maps={"A Foggy Day": [[0, 97.5, "quarter"]]},
    )


def test_missing_file_returns_defaults(tmp_path):
    settings = read_settings(str(tmp_path / "no-existe.json"))
    assert settings == Settings()


def test_write_read_roundtrip(tmp_path):
    path = str(tmp_path / "config.json")
    original = _custom_settings()

    write_settings(original, path)
    loaded = read_settings(path)

    assert loaded == original


def test_json_schema_keeps_the_old_keys(tmp_path):
    path = str(tmp_path / "config.json")
    write_settings(_custom_settings(), path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert set(data) == EXPECTED_KEYS
    assert data["mix_song"] == 0.8
    assert data["muted"] is True


def test_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ esto no es json", encoding="utf-8")
    assert read_settings(str(path)) == Settings()


def test_invalid_values_fall_back_individually():
    settings = parse_settings({
        "bpm": "no-es-un-numero",
        "pitch_method": "inventado",
        "score_renderer": "otro",
        "gen_barlen": "x",
        "bpm_map": ["no", "es", "dict"],
    })
    assert settings.bpm == Settings().bpm
    assert settings.pitch_method == "mpm"
    assert settings.score_renderer == "verovio"
    assert settings.gen_barlen == 3
    assert settings.bpm_map == {}


def test_mixer_values_are_clamped():
    settings = parse_settings({
        "mix_song": 1.8,
        "mix_bass": -0.4,
        "mix_band": 0.5,
        "mix_click": 2,
    })
    assert settings.mixer.song_vol == 1.0
    assert settings.mixer.bass_vol == 0.0
    assert settings.mixer.band_vol == 0.5
    assert settings.mixer.click_vol == 1.0


def test_device_and_song_are_validated_against_current_environment():
    settings = parse_settings(
        {"device_idx": 7, "song": "Ya no existe"},
        device_count=2,
        known_songs=["Otra canción"],
    )
    assert settings.device_idx == 0
    assert settings.song == ""

    kept = parse_settings(
        {"device_idx": 1, "song": "Otra canción"},
        device_count=2,
        known_songs=["Otra canción"],
    )
    assert kept.device_idx == 1
    assert kept.song == "Otra canción"


@pytest.mark.parametrize("renderer", SCORE_RENDERERS)
def test_known_renderers_are_accepted(renderer):
    assert parse_settings({"score_renderer": renderer}).score_renderer == renderer


def test_settings_to_dict_uses_mixer_state():
    data = settings_to_dict(_custom_settings())
    assert data["muted"] is True
    assert data["mix_band"] == 0.25
    assert data["mp3_offset_map"] == {"A Foggy Day": 1.25}


def test_parse_settings_accepts_non_dict():
    assert parse_settings(None) == Settings()


def _bare_app():
    """BassKaraoke sin __init__: estado perezoso y atributos mínimos."""
    from bass_karaoke.app import BassKaraoke

    app = BassKaraoke.__new__(BassKaraoke)
    app.song_name = "Mi Canción"
    app.tempo_map = [[0, 120.0, "quarter"]]
    return app


def test_app_save_and_load_config_roundtrip(monkeypatch, tmp_path):
    import bass_karaoke.app as app_module

    path = str(tmp_path / "config.json")
    monkeypatch.setattr(app_module, "CONFIG_PATH", path)

    app = _bare_app()
    app.bpm = 120.0
    app.mp3_offset_sec = 1.5
    app.song_start_sec = 0.2
    app.device_idx = 1
    app.pitch_method = "pesto"
    app.countdown_enabled = False
    app.score_renderer = "music21"
    app.gen_barlen = 4
    app.gen_bars_per_chord = 3
    app.mix_song = 0.9
    app.mix_bass = 0.4
    app.mix_band = 0.3
    app.mix_click = 0.7
    app.muted = True
    app.muted_bass = True
    app.muted_band = False
    app.muted_click = True
    app._save_config()

    with open(path, encoding="utf-8") as f:
        assert json.load(f)["song"] == "Mi Canción"

    loaded = _bare_app()
    loaded.audio_devices = [(0, "a"), (1, "b")]
    loaded.songs = [{"name": "Mi Canción"}]
    loaded.view = SimpleNamespace(pitch_menu_sel=0)
    loaded._load_config()

    assert loaded.bpm == 120.0
    assert loaded.mp3_offset_sec == 1.5
    assert loaded.pitch_method == "pesto"
    assert loaded.view.pitch_menu_sel > 0
    assert loaded.mixer_state == MixerState(
        song_vol=0.9, bass_vol=0.4, band_vol=0.3, click_vol=0.7,
        song_muted=True, bass_muted=True, band_muted=False, click_muted=True,
    )
    assert loaded._bpm_map["Mi Canción"] == 120.0
    assert loaded._song_start_map["Mi Canción"] == 0.2
