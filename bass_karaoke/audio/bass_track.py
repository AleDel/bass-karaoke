"""
Render offline de una línea de bajo a audio, para oírla como una pista más
del mixer (junto al MP3 y al metrónomo).

Dos motores, con la misma interfaz:

* ``sf2``   — SoundFont vía ``tinysoundfont`` (feature opcional): timbre de
              bajo eléctrico real (GM "Fingered Bass").
* ``synth`` — síntesis numpy (fundamental + armónicos con caída exponencial):
              suena siempre, sin instalar nada.

El render es determinista y se hace una sola vez por canción (o al cambiar
el tempo), no en el callback de audio.
"""

import logging
import math
import os
import sys

import numpy as np

from ..config import ASSETS_DIR, SAMPLERATE

log = logging.getLogger(__name__)

SOUNDFONT_NAME = "TimGM6mb.sf2"
JJAZZLAB_SF_NAME = "JJazzLab-SoundFont.sf2"
BASS_PRESET    = 32        # GM: Acoustic Bass (el que usa jjSwing.mix)
BASS_GAIN_DB   = -6.0
RELEASE_SEC    = 1.2       # cola tras la última nota

try:
    import tinysoundfont
    TSF_OK = True
except ImportError:
    TSF_OK = False


def _jjazzlab_soundfont_candidates():
    """SoundFont GM de JJazzLab (356 MB): el que usa jjSwing, mucho más rico."""
    env = os.environ.get("BASS_KARAOKE_JJAZZLAB") or os.environ.get("JJAZZLAB_HOME")
    bases = []
    if env:
        if env.lower().endswith(".jar"):
            env = os.path.dirname(os.path.dirname(env))
        bases += [os.path.join(env, "jjazzlab"), env]
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        bases.append(os.path.join(base, "JJazzLab", "jjazzlab"))
    mod = os.path.join("modules", "soundfont", JJAZZLAB_SF_NAME)
    return [os.path.join(b, mod) for b in bases]


def soundfont_candidates():
    """Rutas candidatas del SoundFont, por orden de preferencia."""
    paths = []
    env = os.environ.get("BASS_KARAOKE_SF2")
    if env:
        paths.append(env)
    paths += _jjazzlab_soundfont_candidates()
    paths.append(os.path.join(ASSETS_DIR, SOUNDFONT_NAME))
    # Exe empaquetado: assets/ también puede venir dentro del bundle
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        paths.append(os.path.join(meipass, "assets", SOUNDFONT_NAME))
    try:
        import pretty_midi
        paths.append(os.path.join(
            os.path.dirname(pretty_midi.__file__), SOUNDFONT_NAME))
    except ImportError:
        pass
    return paths


def find_soundfont():
    for p in soundfont_candidates():
        if p and os.path.isfile(p):
            return p
    return ""


def backend():
    """'sf2' si el SoundFont se puede usar, si no 'synth'."""
    return "sf2" if (TSF_OK and find_soundfont()) else "synth"


def hz_to_midi(hz: float) -> int:
    return int(round(69 + 12 * math.log2(max(1.0, float(hz)) / 440.0)))


# ── motor SoundFont ──────────────────────────────────────────────────────────
def _render_sf2(events, total_sec, sr, sf2, preset, gain_db):
    n_frames = max(1, int(math.ceil(total_sec * sr)))
    out = np.zeros((n_frames, 2), dtype=np.float32)

    synth = tinysoundfont.Synth(gain=gain_db, samplerate=sr)
    sfid = synth.sfload(sf2)
    synth.program_select(0, sfid, 0, int(preset))

    # Una sola lista ordenada de eventos: note-off antes que note-on en el
    # mismo frame (así una nota repetida se re-articula sin cortar la nueva).
    sched = []
    for t, dur, midi in events:
        a = int(round(float(t) * sr))
        b = int(round((float(t) + float(dur)) * sr))
        if b <= a:
            b = a + 1
        sched.append((a, 1, int(midi)))
        sched.append((b, 0, int(midi)))
    sched.sort(key=lambda e: (e[0], e[1]))

    pos, i, chunk = 0, 0, 1024
    while pos < n_frames:
        while i < len(sched) and sched[i][0] <= pos:
            _, kind, midi = sched[i]
            if kind:
                synth.noteon(0, midi, 100)
            else:
                synth.noteoff(0, midi)
            i += 1
        nxt = sched[i][0] if i < len(sched) else n_frames
        n = min(nxt - pos, chunk, n_frames - pos)
        if n <= 0:
            n = 1
        # generate_simple(n) devuelve n frames en float32 estéreo intercalado
        # (la librería documenta float32; leerlo como int16 sonaba a ruido).
        buf = np.frombuffer(synth.generate_simple(n), dtype=np.float32)
        buf = buf.reshape(-1, 2)[:n]
        out[pos:pos + len(buf)] = buf
        pos += max(1, len(buf))

    return out


def _normalize(audio: np.ndarray) -> np.ndarray:
    """Evita el clipping del SoundFont y deja un nivel audible de bajo."""
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0.92:
        audio = audio * (0.92 / peak)
    elif 0.0 < peak < 0.7:
        audio = audio * (0.7 / peak)
    return audio


# ── motor numpy (sin dependencias) ──────────────────────────────────────────
_HARMONICS = ((1, 1.00, 1.0), (2, 0.42, 1.8), (3, 0.22, 2.6),
              (4, 0.12, 3.4), (5, 0.07, 4.2), (6, 0.04, 5.0))


def _synth_note(midi: int, dur: float, sr: int):
    hz  = 440.0 * 2 ** ((midi - 69) / 12.0)
    n   = max(1, int((dur + 0.25) * sr))
    t   = np.arange(n, dtype=np.float32) / sr
    env = np.exp(-t * 2.2)
    end = int(dur * sr)
    if end < n:
        rel = np.ones(n, dtype=np.float32)
        rel[end:] = np.linspace(1.0, 0.0, n - end) ** 2
        env = env * rel
    wave = np.zeros(n, dtype=np.float32)
    for mult, amp, decay in _HARMONICS:
        if hz * mult > 4000:
            break
        wave += (amp * np.exp(-t * decay)
                 * np.sin(2 * np.pi * hz * mult * t)).astype(np.float32)
    wave *= env
    att = max(1, int(0.006 * sr))
    wave[:att] *= np.linspace(0.0, 1.0, att, dtype=np.float32)
    return wave


def _render_synth(events, total_sec, sr):
    n_frames = max(1, int(math.ceil(total_sec * sr)))
    mono = np.zeros(n_frames, dtype=np.float32)
    for t, dur, midi in events:
        w = _synth_note(int(midi), float(dur), sr)
        a = int(round(float(t) * sr))
        b = min(n_frames, a + len(w))
        if b > a:
            mono[a:b] += w[:b - a]
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    if peak > 0.85:
        mono *= 0.85 / peak
    return np.column_stack([mono, mono])


# ── API ─────────────────────────────────────────────────────────────────────
def render(events, total_sec: float, sr: int = SAMPLERATE,
           sf2=None, preset: int = BASS_PRESET,
           engine: str = "auto") -> np.ndarray:
    """Renderiza ``events`` = [(t_sec, dur_sec, midi), ...] a estero float32.

    ``engine``: "auto" (SoundFont si está disponible), "sf2" o "synth".
    Devuelve un array (frames, 2) float32 en [-1, 1], con ``RELEASE_SEC`` de
    cola para que no se corte la última nota.
    """
    events = [(float(t), max(0.02, float(d)), int(m))
              for t, d, m in events if m is not None and 0 <= int(m) < 128]
    total = max(0.0, float(total_sec)) + RELEASE_SEC
    if not events:
        return np.zeros((max(1, int(total * sr)), 2), dtype=np.float32)
    if engine != "synth":
        sf2 = sf2 or (find_soundfont() if TSF_OK else "")
        if sf2:
            try:
                return _normalize(
                    _render_sf2(events, total, sr, sf2, preset, BASS_GAIN_DB))
            except Exception as e:                    # SoundFont roto: seguimos
                log.warning(f"[BassTrack] SoundFont falló ({e}); uso síntesis")
    return _render_synth(events, max(t for t, _, _ in events) + RELEASE_SEC, sr)


def to_int16(audio: np.ndarray) -> np.ndarray:
    """float32 (frames, 2) → int16 contiguo, para pygame.sndarray."""
    x = np.clip(audio, -1.0, 1.0) * 32767.0
    return np.ascontiguousarray(x.astype(np.int16))
