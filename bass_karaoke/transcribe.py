"""Transcripción offline de la línea de bajo desde audio.

Pipeline:
  1. Aislar el bajo: stem ``*bass*.wav`` (Demucs) si existe; si no, el mix
     filtrado con un paso-bajo agresivo (rápido, sin dependencias).
  2. Detectar la fundamental por ventanas con el MPM (McLeod) del proyecto
     (`audio.pitch_engine._mpm_pitch`), robusto en graves.
  3. Segmentar la pista de f0 en notas (suavizado + histéresis + duración
     mínima + fusión de repeticiones).
  4. Entregar ``(start, end, midi)`` en segundos a `build.build_from_notes`.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys

import numpy as np

from .config import (
    SAMPLERATE, MIN_HZ, MAX_HZ, MPM_WIN, MPM_THRESHOLD,
    HIGHPASS_HZ, LOWPASS_HZ,
)
from .audio.pitch_engine import _mpm_pitch

# Cortes del paso-bajo: el stem ya viene limpio; el mix necesita cortar más
# (guitarra, voz y bombo) o el MPM se engancha a contenido no-bajo.
LP_STEM = 700.0
LP_MIX = 200.0

AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aiff", ".aif")


def _resample(y, sr, target):
    if sr == target:
        return y
    try:
        import librosa
        return librosa.resample(y.astype(np.float32), orig_sr=sr, target_sr=target)
    except Exception:
        n = int(round(len(y) * target / sr))
        x_old = np.linspace(0.0, 1.0, len(y), endpoint=False)
        x_new = np.linspace(0.0, 1.0, n, endpoint=False)
        return np.interp(x_new, x_old, y).astype(np.float32)


def load_audio(path, sr=SAMPLERATE):
    """Carga mono a `sr`. soundfile para wav; librosa para el resto."""
    ext = os.path.splitext(path)[1].lower()
    y = None
    if ext in (".wav", ".flac", ".aiff", ".aif", ".ogg"):
        try:
            import soundfile as sf
            y, file_sr = sf.read(path, dtype="float32", always_2d=True)
            y = y.mean(1)
            return _resample(y, file_sr, sr), sr
        except Exception:
            y = None
    try:
        import librosa
        y, file_sr = librosa.load(path, sr=sr, mono=True)
        return y.astype(np.float32), sr
    except Exception as exc:
        raise RuntimeError(f"No se pudo leer el audio {path}: {exc}")


def _bandpass(y, sr, hp=HIGHPASS_HZ, lp=LP_STEM):
    """HP + LP Butterworth (scipy si está; si no, biquads numpy)."""
    try:
        from scipy.signal import butter, sosfilt
        sos = np.vstack([butter(2, hp, "highpass", fs=sr, output="sos"),
                         butter(4, lp, "lowpass", fs=sr, output="sos")])
        return sosfilt(sos, y).astype(np.float32)
    except Exception:
        from .audio.pitch_engine import _hp_biquad, _lp_biquad, _apply_biquad
        sections = [_hp_biquad(hp, sr, 0.7071),
                    _lp_biquad(lp, sr, 0.5412),
                    _lp_biquad(lp, sr, 1.3066)]
        state = np.zeros(4 * len(sections), dtype=np.float64)
        out = y.astype(np.float64)
        for k, (b, a) in enumerate(sections):
            out = _apply_biquad(out, b, a, state[4 * k:4 * k + 4])
        return out.astype(np.float32)


def find_bass_stem(song_dir):
    """Busca un stem de bajo ya separado (p. ej. htdemucs-bass.wav)."""
    if not os.path.isdir(song_dir):
        return None
    for root, _dirs, files in os.walk(song_dir):
        for name in sorted(files):
            low = name.lower()
            if low.endswith(".wav") and "bass" in low and "basic" not in low:
                return os.path.join(root, name)
    return None


def find_audio(song_dir):
    """Audio principal de la canción (prefiere <carpeta>.mp3)."""
    files = []
    for name in sorted(os.listdir(song_dir)):
        if name.lower().endswith(AUDIO_EXTS) and os.path.isfile(os.path.join(song_dir, name)):
            files.append(name)
    if not files:
        return None
    base = os.path.basename(song_dir).lower()
    for name in files:
        if os.path.splitext(name)[0].lower() == base:
            return os.path.join(song_dir, name)
    return os.path.join(song_dir, files[0])


def separate_bass_demucs(audio_path, out_dir, model="htdemucs"):
    """Separa stems con Demucs (requiere la feature instalada).

    Devuelve la ruta del stem de bajo o None. Es lento (CPU) y pesado.
    """
    try:
        from demucs.separate import main as demucs_main
    except Exception:
        return None
    os.makedirs(out_dir, exist_ok=True)
    try:
        demucs_main(["-n", model, "--out", out_dir, "--filename", "{stem}.{ext}",
                     audio_path])
    except Exception as exc:
        print(f"[demucs] {exc}")
        return None
    track = os.path.splitext(os.path.basename(audio_path))[0]
    for cand in (os.path.join(out_dir, model, track, "bass.wav"),
                 os.path.join(out_dir, model, track, "bass.mp3")):
        if os.path.exists(cand):
            # Caché estable para no re-separar en la próxima generación.
            try:
                song_dir = os.path.dirname(os.path.abspath(audio_path))
                dst = os.path.join(song_dir, "work",
                                   f"{os.path.basename(song_dir)}-bass.wav")
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    shutil.copy2(cand, dst)
                return dst
            except OSError:
                return cand
    return None


def detect_notes_from_signal(y, sr, progress_cb=None, hop=256,
                             min_dur=0.10, merge_gap=0.07):
    """Pista de f0 por ventanas MPM → lista de (start, end, midi)."""
    n = len(y)
    n_frames = max(0, (n - MPM_WIN) // hop + 1)
    f0 = np.zeros(n_frames, dtype=np.float64)
    for k in range(n_frames):
        i = k * hop
        hz, _ = _mpm_pitch(y[i:i + MPM_WIN], sr, MIN_HZ, MAX_HZ, MPM_THRESHOLD)
        f0[k] = hz
        if progress_cb and (k % 400 == 0):
            progress_cb(k / max(1, n_frames))
    times = np.arange(n_frames) * hop / sr

    # Suavizado: mediana sobre 5 frames, solo si hay >=3 con voz.
    f0m = np.zeros_like(f0)
    for k in range(n_frames):
        lo, hi = max(0, k - 2), min(n_frames, k + 3)
        seg = f0[lo:hi]
        seg = seg[seg > 0]
        f0m[k] = np.median(seg) if len(seg) >= 3 else 0.0

    # Segmentación por histéresis de altura (±0.6 semitonos).
    raw = []
    i = 0
    while i < n_frames:
        if f0m[i] <= 0:
            i += 1
            continue
        ref = f0m[i]
        j = i
        while j < n_frames and f0m[j] > 0 and abs(12 * math.log2(f0m[j] / ref)) < 0.6:
            ref = 0.7 * ref + 0.3 * f0m[j]
            j += 1
        if times[j - 1] - times[i] >= min_dur:
            midi = int(round(12 * math.log2(np.median(f0m[i:j]) / 440.0) + 69))
            raw.append([times[i], times[j - 1], midi])
        i = j

    # Fusiona repeticiones contiguas del mismo tono.
    merged = []
    for s, e, m in raw:
        if merged and m == merged[-1][2] and s - merged[-1][1] < merge_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e, m])

    # Blips aislados al principio (antes de que entre el bajo).
    if len(merged) >= 2:
        s0, e0, _ = merged[0]
        if (e0 - s0) < 0.30 and (merged[1][0] - e0) > 0.60:
            merged.pop(0)
    return [tuple(x) for x in merged]


def estimate_bpm(y, sr):
    """Tempo aproximado (negras/min) plegado al rango 60-180."""
    try:
        import librosa
        tempo = librosa.beat.beat_track(y=y, sr=sr, start_bpm=100)[0]
        tempo = float(np.atleast_1d(tempo)[0])
        while tempo > 180:
            tempo /= 2.0
        while 0 < tempo < 60:
            tempo *= 2.0
        return tempo
    except Exception:
        return None


def load_bass_signal(song_dir, use_demucs=True, progress_cb=None):
    """Devuelve (y, sr, fuente, ruta). Fuente: 'stem' o 'mix'."""
    stem = find_bass_stem(song_dir)
    if stem:
        y, sr = load_audio(stem)
        return _bandpass(y, sr, lp=LP_STEM), sr, "stem", stem
    audio = find_audio(song_dir)
    if not audio:
        raise RuntimeError("La canción no tiene audio ni stem de bajo")
    if use_demucs:
        stem = separate_bass_demucs(audio, os.path.join(song_dir, "work", "demucs"))
        if stem:
            y, sr = load_audio(stem)
            return _bandpass(y, sr, lp=LP_STEM), sr, "demucs", stem
    y, sr = load_audio(audio)
    return _bandpass(y, sr, lp=LP_MIX), sr, "mix", audio


def transcribe_song(song_dir, barlen=3, bars_per_chord=2,
                    key_fifths=-4, key_mode="minor",
                    clef_sign="F", clef_line=4,
                    bpm=None, use_demucs=True, progress_cb=None):
    """Genera <carpeta>.musicxml + .chords.json a partir del audio.

    Devuelve el dict de estadísticas de `build.build_from_notes` más
    ``source`` (stem/mix/demucs) y las rutas generadas.
    """
    from . import build

    def step(msg, frac=None):
        if progress_cb:
            progress_cb(msg, frac)

    step("Aislando el bajo…", 0.02)
    y, sr, source, audio_path = load_bass_signal(
        song_dir, use_demucs=use_demucs,
        progress_cb=None)
    step(f"Analizando audio ({source})…", 0.05)
    notes = detect_notes_from_signal(
        y, sr, progress_cb=lambda f: step("Detectando notas…", 0.05 + 0.75 * f))
    if not notes:
        raise RuntimeError("No se detectaron notas de bajo en el audio")

    step("Ajustando tempo…", 0.82)
    if bpm is not None and bpm <= 0:
        bpm = None

    step("Construyendo partitura…", 0.90)
    base_name = os.path.basename(os.path.normpath(song_dir))
    out_base = os.path.join(song_dir, base_name)
    for ext in (".musicxml", ".chords.json"):
        p = out_base + ext
        if os.path.exists(p):
            try:
                shutil.copy2(p, p + ".bak")
            except OSError:
                pass
    res = build.build_from_notes(
        notes, out_base, bpm=bpm, barlen=barlen,
        bars_per_chord=bars_per_chord,
        key_fifths=key_fifths, key_mode=key_mode,
        clef_sign=clef_sign, clef_line=clef_line)
    res["source"] = source
    res["audio"] = audio_path
    res["raw_notes"] = len(notes)
    step("Listo", 1.0)
    return res
