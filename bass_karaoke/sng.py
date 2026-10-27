"""Lector de ficheros .sng de JJazzLab y generador de la línea de bajo.

Un ``.sng`` es un XML con el cifrado de la canción (chord lead sheet): tempo,
acordes con su posición ``[compás:tiempo]``, secciones y la estructura. No
contiene la línea de bajo: JJazzLab la genera al reproducir con su motor
JJSwing (patrones reales + fallback de arpegio).

Este módulo replica el criterio de ese motor para producir material de
práctica:

- ``yjz``       (por defecto) frases reales del ritmo *jjSwing* (``psBase.yjz``)
               con la variación de cada parte; sin JJazzLab cae a ``jjazz``.
- ``walking``  negras caminantes: raíz → 3ª → 5ª → aproximación a la
               fundamental del acorde siguiente (estilo walking bass).
- ``jjazz``    fallback exacto de JJSwing: raíz + 3ª + 5ª repartidos según
               la duración del acorde.
- ``two_feel`` raíz en los tiempos 1 y 3.

La salida es el formato que ya consume la app: ``<nombre>.musicxml`` (con
tablatura y armonía) + ``<nombre>.chords.json``. La app también puede generar
la partitura desde el propio ``.sng`` (tecla ``F7``) si está en ``songs/``.
"""
from __future__ import annotations

import math
import os
import re
import sys
import xml.etree.ElementTree as ET

from .build import _add_rest, build_musicxml
from .chords import NAMES_ES, save_song_map
from .config import SONGS_DIR

_TS_WORDS = {
    "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6,
    "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10, "ELEVEN": 11, "TWELVE": 12,
}

# cualidad -> (semitonos de 3ª, semitonos de 5ª, sufijo español, kind MusicXML)
# 3ª None = acorde sin tercera (sus / power chord).
_QUALITIES = {
    "":        (4, 7, "",       "major"),
    "m":       (3, 7, "m",      "minor"),
    "7":       (4, 7, "7",      "dominant"),
    "M7":      (4, 7, "maj7",   "major-seventh"),
    "m7":      (3, 7, "m7",     "minor-seventh"),
    "6":       (4, 7, "6",      "major-sixth"),
    "m6":      (3, 7, "m6",     "minor-sixth"),
    "69":      (4, 7, "6",      "major-sixth"),
    "m69":     (3, 7, "m6",     "minor-sixth"),
    "dim":     (3, 6, "dim",    "diminished"),
    "dim7":    (3, 6, "dim",    "diminished-seventh"),
    "dim7M":   (3, 6, "dim",    "diminished-seventh"),
    "+":       (4, 8, "aug",    "augmented"),
    "m+":      (3, 8, "aug",    "augmented"),
    "7#5":     (4, 8, "7",      "augmented-seventh"),
    "7#9#5":   (4, 8, "7",      "augmented-seventh"),
    "7b9#5":   (4, 8, "7",      "augmented-seventh"),
    "9#5":     (4, 8, "9",      "augmented-seventh"),
    "M7#5":    (4, 8, "maj7",   "major-seventh"),
    "m7b5":    (3, 6, "m7b5",   "half-diminished"),
    "m9b5":    (3, 6, "m7b5",   "half-diminished"),
    "7b5":     (4, 6, "7",      "dominant"),
    "7b9b5":   (4, 6, "7",      "dominant"),
    "7#9b5":   (4, 6, "7",      "dominant"),
    "9b5":     (4, 6, "9",      "dominant"),
    "sus":     (5, 7, "sus4",   "suspended-fourth"),
    "sus2":    (2, 7, "sus2",   "suspended-second"),
    "2":       (2, 7, "sus2",   "suspended-second"),
    "7sus":    (5, 7, "7",      "suspended-fourth"),
    "9sus":    (5, 7, "9",      "suspended-fourth"),
    "13sus":   (5, 7, "9",      "suspended-fourth"),
    "7susb9":  (5, 7, "7",      "suspended-fourth"),
    "9":       (4, 7, "9",      "dominant-ninth"),
    "13":      (4, 7, "9",      "dominant-13th"),
    "m9":      (3, 7, "m9",     "minor-ninth"),
    "m11":     (3, 7, "m9",     "minor-11th"),
    "M9":      (4, 7, "maj7",   "major-ninth"),
    "M13":     (4, 7, "maj7",   "major-13th"),
    "m7M":     (3, 7, "m7",     "major-minor"),
    "add9":    (4, 7, "add9",   "major"),
    "5":       (None, 7, "5",   "power"),
    "7b9":     (4, 7, "7",      "dominant"),
    "7#9":     (4, 7, "7",      "dominant"),
    "7#11":    (4, 7, "7",      "dominant"),
    "7b9#11":  (4, 7, "7",      "dominant"),
    "7#9#11":  (4, 7, "7",      "dominant"),
    "M7#11":   (4, 7, "maj7",   "major-seventh"),
    "M9#11":   (4, 7, "maj7",   "major-ninth"),
    "9#11":    (4, 7, "9",      "dominant-ninth"),
    "13b9":    (4, 7, "9",      "dominant-13th"),
    "13#11":   (4, 7, "9",      "dominant-13th"),
    "13#9":    (4, 7, "9",      "dominant-13th"),
}

_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_CHORD_RE = re.compile(r"([A-G])([#b]*)(.*)")
_BASS_RE = re.compile(r"([A-G])([#b]*)")

# Registro de trabajo: E1..A2 (el bajo de 4 cuerdas, como InstrumentFamily.Bass
# de JJazzLab, que mapea todo a E1-D#2).
_RANGE = (28, 43)
_ROOT_REF = 33          # nota de referencia para colocar las fundamentales
_TAB_MIN, _TAB_MAX = 28, 58     # rango tocable en el mástil de la app

_POS_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_SEC_REF_RE = re.compile(r"CLI__SectionImpl(?:\[(\d+)\])?$")


# ── Lectura del .sng ────────────────────────────────────────────────────────
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ts_of(name: str):
    """``'SIX_EIGHT'`` -> ``(6, 8)``; ``None`` si no se reconoce."""
    parts = (name or "").split("_")
    if len(parts) != 2:
        return None
    num, den = _TS_WORDS.get(parts[0]), _TS_WORDS.get(parts[1])
    return (num, den) if num and den else None


def _bar_quarters(ts) -> float:
    num, den = ts
    return num * 4.0 / den


def _part_variation(part) -> str:
    """Variación de JJazzLab de un ``SongPartImpl`` (``rpVariationID``)."""
    mapping = part.find("spHashMapRpIdValue")
    if mapping is None:
        return ""
    for entry in mapping:
        strings = [c for c in entry if _local(c.tag) == "string"]
        if len(strings) >= 2 and (strings[0].text or "").strip() == "rpVariationID":
            return (strings[1].text or "").strip()
    return ""


def parse_sng(path: str) -> dict:
    """Lee un ``.sng`` y devuelve el cifrado en orden de reproducción.

    Claves del dict:
        name, tempo, comments, time_signature, beats_per_bar, total_bars,
        sections  [(label, start_bar, nb_bars)],
        chords    [{start, dur, name, bar}] con tiempos en negras y orden de
                  la estructura (las secciones repetidas se expanden),
        warnings  [str]
    """
    root = ET.parse(path).getroot()
    warnings = []
    name = os.path.splitext(os.path.basename(path))[0]
    try:
        tempo = int(round(float(root.get("spTempo") or 0)))
    except ValueError:
        tempo = 0
    if tempo <= 0:
        tempo = 120
        warnings.append("tempo ausente o inválido: se usa 120")

    items = root.find("spChordLeadSheet/spItems")
    if items is None:
        raise ValueError(f"{name}: sin spChordLeadSheet/spItems")

    sections, counts, lead_chords = {}, {}, []
    for it in list(items):
        tag = _local(it.tag)
        counts[tag] = counts.get(tag, 0) + 1
        if tag.endswith("SectionImpl"):
            sections[counts[tag]] = {
                "label": it.get("spName") or "?",
                "ts": _ts_of(it.get("spTs")),
                "bar": int(it.get("spBarIndex") or 0),
            }
        elif tag.endswith("ChordSymbolImpl"):
            pos = it.find("spPos")
            chord = it.find("spChord")
            m = _POS_RE.match((pos.get("spPos") if pos is not None else "") or "")
            if not m:
                continue
            lead_chords.append({
                "bar": int(m.group(1)),
                "beat": float(m.group(2)),
                "name": (chord.get("spName") or "").strip() if chord is not None else "",
            })

    parts = []
    structure = root.find("spSongStructure")
    for it in (structure.iter() if structure is not None else ()):
        if _local(it.tag) != "SongPartImpl":
            continue
        ref = next((c for c in it.iter()
                    if _local(c.tag) == "spParentSection"), None)
        m = _SEC_REF_RE.search((ref.get("reference") if ref is not None else "") or "")
        parts.append({
            "label": it.get("spName") or "?",
            "start": int(it.get("spStartBarIndex") or 0),
            "nb": int(it.get("spNbBars") or 0),
            "ts": _ts_of(it.get("spRhythmTs")),
            "sec": int(m.group(1) or 1) if m else 1,
            "variation": _part_variation(it),
        })
    if not parts:
        raise ValueError(f"{name}: sin spSongStructure/SongPartImpl")

    first_ts = sections[parts[0]["sec"]]["ts"] if parts[0]["sec"] in sections else None
    first_ts = first_ts or parts[0]["ts"] or (4, 4)
    barlen = _bar_quarters(first_ts)
    used_ts = {parts[0]["ts"] or first_ts}
    used_ts |= {sections[p["sec"]]["ts"] for p in parts
                if p["sec"] in sections and sections[p["sec"]]["ts"]}
    if len({_bar_quarters(ts) for ts in used_ts}) > 1:
        warnings.append("cambios de compás: la partitura usa el primero "
                        f"({barlen:g}/4)")

    events = []
    for part in parts:
        sec = sections.get(part["sec"])
        if sec is None:
            warnings.append(f"sección {part['sec']} sin definir en {part['label']}")
            continue
        ts = sec["ts"] or first_ts
        beat_factor = 4.0 / ts[1]
        if _bar_quarters(ts) != barlen:
            warnings.append(f"compás distinto en la sección {part['label']}")
        for chord in lead_chords:
            rel = chord["bar"] - sec["bar"]
            if 0 <= rel < part["nb"]:
                events.append({
                    "start": (part["start"] + rel) * barlen
                             + chord["beat"] * beat_factor,
                    "name": chord["name"],
                    "bar": part["start"] + rel,
                })

    events.sort(key=lambda e: e["start"])
    deduped = []
    for ev in events:
        if deduped and abs(deduped[-1]["start"] - ev["start"]) < 1e-6:
            continue
        deduped.append(ev)
    events = deduped

    total_bars = sum(p["nb"] for p in parts)
    total_beats = total_bars * barlen
    for i, ev in enumerate(events):
        nxt = events[i + 1]["start"] if i + 1 < len(events) else total_beats
        ev["dur"] = max(0.25, nxt - ev["start"])

    return {
        "name": name,
        "tempo": tempo,
        "comments": (root.findtext("spComments") or "").strip(),
        "time_signature": parts[0]["ts"],
        "beats_per_bar": barlen,
        "total_bars": total_bars,
        "sections": [{"label": p["label"], "start_bar": p["start"],
                      "nb_bars": p["nb"], "variation": p.get("variation", "")}
                     for p in parts],
        "chords": events,
        "warnings": warnings,
    }


# ── Acordes ─────────────────────────────────────────────────────────────────
def _pc(letter: str, accidentals: str) -> int:
    pc = _SEMITONES[letter]
    for ch in accidentals:
        pc += 1 if ch == "#" else -1
    return pc % 12


def parse_chord(name: str):
    """``'Bb69'`` -> ``{root_pc, third, fifth, bass_pc, es, kind}``.

    ``None`` para acorde vacío (N.C.) o no reconocido.
    """
    text = (name or "").strip()
    if not text:
        return None
    m = _CHORD_RE.fullmatch(text)
    if not m:
        return None
    letter, acc, rest = m.group(1), m.group(2), m.group(3)
    root_pc = _pc(letter, acc)
    bass_pc = root_pc
    if "/" in rest:
        main, bass_text = rest.split("/", 1)
        rest = main
        bm = _BASS_RE.fullmatch(bass_text.strip())
        if bm:
            bass_pc = _pc(bm.group(1), bm.group(2))
    quality = _QUALITIES.get(rest)
    if quality is None:
        quality = (4, 7, "", "major")
    third, fifth, suffix, kind = quality
    es = NAMES_ES[root_pc] + suffix
    return {"root_pc": root_pc, "third": third, "fifth": fifth,
            "bass_pc": bass_pc, "es": es, "kind": kind, "quality": rest}


# ── Generación de la línea ──────────────────────────────────────────────────
def _nearest(pc: int, ref: int, lo: int = _RANGE[0], hi: int = _RANGE[1]) -> int:
    """Nota de la clase ``pc`` más cercana a ``ref`` dentro de ``[lo, hi]``."""
    pc %= 12
    base = ref - ((ref - pc) % 12)
    candidates = [c for c in (base, base + 12) if lo <= c <= hi]
    if not candidates:
        note = base
        while note < lo:
            note += 12
        while note > hi:
            note -= 12
        return note
    return min(candidates, key=lambda c: abs(c - ref))


def _root_pitch(pc: int, prev: int) -> int:
    """Octava de ``pc`` más cercana a ``prev`` dentro de Mi1-Sol2."""
    candidates = [p for p in range(28, 44) if p % 12 == pc % 12]
    if not candidates:
        return _nearest(pc, prev, 28, 43)
    return min(candidates,
               key=lambda pitch: abs(pitch - prev) + 0.6 * max(0, pitch - 39))


def _band_pitch(pc: int, root: int, prev: int, below: int = 4,
                above: int = 8) -> int:
    """Octava de ``pc`` en la banda del acorde, lo más cerca de ``prev``."""
    lo, hi = max(_TAB_MIN, root - below), min(45, root + above)
    candidates = [p for p in range(lo, hi + 1) if p % 12 == pc % 12]
    if not candidates:
        return _nearest(pc, prev, _TAB_MIN, 47)
    return min(candidates, key=lambda pitch: abs(pitch - prev))


def _chord_tone(info: dict, prev: int, which: int, root: int | None = None) -> int:
    """3ª (which=0) o 5ª (which=1) más cercana a ``prev``, sin repetirla."""
    degrees = [info["third"], info["fifth"]]
    pool = []
    for degree in degrees:
        if degree is None:
            continue
        pc = (info["root_pc"] + degree) % 12
        pitch = _band_pitch(pc, root, prev) if root is not None else _nearest(pc, prev)
        if pitch != prev and pitch not in pool:
            pool.append(pitch)
    if not pool:
        pc = (info["root_pc"] + info["fifth"]) % 12
        return _band_pitch(pc, root, prev) if root is not None else _nearest(pc, prev)
    return pool[which % len(pool)]


def _colour_tone(info: dict, ref: int, avoid=None, root: int | None = None) -> int:
    """Grado del acorde (3ª/5ª) más cercano a ``ref``, evitando ``avoid``."""
    pool = []
    for degree in (info["third"], info["fifth"]):
        if degree is None:
            continue
        pc = (info["root_pc"] + degree) % 12
        pitch = _band_pitch(pc, root, ref) if root is not None else _nearest(pc, ref)
        if pitch != avoid and pitch not in pool:
            pool.append(pitch)
    if not pool:
        pc = (info["root_pc"] + info["fifth"]) % 12
        return _band_pitch(pc, root, ref) if root is not None else _nearest(pc, ref)
    return min(pool, key=lambda p: abs(p - ref))


def _approach(prev: int, target: int, lo: int = 28, hi: int = 45):
    """Nota de aproximación a la altura ``target``: semitono, tono, 3ª, 4ª."""
    best = None
    for step in (1, 2, 3, 4, 5):
        for sign in (-1, 1):
            pitch = target + sign * step
            if not (lo <= pitch <= hi) or pitch == prev:
                continue
            leap = abs(pitch - prev)
            if leap > 7:
                continue
            key = (step, leap, 0 if sign < 0 else 1)
            if best is None or key < best[0]:
                best = (key, pitch)
    return None if best is None else best[1]


def generate_line(song: dict, style: str = "yjz"):
    """Devuelve ``[(start16, dur16, midi)]`` para el cifrado de ``song``."""
    if style == "yjz":
        return _generate_yjz(song)
    barlen = song["beats_per_bar"]
    total_beats = song["total_bars"] * barlen
    events = song["chords"]
    raw = []
    prev = None

    for i, ev in enumerate(events):
        info = parse_chord(ev["name"])
        start, dur = ev["start"], ev["dur"]
        if info is None or dur <= 0:
            prev = None
            continue
        next_info = None
        if i + 1 < len(events) and abs((start + dur) - events[i + 1]["start"]) < 1e-6:
            next_info = parse_chord(events[i + 1]["name"])
        slash = info["bass_pc"] != info["root_pc"]
        root = _root_pitch(info["bass_pc"],
                           _ROOT_REF if prev is None else prev)
        next_root = None
        if next_info is not None:
            next_root = _root_pitch(next_info["bass_pc"], root)

        if style == "two_feel":
            raw.append((start, min(dur, 1.9) if dur >= 3.5 else dur, root, 88))
            if dur >= 3.5:
                raw.append((start + 2, min(dur - 2, 1.9), root, 80))
            prev = root

        elif style == "jjazz":
            adjusted = dur - 0.09
            if adjusted >= 2.8:
                p2 = math.floor(adjusted)
                p1 = math.floor(adjusted - 1)
                third = root if slash else _chord_tone(info, root, 0)
                fifth = root if slash else _chord_tone(info, third, 1)
                raw.append((start, max(0.10, p1 - 0.09), root, 80))
                raw.append((start + p1, max(0.10, p2 - p1 - 0.09), third, 76))
                raw.append((start + p2, max(0.10, adjusted - p2), fifth, 83))
                prev = fifth
            elif adjusted >= 1.8:
                p1 = math.floor(adjusted)
                fifth = root if slash else _chord_tone(info, root, 1)
                raw.append((start, max(0.10, p1 - 0.09), root, 80))
                raw.append((start + p1, max(0.10, adjusted - p1), fifth, 76))
                prev = fifth
            else:
                raw.append((start, dur, root, 80))
                prev = root

        else:   # walking
            raw.append((start, min(dur, 1.0), root, 88))
            prev = root
            beats = int(math.floor(dur + 1e-6))
            positions = [p for p in range(1, beats + 1) if p <= dur - 0.25]
            next_root_pc = next_info["bass_pc"] if next_info is not None else None
            same_root = (next_info is not None
                         and next_info["bass_pc"] == info["bass_pc"])
            tone_index = 0
            for index, pos in enumerate(positions):
                last = index == len(positions) - 1
                if last and next_root is not None and not same_root:
                    pitch = _approach(prev, next_root)
                    if pitch is None:
                        pitch = _colour_tone(info, next_root, avoid=prev, root=root)
                elif last and next_root_pc is not None:
                    pitch = _colour_tone(info, _nearest(next_root_pc, prev),
                                         avoid=prev, root=root)
                elif pos % barlen == 0:
                    pitch = _root_pitch(info["bass_pc"], prev)
                else:
                    pitch = _chord_tone(info, prev, tone_index, root=root)
                    tone_index += 1
                note_dur = max(0.25, dur - pos)
                raw.append((start + pos, note_dur, pitch, 74 if last else 78))
                prev = pitch

    return _to_sixteenths(raw, total_beats)


def _generate_yjz(song: dict):
    """Línea de bajo con las frases reales de jjSwing (JJazzLab).

    Usa el cifrado y las variaciones ``rpVariationID`` de cada parte del
    ``.sng``; si faltan los datos de jjSwing cae a ``'jjazz'``.
    """
    from .audio import band

    bpm = float(song["tempo"])
    barlen = song["beats_per_bar"]
    total_beats = song["total_bars"] * barlen
    if bpm <= 0 or total_beats <= 0:
        return generate_line(song, style="jjazz")
    chords = [(ev["start"] * 60.0 / bpm, ev["name"]) for ev in song["chords"]]
    sections = [(s["start_bar"], s["nb_bars"], s.get("variation", ""))
                for s in song["sections"]]
    events = band.bass_events(chords, bpm, barlen, total_beats * 60.0 / bpm,
                              sections)
    if not events:
        return generate_line(song, style="jjazz")
    raw = [(t * bpm / 60.0, dur * bpm / 60.0, pitch, vel)
           for t, dur, pitch, vel in events]
    return _to_sixteenths(raw, total_beats)


def _to_sixteenths(raw, total_beats: float):
    """Normaliza a 16avos, sin solapes y dentro del mástil de la app."""
    out = []
    for start, dur, midi, _vel in raw:
        if start >= total_beats:
            continue
        while midi > _TAB_MAX:
            midi -= 12
        while midi < _TAB_MIN:
            midi += 12
        s16 = int(round(start * 4))
        d16 = max(1, int(round(dur * 4)))
        out.append([s16, d16, int(midi)])
    out.sort()
    for i, note in enumerate(out):
        limit = (out[i + 1][0] - note[0]) if i + 1 < len(out) else None
        if limit is not None and limit > 0:
            note[1] = min(note[1], limit)
        note[1] = max(1, note[1])
    return [tuple(n) for n in out]


# ── Escritura del MusicXML + chords.json ────────────────────────────────────
def _measure(part, number: int, barlen: int):
    meas = ET.SubElement(part, "measure", number=str(number))
    attr = ET.SubElement(meas, "attributes")
    ET.SubElement(attr, "divisions").text = "4"
    time = ET.SubElement(attr, "time")
    ET.SubElement(time, "beats").text = str(barlen)
    ET.SubElement(time, "beat-type").text = "4"
    ET.SubElement(attr, "staves").text = "2"
    return meas


def _pad_measures(tree, total_bars: int, barlen: int):
    part = tree.getroot().find("part")
    if part is None:
        return
    measures = part.findall("measure")
    bar16 = barlen * 4
    for number in range(len(measures) + 1, total_bars + 1):
        meas = _measure(part, number, barlen)
        _add_rest(meas, bar16)


_STEP_ALTER = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1),
               4: ("E", 0), 5: ("F", 0), 6: ("F", 1), 7: ("G", 0),
               8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}


def _harmony(info: dict, offset16: int):
    harm = ET.Element("harmony")
    root = ET.SubElement(harm, "root")
    step, alter = _STEP_ALTER[info["root_pc"] % 12]
    ET.SubElement(root, "root-step").text = step
    if alter:
        ET.SubElement(root, "root-alter").text = str(alter)
    kind = ET.SubElement(harm, "kind")
    kind.text = info["kind"]
    if info["quality"]:
        kind.set("text", info["quality"])
    if info["bass_pc"] != info["root_pc"]:
        bass = ET.SubElement(harm, "bass")
        bstep, balter = _STEP_ALTER[info["bass_pc"] % 12]
        ET.SubElement(bass, "bass-step").text = bstep
        if balter:
            ET.SubElement(bass, "bass-alter").text = str(balter)
    if offset16:
        ET.SubElement(harm, "offset").text = str(offset16)
    return harm


def _patch_harmonies(tree, song: dict):
    """Reemplaza la armonía simplificada por el cifrado real del .sng."""
    part = tree.getroot().find("part")
    if part is None:
        return
    bar16 = int(round(song["beats_per_bar"] * 4))
    measures = part.findall("measure")
    for meas in measures:
        for harm in meas.findall("harmony"):
            meas.remove(harm)
    pending = {}
    for ev in song["chords"]:
        info = parse_chord(ev["name"])
        if info is None:
            continue
        start16 = int(round(ev["start"] * 4))
        index = start16 // bar16
        if not (0 <= index < len(measures)):
            continue
        pending.setdefault(index, []).append((start16 % bar16, info))
    for index, events in pending.items():
        meas = measures[index]
        pos = 1 if meas.find("attributes") is not None else 0
        for step, (offset, info) in enumerate(sorted(events,
                                                     key=lambda e: e[0])):
            meas.insert(pos + step, _harmony(info, offset))


def _add_rehearsals(tree, song: dict):
    part = tree.getroot().find("part")
    if part is None:
        return
    measures = part.findall("measure")
    for section in song["sections"]:
        index = int(section["start_bar"])
        if not (0 <= index < len(measures)):
            continue
        meas = measures[index]
        direction = ET.Element("direction", placement="above")
        dtype = ET.SubElement(direction, "direction-type")
        ET.SubElement(dtype, "rehearsal").text = str(section["label"])
        pos = 1 if meas.find("attributes") is not None else 0
        meas.insert(pos, direction)


def _notes_from_jjazz(song: dict, sng_path: str, mid_path: str):
    """Línea de bajo tal cual la genera JJazzLab (MIDI real).

    Devuelve ``(notes16, track)`` o ``(None, None)`` si no hay motor o el
    MIDI no trae pista de bajo.
    """
    from . import jjazz

    if not jjazz.available():
        return None, None
    if not jjazz.sng_to_midi(sng_path, mid_path):
        return None, None
    track = jjazz.bass_track(mid_path)
    if not track or not track["notes"]:
        try:
            os.remove(mid_path)
        except OSError:
            pass
        return None, None
    total_beats = float(song["total_bars"] * song["beats_per_bar"])
    notes = _to_sixteenths(track["notes"], total_beats)
    return (notes or None), track


def build_song(sng_path: str, out_dir: str | None = None, style: str = "yjz",
               force: bool = False, engine: str = "auto") -> dict:
    """Escribe ``<nombre>.musicxml`` + ``<nombre>.chords.json`` de un ``.sng``.

    ``engine='auto'`` (por defecto) pide el MIDI al motor de JJazzLab; si no
    está disponible cae al generador interno (``style``). Con ``'internal'``
    se usa siempre el generador interno.
    """
    song = parse_sng(sng_path)
    name = song["name"]
    target_dir = out_dir or os.path.join(SONGS_DIR, name)
    xml_path = os.path.join(target_dir, name + ".musicxml")
    json_path = os.path.join(target_dir, name + ".chords.json")
    if os.path.exists(xml_path) and not force:
        raise FileExistsError(f"ya existe {xml_path} (usa force=True)")
    os.makedirs(target_dir, exist_ok=True)

    notes, used = None, style
    mid_path = os.path.join(target_dir, name + ".mid")
    marker_path = os.path.join(target_dir, name + ".jjazz.json")
    if os.path.exists(mid_path) and not os.path.exists(marker_path):
        # No pisar un MIDI ajeno (sin marcador): el del motor va aparte.
        mid_path = os.path.join(target_dir, name + ".jjazz.mid")
    if engine == "auto" and style in ("yjz", "jjazz"):
        notes, track = _notes_from_jjazz(song, sng_path, mid_path)
        if notes:
            used = "jjazzlab"
            from . import jjazz
            jjazz.write_marker(target_dir, name, mid_path, track)
    if not notes:
        notes = generate_line(song, style=style)
    if not notes:
        raise ValueError(f"{name}: el cifrado no produjo notas")

    barlen = int(round(song["beats_per_bar"]))
    segments = []
    for ev in song["chords"]:
        info = parse_chord(ev["name"])
        if info is None:
            continue
        segments.append((int(round(ev["start"] * 4)), info["root_pc"],
                         info["third"] == 3))
    tree = build_musicxml(notes, song["tempo"], chords=segments, barlen=barlen)
    _pad_measures(tree, song["total_bars"], barlen)
    _patch_harmonies(tree, song)
    _add_rehearsals(tree, song)
    ET.indent(tree, space="  ")
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)

    bpm = float(song["tempo"])
    chords_es = []
    for ev in song["chords"]:
        info = parse_chord(ev["name"])
        if info is None:
            continue
        seconds = round(int(round(ev["start"] * 4)) / 4.0 * 60.0 / bpm, 2)
        chords_es.append((seconds, info["es"]))
    save_song_map(json_path, chords_es, [], barlen=barlen)

    return {"song": song, "notes": notes, "musicxml": xml_path,
            "chords_json": json_path, "style": style, "engine": used,
            "mid": mid_path if used == "jjazzlab" else None}


# ── Utilidades de inspección ────────────────────────────────────────────────
_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _note_name(midi: int) -> str:
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def describe(song: dict, notes) -> str:
    """Texto con la línea generada, compás a compás (para revisión rápida)."""
    barlen = song["beats_per_bar"]
    per_bar = int(round(barlen * 4))
    bars = {}
    for start, dur, midi in notes:
        bar = start // per_bar
        for tick in range(start, start + dur):
            bars.setdefault(bar, {})[tick - bar * per_bar] = _note_name(midi)
    chords_by_bar = {}
    for ev in song["chords"]:
        chords_by_bar.setdefault(ev["bar"], ev["name"] or "N.C.")
    lines = []
    for bar in range(song["total_bars"]):
        cells = [bars.get(bar, {}).get(i, ".") for i in range(0, per_bar, 4)]
        lines.append(f"{bar + 1:3d} {chords_by_bar.get(bar, ''):8s} "
                     + " ".join(f"{c:4s}" for c in cells))
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    style, out_dir, show, force = "yjz", None, False, False
    engine = "auto"
    files = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--style" and i + 1 < len(argv):
            style = argv[i + 1]
            i += 2
            continue
        if arg == "--engine" and i + 1 < len(argv):
            engine = argv[i + 1]
            i += 2
            continue
        if arg == "--out" and i + 1 < len(argv):
            out_dir = argv[i + 1]
            i += 2
            continue
        if arg in ("--print", "-p"):
            show = True
        elif arg in ("--force", "-f"):
            force = True
        elif arg.startswith("-"):
            print(f"opción desconocida: {arg}", file=sys.stderr)
            return 2
        else:
            files.append(arg)
        i += 1
    if not files:
        print("uso: python -m bass_karaoke.sng FICHERO.sng [...] "
              "[--engine auto|internal] [--style yjz|walking|jjazz|two_feel] "
              "[--out DIR] [--print] [--force]",
              file=sys.stderr)
        return 2
    if style not in ("yjz", "walking", "jjazz", "two_feel"):
        print(f"estilo desconocido: {style}", file=sys.stderr)
        return 2
    if engine not in ("auto", "internal"):
        print(f"motor desconocido: {engine}", file=sys.stderr)
        return 2

    for path in files:
        try:
            result = build_song(path, out_dir=out_dir, style=style,
                                force=force, engine=engine)
        except (FileExistsError, ValueError) as exc:
            print(f"[ERROR] {path}: {exc}", file=sys.stderr)
            return 1
        song = result["song"]
        print(f"[OK] {song['name']}: {song['total_bars']} compases, "
              f"{song['tempo']} BPM, {len(result['notes'])} notas, "
              f"{result.get('engine', style)}")
        for warning in song["warnings"]:
            print(f"     aviso: {warning}")
        print(f"     {result['musicxml']}")
        print(f"     {result['chords_json']}")
        if result.get("mid"):
            print(f"     {result['mid']}")
        if show:
            print(describe(song, result["notes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
