"""
Acordes y letra sincronizada para el modo karaoke — lógica pura.

- `estimate_chords`: chroma por beat + plantillas mayor/menor (estilo
  Chordino) con suavizado y fusión. Devuelve [(start_sec, nombre)].
- `map_lyrics`: segmenta la voz (stem Demucs) por energía y reparte las
  líneas de letra.txt en orden. Devuelve [(start_sec, texto)].
- El JSON por canción (`<base>.chords.json`) guarda ambos; la app lo
  carga sin coste en tiempo real (J para mostrar/ocultar).
"""
import json
import os

import numpy as np

NAMES_ES = ["Do", "Do#", "Re", "Mib", "Mi", "Fa",
            "Fa#", "Sol", "Lab", "La", "Sib", "Si"]

_MAJOR = [0, 4, 7]
_MINOR = [0, 3, 7]


def _templates():
    majors = np.zeros((12, 12))
    minors = np.zeros((12, 12))
    for r in range(12):
        majors[r, [(r + i) % 12 for i in _MAJOR]] = 1.0
        minors[r, [(r + i) % 12 for i in _MINOR]] = 1.0
    return majors, minors


def chord_name(root_pc: int, minor: bool) -> str:
    return f"{NAMES_ES[root_pc % 12]}{'m' if minor else ''}"


def estimate_chords(audio_path: str, bpm_hint: float = 0.0,
                    sr: int = 22050):
    """Estima un acorde por beat. Devuelve [(start_sec, nombre)]."""
    import librosa
    y, _ = librosa.load(audio_path, sr=sr, mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    beats = np.asarray(sorted(float(b) for b in beats))
    if len(beats) < 4 and bpm_hint > 0:
        step = 60.0 / bpm_hint
        dur = len(y) / sr
        beats = np.arange(0, dur, step)
    if len(beats) < 2:
        return []
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    times = librosa.frames_to_time(np.arange(chroma.shape[1]),
                                   sr=sr, hop_length=512)
    majors, minors = _templates()
    per_beat = []
    for i in range(len(beats)):
        lo, hi = beats[i], beats[i + 1] if i + 1 < len(beats) else beats[i] + 1.0
        sel = (times >= lo) & (times < hi)
        if not np.any(sel):
            per_beat.append(per_beat[-1] if per_beat else (0, False))
            continue
        c = chroma[:, sel].mean(axis=1)
        n = float(np.linalg.norm(c))
        c = c / n if n > 1e-9 else c
        smaj = majors @ c
        smin = minors @ c
        bi = int(np.argmax(np.concatenate([smaj, smin])))
        per_beat.append((bi % 12, bi >= 12))
    # Suavizado: cada beat mira a sus vecinos (voto mayoritario)
    sm = []
    for i, (r, m) in enumerate(per_beat):
        votes = [per_beat[max(0, i - 1)], (r, m),
                 per_beat[min(len(per_beat) - 1, i + 1)]]
        sm.append(sorted(set(votes), key=votes.count)[-1])
    # Fusión de rachas + absorción de rachas de 1 beat
    runs = []
    for v in sm:
        if runs and runs[-1][0] == v:
            runs[-1][1] += 1
        else:
            runs.append([v, 1])
    out = []
    i = 0
    while i < len(runs):
        v, n = runs[i]
        if n < 2 and len(runs) > 1:
            # Absorbe en el vecino más largo
            if i == 0:
                runs[1][1] += n
            else:
                runs[i - 1][1] += n
                # El inicio ya quedó registrado; salta
            i += 1
            continue
        out.append((v, n))
        i += 1
    res = []
    b = 0
    for (r, m), n in out:
        res.append((round(float(beats[min(b, len(beats) - 1)]), 2),
                    chord_name(r, m)))
        b += n
    return res


def vocal_segments(vocals_path: str, sr: int = 22050, min_seg: float = 1.0,
                   min_gap: float = 0.4, thresh_ratio: float = 0.15):
    """Segmentos con voz [(start_sec, end_sec)] por energía."""
    import librosa
    y, _ = librosa.load(vocals_path, sr=sr, mono=True)
    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=2048,
                              hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr,
                                   hop_length=hop)
    thr = float(rms.max()) * thresh_ratio
    mask = rms > thr
    segs = []
    start = None
    for t, on in zip(times, mask, strict=False):
        if on and start is None:
            start = float(t)
        elif not on and start is not None:
            if float(t) - start >= min_seg:
                segs.append((start, float(t)))
            start = None
    if start is not None:
        segs.append((start, float(times[-1])))
    # Fusiona huecos cortos
    merged = []
    for s, e in segs:
        if merged and s - merged[-1][1] < min_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(round(s, 2), round(e, 2)) for s, e in merged]


def map_lyrics(segments, lines):
    """Reparte líneas en segmentos por orden. Devuelve [(start_sec, texto)]."""
    lines = [ln.strip() for ln in lines if ln.strip()]
    if not lines:
        return []
    if not segments:
        return [(0.0, lines[0])]
    S, L = len(segments), len(lines)
    out = []
    for i, ln in enumerate(lines):
        j = round(i * (S - 1) / max(1, L - 1)) if L > 1 else 0
        out.append((segments[min(j, S - 1)][0], ln))
    return out


def chord_at(events, sec: float, default: str = "—"):
    """Nombre del acorde vigente en sec (último evento ≤ sec)."""
    name = default
    for s, n in events:
        if s <= sec:
            name = n
        else:
            break
    return name


def lyric_at(events, sec: float, default: str = ""):
    """Línea de letra vigente en sec (última con inicio ≤ sec)."""
    txt = default
    for s, t in events:
        if s <= sec:
            txt = t
        else:
            break
    return txt


# ── Edición de acordes: vocabulario, sugerencias y alineación ───────────
# Sufijos del cifrado español que usa la app (m = menor, 7 = séptima…).
CHORD_QUALITIES = ("", "m", "7", "m7", "maj7", "6", "m6", "dim", "aug",
                   "sus2", "sus4", "add9", "9", "m9", "5", "m7b5")


def chord_vocabulary():
    """Acordes del cifrado usado aquí (Do, Dom, Do7, Rebm…)."""
    return [f"{r}{q}" for r in NAMES_ES for q in CHORD_QUALITIES]


def suggest_chords(text: str, used=(), limit: int = 8):
    """Sugerencias para el texto tecleado; primero los de la propia canción.

    Coincide por prefijo ("fa" → Fa, Fam, Fa7…) y, con dos o más letras,
    también en cualquier posición ("m7" → Fam7, Dom7…).
    """
    used_l = []
    for u in used or ():
        u = str(u).strip()
        if u and u not in used_l:
            used_l.append(u)
    vocab = chord_vocabulary()
    query = (text or "").strip().lower()
    if not query:
        out = used_l + [n for n in vocab if n not in used_l]
        return out[:limit]

    def _hit(n):
        low = n.lower()
        return low.startswith(query) or (len(query) > 1 and query in low)

    out = [n for n in used_l if _hit(n)]
    out += [n for n in vocab if _hit(n) and n not in out]
    return out[:limit]


def snap_events_to_grid(events, grid_secs, tol_ratio: float = 0.2,
                        tol_max: float = 0.30):
    """Alinea eventos a la rejilla cuando caen cerca de un inicio de compás.

    Corrige desfases pequeños (p. ej. un acorde guardado con el offset del
    MP3 en vez de con la rejilla de la partitura) sin tocar los cambios
    intencionados a mitad de compás: la tolerancia es una fracción del
    compás, con tope en segundos. Si dos eventos caen en el mismo inicio
    gana el más cercano.
    """
    grid = sorted({float(g) for g in (grid_secs or ())})
    evs  = [(float(s), str(n)) for s, n in (events or ())]
    if not grid:
        return [list(e) for e in evs]
    spans = [b - a for a, b in zip(grid, grid[1:], strict=False) if b > a]
    span  = min(spans) if spans else 1.0
    tol   = max(0.05, min(tol_max, span * tol_ratio))
    snapped = {}
    out     = []
    for sec, name in evs:
        near = min(grid, key=lambda g: abs(g - sec))
        dist = abs(near - sec)
        if dist <= tol:
            prev = snapped.get(near)
            if prev is None or dist < prev[0]:
                snapped[near] = (dist, name)
        else:
            out.append([sec, name])
    out += [[near, name] for near, (_d, name) in snapped.items()]
    out.sort(key=lambda e: e[0])
    return out


def save_song_map(path: str, chords, lyrics, barlen: int = 4):
    """Guarda el mapa de la canción. `barlen` = tiempos por compás
    (3 en 3/4 como los corridos tumbados, 4 en 4/4) para agrupar las
    subdivisiones del widget timeline estilo Chordify."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"chords": [[s, n] for s, n in chords],
                   "lyrics": [[s, t] for s, t in lyrics],
                   "barlen": int(barlen)}, f,
                  ensure_ascii=False, indent=1)


def load_song_map(path: str):
    if not path or not os.path.exists(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        chords = [(float(s), str(n)) for s, n in d.get("chords", [])]
        lyrics = [(float(s), str(t)) for s, t in d.get("lyrics", [])]
        return chords, lyrics
    except Exception:
        return [], []


def load_song_barlen(path: str, default: int = 4) -> int:
    """Lee `barlen` (tiempos por compás) del <base>.chords.json.

    Es lo que en el HTML de Chordify aparece como `barlength-N` en
    `<div id="chords" class="chords ... barlength-3">`: con N=3 el
    widget agrupa las subdivisiones de 3 en 3 (compás de 3/4).
    Devuelve `default` si no hay dato."""
    try:
        if not path or not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        b = int(d.get("barlen", default))
        return b if b in (2, 3, 4, 6) else default
    except Exception:
        return default
