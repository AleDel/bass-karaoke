"""Tests del saneado de MusicXML para Verovio (verovio_renderer.py).

Cubren `_strip_doctype`, que sustituyó a una regex con retroceso superlineal
(Sonar python:S8786).
"""
import pytest

from bass_karaoke.score.verovio_renderer import _strip_doctype, strip_tab_staff


def test_sin_doctype_devuelve_el_mismo_texto():
    xml = '<?xml version="1.0"?><score-partwise/>'
    assert _strip_doctype(xml) == xml


def test_quita_doctype_simple():
    xml = '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1//EN" "x.dtd">\n<score/>'
    assert _strip_doctype(xml) == '\n<score/>'


def test_quita_doctype_con_subconjunto_interno():
    xml = (
        '<!DOCTYPE score-partwise [\n'
        '  <!ENTITY mdash "&#8212;">\n'
        ']>\n'
        '<score/>'
    )
    assert _strip_doctype(xml) == '\n<score/>'


def test_subconjunto_con_angulo_dentro_no_corta_antes_de_tiempo():
    # El '>' del entity está dentro de [ ... ]: no debe cerrar el DOCTYPE.
    xml = '<!DOCTYPE s [<!ENTITY x ">">]><score/>'
    assert _strip_doctype(xml) == '<score/>'


def test_doctype_sin_cerrar_devuelve_intacto():
    xml = '<!DOCTYPE s [<score/>'
    assert _strip_doctype(xml) == xml


_MUSICXML_TAB_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1//EN" "x.dtd">
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Bass</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <staves>2</staves>
        <clef number="1"><sign>F</sign><line>4</line></clef>
        <clef number="2"><sign>TAB</sign><line>5</line></clef>
      </attributes>
      <note>
        <pitch><step>E</step><octave>2</octave></pitch>
        <duration>1</duration>
        <voice>1</voice>
        <type>quarter</type>
        <staff>2</staff>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def test_tab_only_se_reeetiqueta_a_notacion_estandar():
    out = strip_tab_staff(_MUSICXML_TAB_ONLY)
    assert "<staff>2</staff>" not in out        # ya no queda nada en el staff 2
    assert "<staff>1</staff>" in out            # se movió al staff 1
    assert "<sign>TAB</sign>" not in out        # la tablatura desaparece


def test_xml_invalido_devuelve_el_original():
    roto = "<score-partwise><part></score-partwise>"
    assert strip_tab_staff(roto) == roto
