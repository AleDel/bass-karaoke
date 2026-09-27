"""Construye la canción para BassKaraoke desde los stems de Demucs.

1. Lee el MIDI transcrito del bajo (basic_pitch) y ajusta (BPM, fase)
   por grid-fit sobre los onsets (rejilla de 16avos).
2. Cuantiza a 16avos, mapea a traste/cuerda (traste más bajo) y escribe
   MusicXML CON tablatura (staff 2) + marca de tempo.
3. Mezcla drums+other+vocals (sin bajo, estilo karaoke) a MP3 con ffmpeg.

Uso: python build_song.py   (desde la carpeta de la canción)
"""
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

import mido
import numpy as np
import soundfile as sf


def _ffmpeg():
    for cand in (r"C:\ffmpeg-2026-03-30-git-e54e117998-full_build\bin\ffmpeg.exe",
                 shutil.which("ffmpeg")):
        if cand and os.path.exists(cand):
            return cand
    return "ffmpeg"

BASE = "ayer_hable_con_dios"
MIDI_PATH = os.path.join("work", "htdemucs-bass_basic_pitch.mid")
STEMS_NOBASS = ["htdemucs-drums.wav", "htdemucs-other.wav", "htdemucs-vocals.wav"]

OPEN_MIDI = {4: 28, 3: 33, 2: 38, 1: 43}
NECK_FRETS = 15
NAMES = ["C", "C#", "D", "D#", "E", "F",
         "F#", "G", "G#", "A", "A#", "B"]
PC_STEP_ALTER = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1),
                 4: ("E", 0), 5: ("F", 0), 6: ("F", 1), 7: ("G", 0),
                 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}


def midi_to_hz(m):
    return 440.0 * (2 ** ((m - 69) / 12.0))


def hz_to_name(hz):
    m = int(round(12 * np.log2(hz / 440.0) + 69))
    return f"{NAMES[m % 12]}{(m // 12) - 1}"


def load_note_events():
    mid = mido.MidiFile(MIDI_PATH)
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
                sec = abs_t * spb / tpb
                events.append((sec, msg))
    events.sort(key=lambda e: e[0])
    # Empareja on/off por tono (monofoniza: conserva el más grave si solapan)
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


def fit_grid(onsets):
    """Busca (bpm, fase) que maximiza onsets pegados a la rejilla de 16avos."""
    onsets = np.asarray(sorted(onsets), dtype=float)
    best = (0, 0.0, 0.0)
    for bpm in np.arange(88.0, 96.01, 0.05):
        step = 60.0 / bpm / 4.0
        for phase in np.arange(0, step, 0.005):
            frac = ((onsets - phase) / step) % 1.0
            dist = np.minimum(frac, 1.0 - frac) * step
            score = float(np.mean(dist < 0.030))
            if score > best[0]:
                best = (score, bpm, phase)
    return best  # (score, bpm, phase)


def fix_octave_jumps(notes):
    """Corrige flips de octava típicos de la transcripción: si el salto
    con la nota anterior supera la octava, prueba ±12 y se queda con el
    salto mínimo cuando este queda en séptima o menos. Devuelve
    (notas, correcciones)."""
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


def tab_for_midi(midi):
    for string in (1, 2, 3, 4):
        fret = midi - OPEN_MIDI[string]
        if 0 <= fret <= NECK_FRETS:
            return fret, string
    return None


def build_musicxml(notes_q, bpm):
    """notes_q: [(start16, dur16, midi)] → MusicXML con tab (divisions=4).

    Cada compás suma EXACTAMENTE 16: las notas se recortan al compás y
    a la siguiente nota, y los huecos se rellenan con silencios.
    """
    n_measures = (max(s for s, _, _ in notes_q) // 16 + 1) if notes_q else 1
    by_measure = {}
    for start16, dur16, midi in sorted(notes_q):
        m = start16 // 16
        # Recorta al final del compás (sin ligaduras: se rearticula)
        dur16 = max(1, min(dur16, (m + 1) * 16 - start16))
        by_measure.setdefault(m, []).append([start16, dur16, midi])
    # Sin solapes dentro del compás: recorta al inicio de la siguiente
    # y elimina las totalmente tapadas.
    for m, evs in by_measure.items():
        evs.sort()
        kept = []
        for s, d, mid in evs:
            if kept and s <= kept[-1][0]:
                continue  # tapada por completo: fuera
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
        ET.SubElement(attr, "staves").text = "2"
        time = ET.SubElement(attr, "time")
        ET.SubElement(time, "beats").text = "4"
        ET.SubElement(time, "beat-type").text = "4"
        if m == 0:
            direction = ET.SubElement(meas, "direction",
                                      placement="above")
            dtype = ET.SubElement(direction, "direction-type")
            metro = ET.SubElement(dtype, "metronome")
            ET.SubElement(metro, "beat-unit").text = "quarter"
            ET.SubElement(metro, "per-minute").text = f"{bpm:.1f}"
            ET.SubElement(direction, "sound", tempo=f"{bpm:.1f}")
        pos = m * 16
        for start16, dur16, midi in sorted(by_measure.get(m, [])):
            if start16 > pos:
                _add_rest(meas, start16 - pos)
                pos = start16
            _add_note(meas, dur16, midi)
            pos = start16 + dur16
        if pos < (m + 1) * 16:
            _add_rest(meas, (m + 1) * 16 - pos)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return tree


def _add_rest(meas, dur16):
    rest = ET.SubElement(meas, "note")
    ET.SubElement(rest, "rest")
    ET.SubElement(rest, "duration").text = str(dur16)
    ET.SubElement(rest, "staff").text = "2"


def _add_note(meas, dur16, midi):
    note = ET.SubElement(meas, "note")
    pitch = ET.SubElement(note, "pitch")
    step_letter, alter = PC_STEP_ALTER[midi % 12]
    ET.SubElement(pitch, "step").text = step_letter
    if alter:
        ET.SubElement(pitch, "alter").text = str(alter)
    ET.SubElement(pitch, "octave").text = str(midi // 12 - 1)
    ET.SubElement(note, "duration").text = str(dur16)
    ET.SubElement(note, "staff").text = "2"
    ET.SubElement(note, "type").text = (
        "16th" if dur16 == 1 else
        "eighth" if dur16 == 2 else "quarter")
    tech = ET.SubElement(ET.SubElement(note, "notations"),
                         "technical")
    tab = tab_for_midi(midi)
    ET.SubElement(tech, "string").text = str(tab[1])
    ET.SubElement(tech, "fret").text = str(tab[0])


def _validate_measures(xml_path):
    """Validador independiente: cada compás debe sumar 16 (divisions=4).
    Replica la regla quejaba el editor (21/16, 9/8, ...). Falla si no."""
    root = ET.parse(xml_path).getroot()
    bad = []
    for part in root.iter("part"):
        for meas in part.findall("measure"):
            total = 0
            for note in meas.findall("note"):
                d = note.find("duration")
                total += int(d.text) if d is not None else 0
            if total != 16:
                bad.append((meas.get("number"), total))
    if bad:
        raise SystemExit(f"COMPASES MAL: {bad[:10]} (total {len(bad)})")
    n = sum(1 for _ in root.iter("measure"))
    print(f"validador: {n} compases × 16 OK")


def main():
    notes = load_note_events()
    print(f"notas MIDI: {len(notes)}")
    notes, n_fix = fix_octave_jumps(notes)
    print(f"flips de octava corregidos: {n_fix}")
    onsets = [s for s, _, _ in notes]
    score, bpm, phase = fit_grid(onsets)
    bpm = round(float(bpm), 1)
    print(f"grid-fit: score={score:.3f} bpm={bpm} fase={phase:.3f}s")
    step = 60.0 / bpm / 4.0

    notes_q = []
    dropped = 0
    for start, end, midi in notes:
        s16 = int(round((start - phase) / step))
        d16 = max(1, int(round((end - start) / step)))
        if s16 < 0:
            continue
        if tab_for_midi(midi) is None:
            dropped += 1
            continue
        notes_q.append((s16, d16, midi))
    # Sin solapes: recorta duraciones que pisan la siguiente
    notes_q.sort()
    fixed = []
    for i, (s, d, m) in enumerate(notes_q):
        if i + 1 < len(notes_q):
            d = max(1, min(d, notes_q[i + 1][0] - s))
        fixed.append((s, d, m))
    print(f"cuantizadas: {len(fixed)}  descartadas fuera de mástil: {dropped}")

    tree = build_musicxml(fixed, bpm)
    xml_path = f"{BASE}.musicxml"
    tree.write(xml_path, encoding="unicode",
               xml_declaration=True)
    print("MusicXML:", xml_path)
    _validate_measures(xml_path)

    # Mezcla sin bajo → WAV (numpy) → MP3 (ffmpeg solo transcodifica,
    # así vale cualquier ffmpeg con libmp3lame, sin filtros modernos)
    mix = None
    sr = None
    tracks = []
    for s in STEMS_NOBASS:
        y, sr = sf.read(s, dtype="float32", always_2d=True)
        tracks.append(y)
    n = min(len(t) for t in tracks)
    mix = sum(t[:n] for t in tracks)
    peak = float(np.abs(mix).max())
    if peak > 0:
        mix = mix / peak * 0.95
    tmp_wav = "_nobass_mix.wav"
    sf.write(tmp_wav, mix, sr, subtype="PCM_16")
    mp3_path = f"{BASE}.mp3"
    subprocess.run([_ffmpeg(), "-y", "-i", tmp_wav,
                    "-codec:a", "libmp3lame", "-q:a", "3", mp3_path],
                   check=True, capture_output=True)
    os.remove(tmp_wav)
    print("MP3:", mp3_path)


if __name__ == "__main__":
    main()
