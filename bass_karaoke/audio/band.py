"""Banda de acompañamiento al estilo jjSwing de JJazzLab.

Genera batería, piano y guitarra a partir del cifrado de la canción, usando
los datos reales del ritmo ``jjSwing`` que instala JJazzLab:

* ``drums44DB.mid`` — frases de batería (4 compases + fills de 1 compás) con
  swing ya grabado; estilo automático por variación (BRUSHES/HI_HAT/RIDE).
* ``psBase.yjz``   — frases de piano y guitarra por variación y acorde
  origen; cada nota se reajusta por grados al acorde que suena.

Si JJazzLab no está instalado (o no se encuentran los datos) el módulo
devuelve ``None`` y la app sigue funcionando sin banda.
"""
from __future__ import annotations

import io
import logging
import math
import os
import re
import zipfile
from collections import defaultdict

import numpy as np

from ..config import SAMPLERATE
from .bass_track import find_soundfont

log = logging.getLogger(__name__)

JAR_NAME = "org-jjazzlab-plugins-jjswing.jar"
DATA_MEMBERS = {
    "yjz":   "org/jjazz/jjswing/api/psBase.yjz",
    "drums": "org/jjazz/jjswing/drums/db/drums44DB.mid",
}

DRUM_BANK, DRUM_PRESET = 128, 40          # GM2: Brush Kit
PIANO_PRESET, GUITAR_PRESET = 0, 26        # Grand Piano / Jazz Guitar
STEM_TARGET_RMS = {"drums": 0.045, "piano": 0.050, "guitar": 0.040}
MASTER_PEAK = 0.72

DEFAULT_VARIATIONS = ("Main A-1", "Main B-1", "Main C-1", "Main D-1")
BLOCK_BARS = 8

STYLE_BY_VARIATION = {
    "Main A-1": "BRUSHES_1", "Main A-2": "BRUSHES_2",
    "Main B-1": "HI_HAT_1", "Main B-2": "HI_HAT_2",
    "Main C-1": "RIDE_1", "Main C-2": "RIDE_2",
    "Main D-1": "RIDE_3", "Main D-2": "RIDE_3",
    "Main E-1": "RIDE_4", "Main E-2": "DOUBLE_1",
    "Intro A-1": "INTRO", "Ending A-1": "ENDING",
}
BRUSH_MAP = {25: 38, 26: 38}        # XG brush tap/slap -> GM brush slap
VEL_BOOST = {27: 15, 28: 15, 42: 40, 44: 40, 46: 40, 49: 30, 51: 40, 53: 30}

_ES_ROOTS = ("Sol", "Do", "Re", "Mi", "Fa", "La", "Si")
_ES_PC = {"Do": 0, "Re": 2, "Mi": 4, "Fa": 5, "Sol": 7, "La": 9, "Si": 11}
_EN_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_YJZ_TRACK_RE = re.compile(r"(.+?)-\[([^,]+),([^,]+),ch(\d+)\]")

_CACHE = {}


# ── localización de los datos de JJazzLab ───────────────────────────────────
def _jar_candidates():
    env = os.environ.get("BASS_KARAOKE_JJAZZLAB") or os.environ.get("JJAZZLAB_HOME")
    if env:
        if env.lower().endswith(".jar"):
            yield env
        else:
            yield os.path.join(env, "jjazzlab", "modules", JAR_NAME)
            yield os.path.join(env, "modules", JAR_NAME)
            yield os.path.join(env, JAR_NAME)
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        yield os.path.join(base, "JJazzLab", "jjazzlab", "modules", JAR_NAME)


def _read_member(name: str):
    for jar in _jar_candidates():
        if not jar or not os.path.isfile(jar):
            continue
        try:
            with zipfile.ZipFile(jar) as z:
                return z.read(DATA_MEMBERS[name])
        except (KeyError, zipfile.BadZipFile, OSError):
            continue
    return None


def _load_yjz(data: bytes):
    import mido
    mid = mido.MidiFile(file=io.BytesIO(data))
    tpb = mid.ticks_per_beat
    out = {}
    for track in mid.tracks:
        m = _YJZ_TRACK_RE.match(track.name)
        if not m:
            continue
        variation, part, src = m.group(1), m.group(2), m.group(3)
        ticks, held, notes = 0, {}, []
        for msg in track:
            ticks += msg.time
            if msg.type == "note_on" and msg.velocity:
                held[msg.note] = (ticks, msg.velocity)
            elif msg.type in ("note_off", "note_on"):
                start = held.pop(msg.note, None)
                if start is not None:
                    notes.append((start[0] / tpb, (ticks - start[0]) / tpb,
                                  msg.note, start[1]))
        notes.sort()
        out.setdefault(variation, {}).setdefault(part, {})[src] = notes
    return out, tpb


def _load_drums(data: bytes):
    import mido
    mid = mido.MidiFile(file=io.BytesIO(data))
    ticks, markers = 0, []
    for msg in mid.tracks[0]:
        ticks += msg.time
        if msg.type == "marker":
            markers.append((ticks, msg.text))
    ticks, notes = 0, []
    for msg in mid.tracks[1]:
        ticks += msg.time
        if msg.type == "note_on" and msg.velocity:
            notes.append((ticks, msg.note, msg.velocity))

    db = defaultdict(lambda: {"std": [], "fill": []})
    style, kind = None, "std"
    for i in range(len(markers) - 1):
        t0, text = markers[i]
        if text.startswith("_"):
            style, kind = text[1:].upper(), "std"
        elif text.lower().startswith("#fill"):
            kind = "fill"
        t1 = markers[i + 1][0]
        if style and style != "END":
            db[style][kind].append(
                [(t - t0, n, v) for (t, n, v) in notes if t0 <= t < t1])
    return db, mid.ticks_per_beat


def _data():
    if "data" in _CACHE:
        return _CACHE["data"]
    yjz_raw = _read_member("yjz")
    drums_raw = _read_member("drums")
    if not yjz_raw or not drums_raw:
        _CACHE["data"] = None
        return None
    try:
        yjz, yjz_tpb = _load_yjz(yjz_raw)
        drums, drums_tpb = _load_drums(drums_raw)
    except Exception as exc:
        log.warning(f"[Banda] no puedo leer los datos de JJazzLab: {exc}")
        _CACHE["data"] = None
        return None
    _CACHE["data"] = (yjz, yjz_tpb, drums, drums_tpb)
    return _CACHE["data"]


def midi_available() -> bool:
    """True si hay SoundFont y mido para renderizar un ``.mid`` externo."""
    if os.environ.get("BASS_KARAOKE_NO_BAND"):
        return False
    try:
        import mido  # noqa: F401
    except Exception:
        return False
    return bool(find_soundfont())


def available() -> bool:
    """True si están los datos de jjSwing y el SoundFont para renderizar."""
    return _data() is not None and midi_available()


def source_name() -> str:
    for jar in _jar_candidates():
        if jar and os.path.isfile(jar):
            return jar
    return ""


# ── armonía ─────────────────────────────────────────────────────────────────
def _quality_tones(quality: str):
    q = (quality or "").strip()
    low = q.lower()
    has7 = "7" in q
    ninth = any(tok in q for tok in ("9", "11", "13"))
    sixth = "6" in q
    if q.startswith("maj") or q.startswith("M") or q.startswith("Δ"):
        third, seventh = 4, 11
    elif low.startswith("m"):
        third = 3
        seventh = 10 if has7 or ninth else None
    elif "sus" in low:
        third = 5
        seventh = 10 if has7 or ninth else None
    else:
        third = 4
        seventh = 10 if has7 or ninth else None
    if sixth and not has7:
        seventh = None
    if "b5" in low or "dim" in low or "ø" in q:
        fifth = 6
    elif "#5" in low or "+" in q or "aug" in low:
        fifth = 8
    elif third == 5:
        fifth = 7
    else:
        fifth = 7
    tones = [0, third, fifth]
    if seventh is not None:
        tones.append(seventh)
    elif sixth:
        tones.append(9)
    if ("9" in q or "13" in q) and 2 not in tones:
        tones.append(2)
    return tones


def _split_chord(name: str):
    """``'Rem7'`` -> ``(2, 'm7')``; ``(None, '')`` si no se reconoce la raíz."""
    text = (name or "").strip()
    if not text:
        return None, ""
    root_pc = None
    rest = ""
    for word in _ES_ROOTS:
        if text.startswith(word):
            root_pc, rest = _ES_PC[word], text[len(word):]
            break
    if root_pc is None:
        m = re.match(r"([A-G])([#b]*)", text)
        if not m:
            return None, ""
        root_pc = _EN_PC[m.group(1)]
        root_pc = (root_pc + m.group(2).count("#") - m.group(2).count("b")) % 12
        rest = text[m.end():]
    acc = 0
    while rest[:1] in ("#", "b"):
        acc += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    root_pc = (root_pc + acc) % 12
    if "/" in rest:
        rest = rest.split("/", 1)[0]
    return root_pc, rest


def parse_chord(name: str):
    """``'Rem7'`` / ``'Dm7'`` -> ``(root_pc, [pc, ...])``; ``None`` si no se reconoce."""
    root_pc, rest = _split_chord(name)
    if root_pc is None:
        return None
    tones = [(root_pc + d) % 12 for d in _quality_tones(rest)]
    return root_pc, tones


def _fit_pitch(pitch: int, src_pcs, dst_pcs):
    pc = pitch % 12
    if not dst_pcs:
        return pitch
    idx = src_pcs.index(pc) if pc in src_pcs else None
    if idx is None:
        delta = (pc - src_pcs[0]) % 12
        target = (dst_pcs[0] + delta) % 12
    else:
        target = dst_pcs[min(idx, len(dst_pcs) - 1)]
    up = (target - pitch) % 12
    return pitch + up - (12 if up > 6 else 0)


# ── generación de eventos ───────────────────────────────────────────────────
def _drum_note(note: int, vel: int):
    note = BRUSH_MAP.get(note, note)
    return note, int(min(127, vel + VEL_BOOST.get(note, 0)))


def _drum_fill(fills, block_index):
    if not fills:
        return []
    return fills[block_index % len(fills)]


def build_events(chords, bpm: float, barlen: float, total_sec: float):
    """Eventos por instrumento a partir del cifrado ``[(sec, 'Chord')]``.

    Devuelve ``{"drums": [(t, dur, nota, vel)], "piano": [...],
    "guitar": [...]}`` en segundos (tempo constante del cifrado).
    """
    data = _data()
    if data is None or not chords or bpm <= 0:
        return None
    yjz, _yjz_tpb, drums_db, drums_tpb = data

    bar_sec = float(barlen) * 60.0 / float(bpm)
    n_bars = max(1, int(math.ceil(total_sec / bar_sec)))
    parsed = []
    for i, (sec, name) in enumerate(chords):
        info = parse_chord(name)
        end = float(chords[i + 1][0]) if i + 1 < len(chords) else total_sec
        if info is not None and end > sec:
            parsed.append((float(sec), max(0.1, end - float(sec)), info))

    def chord_at(t):
        for start, dur, info in parsed:
            if start <= t < start + dur:
                return info
        return None

    events = {"drums": [], "piano": [], "guitar": []}
    for block in range((n_bars + BLOCK_BARS - 1) // BLOCK_BARS):
        variation = DEFAULT_VARIATIONS[block % len(DEFAULT_VARIATIONS)]
        block_start = block * BLOCK_BARS * bar_sec
        block_len = min(BLOCK_BARS * bar_sec, total_sec - block_start)
        if block_len <= 0.01:
            continue

        style = STYLE_BY_VARIATION.get(variation, "BRUSHES_2")
        std = drums_db.get(style, {}).get("std") or []
        if std:
            step = 4 * bar_sec
            shift = 0.0
            k = 0
            while shift < block_len - 1e-6:
                seg = std[k % len(std)]
                for tick, note, vel in seg:
                    t = block_start + shift + tick / drums_tpb * (60.0 / bpm)
                    if t < block_start + block_len:
                        events["drums"].append((t, 0.12) + _drum_note(note, vel))
                shift += step
                k += 1
            fill = _drum_fill(drums_db.get(style, {}).get("fill"), block)
            if fill and block_len >= bar_sec:
                fill_start = block_start + block_len - bar_sec
                for tick, note, vel in fill:
                    t = fill_start + tick / drums_tpb * (60.0 / bpm)
                    if t < block_start + block_len:
                        events["drums"].append((t, 0.12) + _drum_note(note, vel))

        for part, key, src in (("Piano_Chord1", "piano", "CM7"),
                               ("Guit_Chord2", "guitar", "CM7")):
            phrases = yjz.get(variation, {}).get(part) or {}
            notes = phrases.get(src) or (next(iter(phrases.values()))
                                         if phrases else None)
            if not notes:
                continue
            src_pcs = [(0 + d) % 12 for d in _quality_tones("M7")]
            for pos, dur, pitch, vel in notes:
                if not (0 <= pos < BLOCK_BARS * barlen):
                    continue
                t = block_start + pos * 60.0 / bpm
                if t >= block_start + block_len:
                    continue
                info = chord_at(t)
                if info is None:
                    continue
                fitted = _fit_pitch(pitch, src_pcs, info[1])
                if 36 <= fitted <= 96:
                    events[key].append((t, min(dur * 60.0 / bpm, 4.0), fitted, vel))
    return events


BASS_LO, BASS_HI = 28, 58


def _place_bass(pitch: int, prev=None) -> int:
    """Mete ``pitch`` en el registro del bajo sin romper el contorno."""
    while pitch < BASS_LO:
        pitch += 12
    while pitch > BASS_HI:
        pitch -= 12
    return pitch


def _bass_source(phrases, quality: str):
    """Elige la frase de bajo según la calidad del acorde (CM7/Cm7/CM7#11)."""
    low = (quality or "").lower()
    if "Cm7" in phrases and _quality_tones(quality or "")[1] == 3:
        return phrases["Cm7"]
    if "CM7#11" in phrases and "#11" in low:
        return phrases["CM7#11"]
    return phrases.get("CM7") or next(iter(phrases.values()))


def bass_events(chords, bpm: float, barlen: float, total_sec: float,
                sections=None):
    """Línea de bajo con las frases ``Bass`` de jjSwing (``psBase.yjz``).

    ``sections`` = ``[(start_bar, nb_bars, variation)]``; sin él se ciclan
    Main A-1/B-1/C-1/D-1 cada 8 compases. La frase se transporta por raíz
    (conserva las aproximaciones cromáticas) y se coloca en el registro del
    bajo. Devuelve ``[(t, dur, nota, vel)]`` en segundos o ``None``.
    """
    data = _data()
    if data is None or not chords or bpm <= 0:
        return None
    yjz = data[0]
    bar_sec = float(barlen) * 60.0 / float(bpm)
    total_bars = max(1, int(round(total_sec / bar_sec)))

    parsed = []
    for i, (sec, name) in enumerate(chords):
        info = parse_chord(name)
        end = float(chords[i + 1][0]) if i + 1 < len(chords) else total_sec
        if info is not None and end > sec:
            parsed.append((float(sec), max(0.1, end - float(sec)), info,
                           _split_chord(name)[1]))
    if not parsed:
        return None

    def chord_at(t):
        for start, dur, info, quality in parsed:
            if start <= t < start + dur:
                return info, quality
        return None, ""

    blocks = []
    if sections:
        for start_bar, nb, variation in sections:
            nb = max(0, int(nb))
            for k in range(0, nb, BLOCK_BARS):
                blocks.append((int(start_bar) + k, min(BLOCK_BARS, nb - k),
                               variation or "", k // BLOCK_BARS))
    else:
        for k in range(0, total_bars, BLOCK_BARS):
            n = k // BLOCK_BARS
            blocks.append((k, min(BLOCK_BARS, total_bars - k),
                           DEFAULT_VARIATIONS[n % len(DEFAULT_VARIATIONS)],
                           n % 3))

    out, prev = [], None
    for start_bar, nb, variation, index in blocks:
        if not variation:
            variation = DEFAULT_VARIATIONS[index % len(DEFAULT_VARIATIONS)]
        phrases = yjz.get(variation, {}).get("Bass") or {}
        if not phrases:
            continue
        block_start = start_bar * bar_sec
        block_end = min(total_sec, (start_bar + nb) * bar_sec)
        if block_end - block_start <= 0.01:
            continue
        _info0, quality0 = chord_at(block_start)
        notes = _bass_source(phrases, quality0)
        span = BLOCK_BARS * barlen
        last_pos = max((n[0] for n in notes), default=0.0)
        count = max(1, int(math.ceil((last_pos + 1e-6) / span)))
        phrase = index % count
        lo, hi = phrase * span, (phrase + 1) * span
        for pos, dur, pitch, vel in notes:
            if not (lo <= pos < hi):
                continue
            t = block_start + (pos - lo) * 60.0 / bpm
            if t >= block_end - 1e-6:
                continue
            info, _quality = chord_at(t)
            if info is None:
                continue
            shift = ((info[0] + 6) % 12) - 6
            placed = _place_bass(pitch + shift, prev)
            prev = placed
            out.append((t, min(dur * 60.0 / bpm, block_end - t), placed, vel))
    out.sort()
    return out or None


# ── render ──────────────────────────────────────────────────────────────────
def _render_channel(synth, channel, events, n_frames, sr=SAMPLERATE):
    """Toca ``events`` en un synth ya cargado y devuelve (frames, 2) float32."""
    out = np.zeros((n_frames, 2), dtype=np.float32)
    sched = []
    for t, dur, midi, vel in events:
        a = int(round(float(t) * sr))
        b = int(round((float(t) + float(dur)) * sr))
        sched.append((a, 1, int(midi), int(vel)))
        sched.append((max(a + 1, b), 0, int(midi), 0))
    sched.sort(key=lambda e: (e[0], e[1]))

    pos, i, chunk = 0, 0, 1024
    while pos < n_frames:
        while i < len(sched) and sched[i][0] <= pos:
            _, kind, midi, vel = sched[i]
            if kind:
                synth.noteon(channel, midi, vel)
            else:
                synth.noteoff(channel, midi)
            i += 1
        nxt = sched[i][0] if i < len(sched) else n_frames
        n = min(max(1, nxt - pos), chunk, n_frames - pos)
        buf = np.frombuffer(synth.generate_simple(n), dtype=np.float32)
        buf = buf.reshape(-1, 2)[:n]
        out[pos:pos + len(buf)] = buf
        pos += max(1, len(buf))
    return out


def _render_stem(events, total_sec, sf2, preset, bank, channel, gain_db,
                 sr=SAMPLERATE):
    import tinysoundfont
    n_frames = max(1, int(math.ceil(total_sec * sr)))
    synth = tinysoundfont.Synth(gain=gain_db, samplerate=sr)
    sfid = synth.sfload(sf2)
    synth.program_select(channel, sfid, bank, preset)
    return _render_channel(synth, channel, events, n_frames, sr)


# ── MIDI externo (<canción>.mid junto al MusicXML) ──────────────────────────
def _sec_converter(mid):
    tempos = []
    for track in mid.tracks:
        ticks = 0
        for msg in track:
            ticks += msg.time
            if msg.type == "set_tempo":
                tempos.append((ticks, msg.tempo))
    tempos.sort()

    def to_sec(tick):
        sec, last, cur = 0.0, 0, 500000
        for at, tempo in tempos:
            if tick <= at:
                break
            sec += (at - last) * (cur / 1e6) / mid.ticks_per_beat
            last, cur = at, tempo
        return sec + (tick - last) * (cur / 1e6) / mid.ticks_per_beat

    return to_sec


def _midi_channels(path):
    """``{canal: {bank, preset, vol, notes:[(t, dur, nota, vel)]}}`` en segundos."""
    import mido
    mid = mido.MidiFile(path)
    to_sec = _sec_converter(mid)
    chans, held = {}, {}
    for track in mid.tracks:
        ticks = 0
        for msg in track:
            ticks += msg.time
            kind = msg.type
            if kind == "program_change":
                chans.setdefault(msg.channel, {"bank": 0, "preset": 0,
                                               "vol": 100, "notes": []}
                                 )["preset"] = msg.program
            elif kind == "control_change":
                info = chans.setdefault(msg.channel, {"bank": 0, "preset": 0,
                                                      "vol": 100, "notes": []})
                if msg.control == 0:
                    info["bank"] = (info["bank"] & 0x7F) | (msg.value << 7)
                elif msg.control == 32:
                    info["bank"] = (info["bank"] & ~0x7F) | (msg.value & 0x7F)
                elif msg.control == 7:
                    info["vol"] = msg.value
            elif kind == "note_on" and msg.velocity:
                held[(msg.channel, msg.note)] = (ticks, msg.velocity)
            elif kind in ("note_off", "note_on"):
                start = held.pop((msg.channel, msg.note), None)
                if start is None:
                    continue
                info = chans.setdefault(msg.channel, {"bank": 0, "preset": 0,
                                                      "vol": 100, "notes": []})
                t0, vel = start
                info["notes"].append((to_sec(t0), to_sec(ticks) - to_sec(t0),
                                      int(msg.note), int(vel)))
    return {ch: info for ch, info in chans.items() if info["notes"]}


def render_midi(path: str, ratio: float = 1.0, total_sec=None,
                sr: int = SAMPLERATE):
    """Renderiza un ``.mid`` completo con el SoundFont (frames, 2) float32."""
    if not path or not os.path.isfile(path) or not midi_available():
        return None
    try:
        chans = _midi_channels(path)
    except Exception as exc:
        log.warning(f"[Banda] no puedo leer el MIDI {path}: {exc}")
        return None
    if not chans:
        return None
    inv = 1.0 if abs(float(ratio) - 1.0) < 1e-6 else 1.0 / max(0.1, float(ratio))
    end = max((t + d for info in chans.values()
               for t, d, _n, _v in info["notes"]), default=0.0)
    dur = float(total_sec) if total_sec else end + 1.0
    total = max(0.5, dur * inv)
    if end * inv > total:
        total = end * inv + 0.5
    sf2 = find_soundfont()
    mix = np.zeros((max(1, int(math.ceil(total * sr))), 2), dtype=np.float32)
    import tinysoundfont
    synth = tinysoundfont.Synth(gain=-6.0, samplerate=sr)
    sfid = synth.sfload(sf2)
    n_frames = len(mix)
    for ch, info in chans.items():
        notes = [(t * inv, d * inv, n, v) for t, d, n, v in info["notes"]]
        if ch == 9:
            bank, preset = DRUM_BANK, info["preset"]
        else:
            bank, preset = info["bank"], info["preset"]
        if bank > 16383 or preset > 127:
            bank, preset = 0, min(127, preset)
        try:
            synth.program_select(ch, sfid, bank, preset)
            stem = _render_channel(synth, ch, notes, n_frames, sr)
        except Exception as exc:
            log.warning(f"[Banda] canal {ch} del MIDI no se pudo renderizar: {exc}")
            continue
        stem *= max(0.0, min(1.5, info["vol"] / 100.0))
        mix[:len(stem)] += stem[:len(mix)]
    mix = np.tanh(mix)
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 1e-6:
        mix *= MASTER_PEAK / peak
    return mix.astype(np.float32, copy=False)


def _scaled_events(chords, bpm: float, barlen: float, total_sec: float,
                   ratio: float):
    """Eventos de la banda con el tempo efectivo ``bpm*ratio`` (varispeed)."""
    inv = 1.0 if abs(float(ratio) - 1.0) < 1e-6 else 1.0 / max(0.1, float(ratio))
    if inv != 1.0:
        chords = [(float(s) * inv, n) for s, n in chords]
    return build_events(chords, float(bpm) / inv, barlen, float(total_sec) * inv)


def render(chords, bpm: float, barlen: float, total_sec: float,
           ratio: float = 1.0, sr: int = SAMPLERATE):
    """Audio (frames, 2) float32 con batería + piano + guitarra, o ``None``."""
    if not available():
        return None
    events = _scaled_events(chords, bpm, barlen, total_sec, ratio)
    if not events or not events["drums"] and not events["piano"]:
        return None
    total = max((e[0] + e[1] for evs in events.values() for e in evs),
                default=0.0) + 1.0

    sf2 = find_soundfont()
    if not sf2:
        return None
    mix = np.zeros((max(1, int(math.ceil(total * sr))), 2), dtype=np.float32)
    import tinysoundfont
    synth = tinysoundfont.Synth(gain=0.0, samplerate=sr)
    sfid = synth.sfload(sf2)
    n_frames = len(mix)
    for key, preset, bank, channel, gain in (
            ("drums", DRUM_PRESET, DRUM_BANK, 9, 0.0),
            ("piano", PIANO_PRESET, 0, 0, 0.0),
            ("guitar", GUITAR_PRESET, 0, 1, 0.0)):
        evs = events[key]
        if not evs:
            continue
        synth.program_select(channel, sfid, bank, preset)
        stem = _render_channel(synth, channel, evs, n_frames, sr)
        rms = float(np.sqrt((stem ** 2).mean()))
        if rms > 1e-6:
            stem *= STEM_TARGET_RMS[key] / rms
        if key == "drums":
            stem = np.tanh(stem)
        mix[:len(stem)] += stem[:len(mix)]
    mix = np.tanh(mix * 1.1)
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 1e-6:
        mix *= MASTER_PEAK / peak
    return mix.astype(np.float32, copy=False)
