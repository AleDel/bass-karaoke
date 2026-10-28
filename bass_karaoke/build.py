"""Construcción de partituras (MusicXML + chords.json) desde notas de bajo.

Este módulo es la versión reutilizable de `songs/<canción>/work/build_song.py`:
recibe eventos de nota ``(start, end, midi)`` en segundos, ajusta la rejilla de
16avos, cuantiza, deriva los acordes de las raíces del bajo y escribe el
MusicXML con tablatura + el ``.chords.json`` del karaoke.

Se usa tanto desde el script reproducible de una canción como desde la app
(transcripción de canciones que solo tienen audio).
"""
from __future__ import annotations

import os

# ElementTree solo se usa para CONSTRUIR MusicXML; la lectura va por defusedxml.
import xml.etree.ElementTree as ET  # nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from collections import defaultdict

import numpy as np
from defusedxml.ElementTree import parse as _parse_xml

# ── Métrica y armonía (valores por defecto; se pueden pasar por argumento) ────
BARLEN_DEFAULT = 3          # 3/4 corridos
BARS_PER_CHORD_DEFAULT = 2
KEY_FIFTHS_DEFAULT = -4     # Fm (4 bemoles)
KEY_MODE_DEFAULT = "minor"
CLEF_SIGN_DEFAULT = "F"
CLEF_LINE_DEFAULT = 4

OPEN_MIDI = {4: 28, 3: 33, 2: 38, 1: 43}
NECK_FRETS = 15
NAMES = ["C", "C#", "D", "D#", "E", "F",
         "F#", "G", "G#", "A", "A#", "B"]
NAMES_ES = ["Do", "Do#", "Re", "Mib", "Mi", "Fa",
            "Fa#", "Sol", "Lab", "La", "Sib", "Si"]
HARMONY_ROOT = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1),
                4: ("E", 0), 5: ("F", 0), 6: ("F", 1), 7: ("G", 0),
                8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
PC_STEP_ALTER = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1),
                 4: ("E", 0), 5: ("F", 0), 6: ("F", 1), 7: ("G", 0),
                 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}


def load_note_events(midi_path):
    """Lee un MIDI y devuelve (start_sec, end_sec, midi) monofonizado."""
    import mido
    mid = mido.MidiFile(midi_path)
    tempo = 500000
    for tr in mid.tracks:
        for msg in tr:
            if msg.type == "set_tempo":
                tempo = msg.tempo
    spb = tempo / 1_000_000
    tpb = mid.ticks_per_beat
    events = []
    for tr in mid.tracks:
        abs_t = 0
        for msg in tr:
            abs_t += msg.time
            if msg.type in ("note_on", "note_off"):
                events.append((abs_t * spb / tpb, msg))
    events.sort(key=lambda e: e[0])
    active = {}
    notes = []
    for sec, msg in events:
        if msg.type == "note_on" and msg.velocity > 0:
            active[msg.note] = sec
        else:
            start = active.pop(msg.note, None)
            if start is not None and sec - start > 0.03:
                notes.append((start, sec, msg.note))
    notes.sort()
    return notes


def midi_to_hz(m):
    return 440.0 * (2 ** ((m - 69) / 12.0))


def hz_to_name(hz):
    m = int(round(12 * np.log2(hz / 440.0) + 69))
    return f"{NAMES[m % 12]}{(m // 12) - 1}"


def tab_for_midi(midi):
    for string in (1, 2, 3, 4):
        fret = midi - OPEN_MIDI[string]
        if 0 <= fret <= NECK_FRETS:
            return fret, string
    return None


def _grid_score(onsets, bpm, phase, tol=0.030, metric="frac"):
    step = 60.0 / bpm / 4.0
    frac = ((onsets - phase) / step) % 1.0
    dist = np.minimum(frac, 1.0 - frac) * step
    hit = float(np.mean(dist < tol))
    if metric == "frac":
        return hit
    random = min(0.999, 2.0 * tol / step)
    return (hit - random) / max(1e-6, 1.0 - random)


def fit_grid(onsets, bpm_min=88.0, bpm_max=96.0, bpm_step=0.05,
             phase_step=0.005, tol=0.030, metric="frac"):
    """Busca (bpm, fase) que maximiza onsets pegados a la rejilla de 16avos."""
    onsets = np.asarray(sorted(onsets), dtype=float)
    if onsets.size == 0:
        return 0.0, 120.0, 0.0
    best = (-1e9, 0.0, 0.0)
    for bpm in np.arange(bpm_min, bpm_max + 1e-9, bpm_step):
        step = 60.0 / bpm / 4.0
        for phase in np.arange(0, step, phase_step):
            score = _grid_score(onsets, bpm, phase, tol, metric)
            if score > best[0]:
                best = (score, bpm, phase)
    return best  # (score, bpm, phase)


def fit_tempo(onsets, bpm_min=60.0, bpm_max=150.0, bpm_step=0.25,
              phase_step=0.005, tol=0.030):
    """Tempo/fase por onsets, sin depender de librosa.

    Usa un score normalizado por la tasa aleatoria (para no favorecer tempos
    rápidos) y, ante empate cercano, prefiere el tempo MÁS LENTO (la
    fundamental, no su doble).
    """
    onsets = np.asarray(sorted(onsets), dtype=float)
    if onsets.size == 0:
        return 0.0, 120.0, 0.0
    cands = []
    for bpm in np.arange(bpm_min, bpm_max + 1e-9, bpm_step):
        step = 60.0 / bpm / 4.0
        best = (-1e9, 0.0)
        for phase in np.arange(0, step, phase_step):
            s = _grid_score(onsets, bpm, phase, tol, "norm")
            if s > best[0]:
                best = (s, phase)
        cands.append((best[0], bpm, best[1]))
    cands.sort(reverse=True)
    top = cands[0][0]
    near = [c for c in cands if c[0] >= top - 0.04]
    bpm0 = min(c[1] for c in near)
    # Refina ±1 BPM alrededor del elegido
    score, bpm, phase = fit_grid(onsets, max(bpm_min, bpm0 - 1.0),
                                 min(bpm_max, bpm0 + 1.0), 0.02,
                                 phase_step, tol, "norm")
    return score, bpm, phase


def fix_octave_jumps(notes):
    """Corrige flips de octava: si el salto supera la octava, prueba ±12."""
    fixed = []
    prev = None
    n_fix = 0
    for start, end, midi in notes:
        if prev is not None and abs(midi - prev) > 12:
            cands = [(abs(midi - 12 - prev), midi - 12),
                     (abs(midi + 12 - prev), midi + 12)]
            cands.sort()
            if cands[0][0] <= 7:
                midi = cands[0][1]
                n_fix += 1
        fixed.append((start, end, midi))
        prev = midi
    return fixed, n_fix


def derive_chord_segments(notes_q, barlen=BARLEN_DEFAULT,
                          bars_per_chord=BARS_PER_CHORD_DEFAULT):
    """Deriva acordes de las raíces del bajo agrupando `bars_per_chord` compases."""
    seg16 = barlen * 4 * bars_per_chord
    if not notes_q or seg16 <= 0:
        return []
    nseg = max(s for s, _, _ in notes_q) // seg16 + 1
    buckets = [defaultdict(int) for _ in range(nseg)]
    for s16, dur, midi in notes_q:
        buckets[s16 // seg16][midi % 12] += dur

    out = []
    prev = None
    for i, b in enumerate(buckets):
        if not b:
            continue
        root = max(b, key=b.get)
        dur3 = b.get((root + 3) % 12, 0)
        dur4 = b.get((root + 4) % 12, 0)
        minor = (dur3 > dur4) if (dur3 or dur4) else True
        if (root, minor) == prev:
            continue
        out.append((i * seg16, root, minor))
        prev = (root, minor)
    if out:
        first16 = min(s for s, _, _ in notes_q)
        if out[0][0] < first16:
            out[0] = (first16, out[0][1], out[0][2])
    return out


def _add_harmony(meas, root_pc, minor):
    harm = ET.SubElement(meas, "harmony")
    r = ET.SubElement(harm, "root")
    step, alter = HARMONY_ROOT[root_pc % 12]
    ET.SubElement(r, "root-step").text = step
    if alter:
        ET.SubElement(r, "root-alter").text = str(alter)
    ET.SubElement(harm, "kind").text = "minor" if minor else "major"


def build_musicxml(notes_q, bpm, chords=None, barlen=BARLEN_DEFAULT,
                   key_fifths=KEY_FIFTHS_DEFAULT, key_mode=KEY_MODE_DEFAULT,
                   clef_sign=CLEF_SIGN_DEFAULT, clef_line=CLEF_LINE_DEFAULT):
    """notes_q: [(start16, dur16, midi)] → ElementTree MusicXML con tab."""
    bar16 = barlen * 4
    chords = chords or []
    harmony_at = {}
    for s16, root, minor in chords:
        harmony_at.setdefault(s16 // bar16, (root, minor))

    n_measures = (max(s for s, _, _ in notes_q) // bar16 + 1) if notes_q else 1
    by_measure = {}
    for start16, dur16, midi in sorted(notes_q):
        m = start16 // bar16
        dur16 = max(1, min(dur16, (m + 1) * bar16 - start16))
        by_measure.setdefault(m, []).append([start16, dur16, midi])
    for m, evs in by_measure.items():
        evs.sort()
        kept = []
        for s, d, mid in evs:
            if kept and s <= kept[-1][0]:
                continue
            if kept:
                ps, pd, pm = kept[-1]
                kept[-1][1] = max(1, min(pd, s - ps))
            kept.append([s, d, mid])
        by_measure[m] = kept

    root = ET.Element("score-partwise", version="3.1")
    pl = ET.SubElement(root, "part-list")
    sp = ET.SubElement(pl, "score-part", id="P1")
    ET.SubElement(sp, "part-name").text = "Bass"
    part = ET.SubElement(root, "part", id="P1")

    for m in range(n_measures):
        meas = ET.SubElement(part, "measure", number=str(m + 1))
        attr = ET.SubElement(meas, "attributes")
        ET.SubElement(attr, "divisions").text = "4"
        if m == 0:
            key = ET.SubElement(attr, "key")
            ET.SubElement(key, "fifths").text = str(key_fifths)
            ET.SubElement(key, "mode").text = key_mode
        time = ET.SubElement(attr, "time")
        ET.SubElement(time, "beats").text = str(barlen)
        ET.SubElement(time, "beat-type").text = "4"
        if m == 0:
            clef = ET.SubElement(attr, "clef")
            ET.SubElement(clef, "sign").text = clef_sign
            ET.SubElement(clef, "line").text = str(clef_line)
        ET.SubElement(attr, "staves").text = "2"
        if m == 0:
            direction = ET.SubElement(meas, "direction", placement="above")
            dtype = ET.SubElement(direction, "direction-type")
            metro = ET.SubElement(dtype, "metronome")
            ET.SubElement(metro, "beat-unit").text = "quarter"
            ET.SubElement(metro, "per-minute").text = f"{bpm:.1f}"
            ET.SubElement(direction, "sound", tempo=f"{bpm:.1f}")
        if m in harmony_at:
            _add_harmony(meas, *harmony_at[m])
        pos = m * bar16
        for start16, dur16, midi in sorted(by_measure.get(m, [])):
            if start16 > pos:
                _add_rest(meas, start16 - pos)
                pos = start16
            _add_note(meas, dur16, midi)
            pos = start16 + dur16
        if pos < (m + 1) * bar16:
            _add_rest(meas, (m + 1) * bar16 - pos)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return tree


_DUR_UNITS = (
    (16, "whole",   0),
    (12, "half",    1),
    (8,  "half",    0),
    (6,  "quarter", 1),
    (4,  "quarter", 0),
    (3,  "eighth",  1),
    (2,  "eighth",  0),
    (1,  "16th",    0),
)


def _split_dur(dur16):
    """Divide dur16 en valores estándar (16avos, tipo, puntillo)."""
    out, rem = [], max(1, int(dur16))
    for val, typ, dot in _DUR_UNITS:
        while rem >= val:
            out.append((val, typ, dot))
            rem -= val
    if not out:
        out.append((1, "16th", 0))
    return out


def _add_rest(meas, dur16):
    for val, typ, dot in _split_dur(dur16):
        rest = ET.SubElement(meas, "note")
        ET.SubElement(rest, "rest")
        ET.SubElement(rest, "duration").text = str(val)
        ET.SubElement(rest, "staff").text = "2"
        ET.SubElement(rest, "type").text = typ
        if dot:
            ET.SubElement(rest, "dot")


def _add_note(meas, dur16, midi):
    pieces = _split_dur(dur16)
    tab = tab_for_midi(midi)
    last = len(pieces) - 1
    for i, (val, typ, dot) in enumerate(pieces):
        note = ET.SubElement(meas, "note")
        pitch = ET.SubElement(note, "pitch")
        step_letter, alter = PC_STEP_ALTER[midi % 12]
        ET.SubElement(pitch, "step").text = step_letter
        if alter:
            ET.SubElement(pitch, "alter").text = str(alter)
        ET.SubElement(pitch, "octave").text = str(midi // 12 - 1)
        ET.SubElement(note, "duration").text = str(val)
        if last:
            if i < last:
                ET.SubElement(note, "tie", type="start")
            if i > 0:
                ET.SubElement(note, "tie", type="stop")
        ET.SubElement(note, "staff").text = "2"
        ET.SubElement(note, "type").text = typ
        if dot:
            ET.SubElement(note, "dot")
        notations = ET.SubElement(note, "notations")
        if last:
            if i < last:
                ET.SubElement(notations, "tied", type="start")
            if i > 0:
                ET.SubElement(notations, "tied", type="stop")
        tech = ET.SubElement(notations, "technical")
        ET.SubElement(tech, "string").text = str(tab[1])
        ET.SubElement(tech, "fret").text = str(tab[0])


def write_chords_json(path, segments, bpm, lyrics=None, barlen=BARLEN_DEFAULT):
    """Escribe <base>.chords.json con tiempos en segundos de PARTITURA."""
    import json

    def sec_of(s16):
        return round(s16 / 4.0 * 60.0 / bpm, 2)
    chords = []
    for s16, root, minor in segments:
        name = NAMES_ES[root % 12] + ("m" if minor else "")
        chords.append([sec_of(s16), name])
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"chords": chords,
                   "lyrics": [[s, t] for s, t in (lyrics or [])],
                   "barlen": int(barlen)}, f,
                  ensure_ascii=False, indent=1)


def load_existing_lyrics(path):
    import json
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return [(float(s), str(t)) for s, t in d.get("lyrics", [])]
    except Exception:
        return []


def validate_measures(xml_path, barlen=BARLEN_DEFAULT):
    """Validador independiente: cada compás debe sumar barlen*4."""
    bar16 = barlen * 4
    root = _parse_xml(xml_path).getroot()
    bad = []
    for part in root.iter("part"):
        for meas in part.findall("measure"):
            total = 0
            for note in meas.findall("note"):
                d = note.find("duration")
                total += int(d.text) if d is not None else 0
            if total != bar16:
                bad.append((meas.get("number"), total))
    if bad:
        raise ValueError(f"Compases incompletos: {bad[:10]} (total {len(bad)})")
    n = sum(1 for _ in root.iter("measure"))
    return n


def quantize(notes, bpm, phase, barlen=BARLEN_DEFAULT):
    """[(start,end,midi)] segundos → [(start16, dur16, midi)] sin solapes."""
    step = 60.0 / bpm / 4.0
    q = []
    dropped = 0
    for start, end, midi in notes:
        s16 = int(round((start - phase) / step))
        d16 = max(1, int(round((end - start) / step)))
        if s16 < 0:
            continue
        if tab_for_midi(midi) is None:
            dropped += 1
            continue
        q.append((s16, d16, midi))
    q.sort()
    fixed = []
    for i, (s, d, m) in enumerate(q):
        if i + 1 < len(q):
            d = max(1, min(d, q[i + 1][0] - s))
        fixed.append((s, d, m))
    return fixed, dropped


def build_from_notes(notes, out_base, bpm=None, phase=None,
                     barlen=BARLEN_DEFAULT,
                     bars_per_chord=BARS_PER_CHORD_DEFAULT,
                     key_fifths=KEY_FIFTHS_DEFAULT, key_mode=KEY_MODE_DEFAULT,
                     clef_sign=CLEF_SIGN_DEFAULT, clef_line=CLEF_LINE_DEFAULT):
    """Construye <out_base>.musicxml + .chords.json desde notas en segundos.

    Devuelve un dict con las rutas y estadísticas del proceso.
    """
    notes = list(notes)
    if not notes:
        raise ValueError("No hay notas para construir la partitura")
    notes, n_fix = fix_octave_jumps(notes)
    onsets = [s for s, _, _ in notes]
    if bpm is None or bpm <= 0:
        score, bpm, phase = fit_tempo(onsets)
    elif phase is None:
        score, _, phase = fit_grid(onsets, bpm, bpm)
    else:
        score = _grid_score(np.asarray(sorted(onsets), dtype=float),
                            bpm, phase)
    bpm = round(float(bpm), 1)
    q, dropped = quantize(notes, bpm, phase, barlen)
    segments = derive_chord_segments(q, barlen, bars_per_chord)

    # Offset que alinea la partitura con el audio (ver _mp3_sec_of_s16):
    #   mp3(s16) = offset + s16*step - S16*step
    # despejando para que mp3(s16) ~= onset real.
    step = 60.0 / bpm / 4.0
    orig = np.asarray(sorted(t for t, _e, _m in notes), dtype=float)
    diffs = []
    for s16, _d, _m in q:
        t = s16 * step
        j = int(np.argmin(np.abs(orig - t)))
        diffs.append(orig[j] - t)
    suggested_offset = 0.0
    if q and orig.size:
        suggested_offset = q[0][0] * step + float(np.median(diffs))

    tree = build_musicxml(q, bpm, segments, barlen,
                          key_fifths, key_mode, clef_sign, clef_line)
    xml_path = out_base + ".musicxml"
    tree.write(xml_path, encoding="unicode", xml_declaration=True)
    n_meas = validate_measures(xml_path, barlen)

    chords_path = out_base + ".chords.json"
    lyrics = load_existing_lyrics(chords_path)
    write_chords_json(chords_path, segments, bpm, lyrics, barlen)
    return {
        "musicxml": xml_path,
        "chords": chords_path,
        "bpm": bpm,
        "phase": phase,
        "grid_score": score,
        "notes": len(q),
        "dropped": dropped,
        "octave_fixes": n_fix,
        "chords_n": len(segments),
        "measures": n_meas,
        "suggested_offset": round(suggested_offset, 3),
    }
