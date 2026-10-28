"""Lectura de XML endurecida (defusedxml): DOCTYPE sí, entidades no.

Cubre las cuatro entradas que parsean XML del usuario: MusicXML
(`parser.py`), `.sng` (`sng.py`), el content.xml de los `.tg` y el
MusicXML que se le pasa a Verovio (`verovio_renderer.py`).
"""
import zipfile

import pytest
from defusedxml.common import DefusedXmlException

from bass_karaoke import parser, sng
from bass_karaoke.score.verovio_renderer import strip_tab_staff

# MusicXML mínimo con una nota en tablatura (cuerda 4, traste 3).
_SCORE = """<?xml version="1.0" encoding="UTF-8"?>
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
      <note>
        <pitch><step>G</step><octave>1</octave></pitch>
        <duration>4</duration>
        <type>quarter</type>
        <staff>2</staff>
        <notations><technical><string>4</string><fret>3</fret></technical></notations>
      </note>
    </measure>
  </part>
</score-partwise>
"""

# El DOCTYPE es habitual en MusicXML exportado (MuseScore, Finale…): debe seguir
# funcionando aunque no se resuelvan DTDs externos.
_SCORE_WITH_DOCTYPE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN"'
    ' "http://www.musicxml.org/dtds/partwise.dtd">\n'
    + _SCORE.split("\n", 1)[1]
)

# "Billion laughs": si se expandiera, cada nivel multiplica por 10.
_BOMB = """<?xml version="1.0"?>
<!DOCTYPE score-partwise [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
  <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
  <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
  <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
  <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
  <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<score-partwise version="3.1">
  <part-list/>
  <part id="P1"><measure number="1"><note><pitch><step>&lol9;</step></pitch>
  </note></measure></part>
</score-partwise>
"""


def test_musicxml_con_doctype_sigue_parseando(tmp_path):
    path = tmp_path / "score.musicxml"
    path.write_text(_SCORE_WITH_DOCTYPE, encoding="utf-8")

    notes, _sections, bpm, _tempo_map, stats = parser.parse_musicxml(str(path))

    assert len(notes) == 1
    assert (notes[0]["string"], notes[0]["fret"]) == (4, 3)
    assert bpm == pytest.approx(113.0)
    assert stats["has_tab"] is True


def test_musicxml_con_entidades_se_rechaza(tmp_path):
    path = tmp_path / "bomba.musicxml"
    path.write_text(_BOMB, encoding="utf-8")

    with pytest.raises(DefusedXmlException):
        parser.parse_musicxml(str(path))


def test_sng_con_entidades_se_rechaza(tmp_path):
    path = tmp_path / "bomba.sng"
    path.write_text(_BOMB, encoding="utf-8")

    with pytest.raises(DefusedXmlException):
        sng.parse_sng(str(path))


def test_parse_grace_notes_ignora_un_tg_con_entidades(tmp_path):
    path = tmp_path / "bomba.tg"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("content.xml", _BOMB)
        z.writestr("version.txt", "1.0")

    # parse_grace_notes ya devuelve [] ante cualquier content.xml ilegible.
    assert parser.parse_grace_notes(str(path), []) == []


def test_verovio_no_recibe_un_musicxml_con_entidades():
    assert strip_tab_staff(_BOMB) == ""


def test_verovio_conserva_el_musicxml_con_doctype():
    salida = strip_tab_staff(_SCORE_WITH_DOCTYPE)

    assert salida.startswith("<?xml")
    assert "<!DOCTYPE" not in salida        # se quita antes de Verovio
    assert "<score-partwise" in salida
