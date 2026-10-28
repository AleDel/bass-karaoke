"""Normalización del mapa de tempo del editor de alineación (app.py).

`_align_normalize` fija las garantías del mapa que consumen el dibujo y el
reproductor: orden por posición, una sola marca por posición y una entrada
en 0. Son funciones puras, así que no hace falta ventana ni audio.
"""
from bass_karaoke.app import BassKaraoke


class FakeApp(BassKaraoke):
    """BassKaraoke sin __init__: `_align_normalize` solo usa `_align_entry`."""

    def __init__(self):
        pass


def test_entrada_de_dos_campos_usa_quarter():
    assert FakeApp()._align_entry((0, 120)) == (0.0, 120.0, "quarter")


def test_entrada_de_tres_campos_respeta_la_unidad():
    assert FakeApp()._align_entry(("16", "90", "eighth")) == (16.0, 90.0, "eighth")


def test_unidad_none_se_convierte_en_quarter():
    assert FakeApp()._align_entry((0, 100, None)) == (0.0, 100.0, "quarter")


def test_mapa_vacio_devuelve_el_tempo_por_defecto():
    assert FakeApp()._align_normalize([]) == [(0.0, 60.0, "quarter")]


def test_mapa_que_no_arranca_en_cero_se_completa():
    out = FakeApp()._align_normalize([(16, 100, "quarter"), (32, 110, "quarter")])
    assert out == [(0.0, 100.0, "quarter"),
                   (16.0, 100.0, "quarter"),
                   (32.0, 110.0, "quarter")]


def test_mapa_que_ya_arranca_en_cero_no_se_toca():
    out = FakeApp()._align_normalize([(0, 100), (32, 110)])
    assert out == [(0.0, 100.0, "quarter"), (32.0, 110.0, "quarter")]


def test_posiciones_repetidas_gana_la_ultima():
    out = FakeApp()._align_normalize([(0, 100), (16, 120), (16, 130)])
    assert out == [(0.0, 100.0, "quarter"), (16.0, 130.0, "quarter")]


def test_mapa_desordenado_se_ordena_por_posicion():
    out = FakeApp()._align_normalize([(32, 110), (0, 100), (16, 105)])
    assert [e[0] for e in out] == [0.0, 16.0, 32.0]
