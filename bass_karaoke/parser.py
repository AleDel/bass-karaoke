"""
Parser de archivos MusicXML para Bass Karaoke.
Devuelve notas, secciones y BPM inicial.
"""
import xml.etree.ElementTree as ET

from .utils import fret_to_hz, hz_to_note_name


def parse_musicxml(filepath: str):
    """
    Parsea un MusicXML y extrae las notas del staff 2 (tablatura/bajo).

    Devuelve:
        notes    — lista de dicts con keys: fret, string, dur, start16, hz,
                   note_name, measure_num, section, step, octave, alter, dur_type
        sections — lista de (label, start16)
        bpm      — float con el tempo inicial encontrado en la partitura
    """
    tree = ET.parse(filepath)
    root = tree.getroot()
    bpm  = 113.0
    notes    = []
    sections = []

    for part in root.findall("part"):
        divs        = 960
        measure_abs = 0

        for measure in part.findall("measure"):
            measure_num = int(measure.get("number", "0"))
            cur_pos     = 0

            attr = measure.find("attributes")
            if attr is not None:
                d = attr.find("divisions")
                if d is not None:
                    divs = int(d.text)

            for direction in measure.findall("direction"):
                for metro in direction.findall(".//metronome"):
                    pm = metro.find("per-minute")
                    if pm is not None:
                        bpm = float(pm.text)
                for reh in direction.findall(".//rehearsal"):
                    if reh.text:
                        s16 = round((measure_abs + cur_pos) / divs * 4)
                        sections.append((reh.text.strip(), s16))

            for child in list(measure):
                tag = child.tag
                if tag == "backup":
                    cur_pos -= int(child.find("duration").text)
                elif tag == "forward":
                    cur_pos += int(child.find("duration").text)
                elif tag == "note":
                    is_chord  = child.find("chord") is not None
                    staff_el  = child.find("staff")
                    staff     = int(staff_el.text) if staff_el is not None else 1
                    dur_el    = child.find("duration")
                    dur_divs  = int(dur_el.text) if dur_el is not None else 0
                    is_rest   = child.find("rest") is not None
                    fret_el   = child.find(".//notations/technical/fret")
                    string_el = child.find(".//notations/technical/string")

                    if (staff == 2 and not is_rest and not is_chord
                            and fret_el is not None and string_el is not None):
                        fret    = int(fret_el.text)
                        string  = int(string_el.text)
                        hz      = fret_to_hz(fret, string)
                        start16 = round((measure_abs + cur_pos) / divs * 4)
                        dur16   = max(1, round(dur_divs / divs * 4))
                        pitch_el = child.find("pitch")
                        p_step   = "C"
                        p_octave = 3
                        p_alter  = 0
                        if pitch_el is not None:
                            se = pitch_el.find("step")
                            oe = pitch_el.find("octave")
                            ae = pitch_el.find("alter")
                            if se is not None: p_step   = se.text.strip()
                            if oe is not None: p_octave = int(oe.text)
                            if ae is not None: p_alter  = int(float(ae.text))
                        type_el  = child.find("type")
                        dur_type = type_el.text.strip() if type_el is not None else "quarter"
                        notes.append({
                            "fret": fret, "string": string,
                            "dur": dur16, "start16": start16,
                            "hz": hz, "note_name": hz_to_note_name(hz),
                            "measure_num": measure_num,
                            "section": f"Compás {measure_num}",
                            "step": p_step, "octave": p_octave, "alter": p_alter,
                            "dur_type": dur_type,
                        })
                    if not is_chord:
                        cur_pos += dur_divs

            time_el = measure.find("attributes/time")
            if time_el is not None:
                beats     = int(time_el.find("beats").text)
                beat_type = int(time_el.find("beat-type").text)
                measure_abs += int(divs * beats * (4 / beat_type))
            else:
                measure_abs += max(cur_pos, divs * 4)

    if sections:
        sec_idx = 0
        for note in notes:
            while (sec_idx + 1 < len(sections)
                   and note["start16"] >= sections[sec_idx + 1][1]):
                sec_idx += 1
            note["section"] = sections[sec_idx][0]

    return notes, sections, bpm
