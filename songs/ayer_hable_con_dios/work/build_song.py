"""Construye la canción para BassKaraoke desde los stems de Demucs.

1. Lee el MIDI transcrito del bajo (basic_pitch) y ajusta (BPM, fase)
   por grid-fit sobre los onsets (rejilla de 16avos).
2. Cuantiza a 16avos, mapea a traste/cuerda (traste más bajo) y escribe
   MusicXML CON tablatura (staff 2) + marca de tempo + compás (BARLEN/4)
   + símbolos de acorde <harmony> derivados de las raíces del bajo.
3. Deriva los acordes del propio bajo y escribe <base>.chords.json
   (mismo origen que la partitura — sin estimación por chroma).
4. Mezcla drums+other+vocals (sin bajo, estilo karaoke) a MP3 con ffmpeg.

Uso: python build_song.py   (desde la carpeta de la canción)

Variables de entorno:
  BARLEN          tiempos por compás (3 = 3/4 corridos, 4 = 4/4). Def 3.
  BARS_PER_CHORD  compases por acorde. Def 2 (raíz + quinta del corrido).
  SKIP_MP3        =1 para no re-mezclar el MP3 (audio intacto).
"""
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict

import mido
import numpy as np
import soundfile as sf

# ── Métrica y armonía ─────────────────────────────────────────────────────────
BARLEN = int(os.environ.get("BARLEN", "3"))                 # 3/4 por defecto
BAR16 = BARLEN * 4                                          # 16avos por compás
BARS_PER_CHORD = int(os.environ.get("BARS_PER_CHORD", "2"))
SKIP_MP3 = os.environ.get("SKIP_MP3") == "1"
# Armadura/clave para la partitura (Fm = 4 bemoles; clave de Fa).
KEY_FIFTHS = int(os.environ.get("KEY_FIFTHS", "-4"))
KEY_MODE = os.environ.get("KEY_MODE", "minor")
CLEF_SIGN = os.environ.get("CLEF_SIGN", "F")
CLEF_LINE = int(os.environ.get("CLEF_LINE", "4"))



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
# Nombres en español (mismos que la app / chords.py)
NAMES_ES = ["Do", "Do#", "Re", "Mib", "Mi", "Fa",
            "Fa#", "Sol", "Lab", "La", "Sib", "Si"]
# (step, alter) para <harmony> (con bemoles en las alteradas)
HARMONY_ROOT = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1),
                4: ("E", 0), 5: ("F", 0), 6: ("F", 1), 7: ("G", 0),
                8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
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


def derive_chord_segments(notes_q, barlen=BARLEN, bars_per_chord=BARS_PER_CHORD):
    """Deriva acordes de las raíces del BAJO (no estimación por audio).

    Agrupa cada `bars_per_chord` compases y toma la clase de tono con más
    duración como raíz. La calidad (m/maj) sale de la 3ª presente en el
    bajo (menor por defecto si no hay 3ª, típico del corrido). Devuelve
    [(start16, root_pc, minor)] fusionando tramos consecutivos iguales.
    """
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
    # El primer acorde empieza donde ENTRA el bajo (no antes): así la barra de
    # acordes queda alineada con la primera nota del bajo en la tab/partitura.
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


def build_musicxml(notes_q, bpm, chords=None):
    """notes_q: [(start16, dur16, midi)] → MusicXML con tab (divisions=4).

    Cada compás suma EXACTAMENTE BAR16 (BARLEN tiempos). `chords` es la
    lista de (start16, root_pc, minor) de derive_chord_segments; se inyecta
    un <harmony> al inicio de cada compás donde cambia el acorde.
    """
    chords = chords or []
    harmony_at = {}
    for s16, root, minor in chords:
        harmony_at.setdefault(s16 // BAR16, (root, minor))

    n_measures = (max(s for s, _, _ in notes_q) // BAR16 + 1) if notes_q else 1
    by_measure = {}
    for start16, dur16, midi in sorted(notes_q):
        m = start16 // BAR16
        # Recorta al final del compás (sin ligaduras: se rearticula)
        dur16 = max(1, min(dur16, (m + 1) * BAR16 - start16))
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
        if m == 0:
            key = ET.SubElement(attr, "key")
            ET.SubElement(key, "fifths").text = str(KEY_FIFTHS)
            ET.SubElement(key, "mode").text = KEY_MODE
        time = ET.SubElement(attr, "time")
        ET.SubElement(time, "beats").text = str(BARLEN)
        ET.SubElement(time, "beat-type").text = "4"
        if m == 0:
            clef = ET.SubElement(attr, "clef")
            ET.SubElement(clef, "sign").text = CLEF_SIGN
            ET.SubElement(clef, "line").text = str(CLEF_LINE)
        ET.SubElement(attr, "staves").text = "2"
        if m == 0:
            direction = ET.SubElement(meas, "direction",
                                      placement="above")
            dtype = ET.SubElement(direction, "direction-type")
            metro = ET.SubElement(dtype, "metronome")
            ET.SubElement(metro, "beat-unit").text = "quarter"
            ET.SubElement(metro, "per-minute").text = f"{bpm:.1f}"
            ET.SubElement(direction, "sound", tempo=f"{bpm:.1f}")
        if m in harmony_at:
            _add_harmony(meas, *harmony_at[m])
        pos = m * BAR16
        for start16, dur16, midi in sorted(by_measure.get(m, [])):
            if start16 > pos:
                _add_rest(meas, start16 - pos)
                pos = start16
            _add_note(meas, dur16, midi)
            pos = start16 + dur16
        if pos < (m + 1) * BAR16:
            _add_rest(meas, (m + 1) * BAR16 - pos)

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


def write_chords_json(path, segments, bpm, lyrics=None, barlen=BARLEN):
    """Escribe <base>.chords.json desde los segmentos derivados del bajo.

    Los tiempos quedan en SEGUNDOS DE PARTITURA (mismo reloj que el audio
    de la app: _song_seconds), no en segundos de MP3."""
    import json
    sec_of = lambda s16: round(s16 / 4.0 * 60.0 / bpm, 2)
    chords = []
    for s16, root, minor in segments:
        name = NAMES_ES[root % 12] + ("m" if minor else "")
        chords.append([sec_of(s16), name])
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"chords": chords,
                   "lyrics": [[s, t] for s, t in (lyrics or [])],
                   "barlen": int(barlen)}, f,
                  ensure_ascii=False, indent=1)


def _load_existing_lyrics(path):
    import json
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return [(float(s), str(t)) for s, t in d.get("lyrics", [])]
    except Exception:
        return []


def _validate_measures(xml_path):
    """Validador independiente: cada compás debe sumar BAR16 (divisions=4).
    Replica la regla que quejaba el editor. Falla si no."""
    root = ET.parse(xml_path).getroot()
    bad = []
    for part in root.iter("part"):
        for meas in part.findall("measure"):
            total = 0
            for note in meas.findall("note"):
                d = note.find("duration")
                total += int(d.text) if d is not None else 0
            if total != BAR16:
                bad.append((meas.get("number"), total))
    if bad:
        raise SystemExit(f"COMPASES MAL: {bad[:10]} (total {len(bad)})")
    n = sum(1 for _ in root.iter("measure"))
    print(f"validador: {n} compases × {BAR16} ({BARLEN}/4) OK")


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

    # Acordes derivados del bajo (mismo origen que la partitura)
    segments = derive_chord_segments(fixed)
    print(f"acordes derivados del bajo: {len(segments)}")

    tree = build_musicxml(fixed, bpm, segments)
    xml_path = f"{BASE}.musicxml"
    tree.write(xml_path, encoding="unicode",
               xml_declaration=True)
    print("MusicXML:", xml_path)
    _validate_measures(xml_path)

    # chords.json (preservando letra ya alineada si existe)
    chords_path = f"{BASE}.chords.json"
    lyrics = _load_existing_lyrics(chords_path)
    write_chords_json(chords_path, segments, bpm, lyrics)
    print(f"chords.json: {chords_path}  ({len(segments)} acordes, "
          f"{len(lyrics)} líneas, {BARLEN}/4)")

    if SKIP_MP3:
        print("MP3: omitido (SKIP_MP3=1)")
        return

    # Mezcla sin bajo → WAV (numpy) → MP3 (ffmpeg solo transcodifica,
    # así vale cualquier ffmpeg con libmp3lame, sin filtros modernos)
    tracks = []
    sr = None
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
