"""
Motor de detección de pitch en tiempo real.

La clase PitchEngine arranca un hilo de audio que captura del micrófono,
aplica el método de pitch seleccionado y llama al callback on_update(hz, note).
Los algoritmos concretos viven en ``detectors.py``; aquí solo quedan la
captura, el pre-filtrado y la estabilización temporal.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import Counter, deque

import numpy as np

from ..config import (
    HIGHPASS_HZ,
    LOWPASS_HZ,
    MAX_HZ,
    MIN_HZ,
    PITCH_DEBUG_EVERY,
    PITCH_FAST_VOTES,
    PITCH_HISTORY_FRAMES,
    PITCH_HOLD_FRAMES,
    PITCH_RMS_GATE,
    SAMPLERATE,
)
from ..utils import hz_to_midi, hz_to_note_name
from .detectors import AUBIO_OK, _octave_to_bass_range, create_detector
from .detectors import _mpm_pitch as _mpm_pitch  # re-export: lo usa transcribe.py

try:
    import pyaudio as _pyaudio_mod
    PA_OK = True
except ImportError:
    PA_OK = False

try:
    from scipy.signal import butter as _sci_butter
    from scipy.signal import sosfilt as _sci_sosfilt
    SCIPY_OK = True
except ImportError:
    SCIPY_OK = False

log = logging.getLogger(__name__)

PITCH_AVAILABLE = AUBIO_OK and PA_OK

__all__ = [
    "PitchEngine", "PitchStabilizer", "PITCH_AVAILABLE", "PA_OK",
    "clean_device_name", "enumerate_devices", "device_name_warning",
    "_mpm_pitch", "_octave_to_bass_range",
]


def clean_device_name(name):
    """Repara nombres con UTF-8 decodificado como latin-1 (PyAudio en Windows).

    PyAudio devuelve algunos nombres de dispositivo como texto ya mal
    decodificado ('MicrÃ³fono' en vez de 'Micrófono'); re-encodear a latin-1 y
    decodear como UTF-8 lo corrige. Si el nombre no es mojibake, se deja igual.
    """
    if isinstance(name, bytes):
        return name.decode("utf-8", "replace")
    if not isinstance(name, str):
        return str(name)
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def enumerate_devices():
    """Devuelve lista de (device_idx, name) de dispositivos de entrada disponibles."""
    if not PA_OK:
        return []
    p = _pyaudio_mod.PyAudio()
    devices = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            devices.append((i, clean_device_name(info["name"])))
    p.terminate()
    return devices


# Nombres típicos de endpoints de SALIDA o loopback que a veces aparecen como
# "entrada" (p. ej. VB-Cable "CABLE Output", Stereo Mix). Elegirlos para un bajo
# suele ser un error — se avisa, no se bloquea (el loopback legítimo existe).
_OUTPUT_NAME_HINTS = (
    "output", "salida", "loopback", "stereo mix", "mezcla",
    "what u hear", "wave out", "monitor",
)


def device_name_warning(name: str):
    """Etiqueta de aviso si el nombre huele a salida/loopback, o None."""
    low = (name or "").lower()
    if any(h in low for h in _OUTPUT_NAME_HINTS):
        return "¿salida?"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Pre-filtrado de streaming: high-pass 20 Hz (DC/rumble) + low-pass 700 Hz
# (armónicos que hacen que el detector se vaya una octava arriba).
# Usa scipy.signal si está disponible; si no, cascada de biquads Butterworth
# puros en numpy (mismo resultado, un poco más lento).
# ─────────────────────────────────────────────────────────────────────────────
_BP_Q    = 0.70710678   # Butterworth 2º orden
_BP_Q1   = 0.54119610   # secciones de un Butterworth 4º orden
_BP_Q2   = 1.30656296


def _lp_biquad(fc: float, fs: float, Q: float):
    w0  = 2.0 * math.pi * fc / fs
    c   = math.cos(w0)
    s   = math.sin(w0)
    alpha = s / (2.0 * Q)
    b0, b1, b2 = (1.0 - c) / 2.0, 1.0 - c, (1.0 - c) / 2.0
    a0, a1, a2 = 1.0 + alpha, -2.0 * c, 1.0 - alpha
    return (b0 / a0, b1 / a0, b2 / a0), (a1 / a0, a2 / a0)


def _hp_biquad(fc: float, fs: float, Q: float):
    w0  = 2.0 * math.pi * fc / fs
    c   = math.cos(w0)
    s   = math.sin(w0)
    alpha = s / (2.0 * Q)
    b0, b1, b2 = (1.0 + c) / 2.0, -(1.0 + c), (1.0 + c) / 2.0
    a0, a1, a2 = 1.0 + alpha, -2.0 * c, 1.0 - alpha
    return (b0 / a0, b1 / a0, b2 / a0), (a1 / a0, a2 / a0)


def _apply_biquad(x: np.ndarray, b, a, st):
    """Filtra un chunk con un biquad; st = [x1, x2, y1, y2] (se muta in-place)."""
    b0, b1, b2 = b
    a1, a2     = a
    x1, x2, y1, y2 = st
    out = np.empty_like(x)
    for i, s in enumerate(x):
        y = b0 * s + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out[i] = y
        x2, x1, y2, y1 = x1, s, y1, y
    st[0], st[1], st[2], st[3] = x1, x2, y1, y2
    return out


def _build_prefilter(fs: float):
    """
    Devuelve (filter_fn, state) para filtrar chunks en streaming.
    filter_fn(x) -> y  mantiene el estado interno entre llamadas.
    """
    if SCIPY_OK:
        sos = np.vstack([
            _sci_butter(2, HIGHPASS_HZ, "highpass", fs=fs, output="sos"),
            _sci_butter(4, LOWPASS_HZ,  "lowpass",  fs=fs, output="sos"),
        ])
        state = {"zi": np.zeros((sos.shape[0], 2), dtype=np.float32)}
        def _filt(x, sos=sos, state=state):
            y, state["zi"] = _sci_sosfilt(sos, x, zi=state["zi"])
            return y
        return _filt, state

    sections = [
        _hp_biquad(HIGHPASS_HZ, fs, _BP_Q),
        _lp_biquad(LOWPASS_HZ, fs, _BP_Q1),
        _lp_biquad(LOWPASS_HZ, fs, _BP_Q2),
    ]
    state = np.zeros(4 * len(sections), dtype=np.float64)
    def _filt(x, sections=sections, state=state):
        for k, (b, a) in enumerate(sections):
            x = _apply_biquad(x, b, a, state[4 * k: 4 * k + 4])
        return x
    return _filt, state


# ══════════════════════════════════════════════════════════════════════════
#  Estabilización temporal (independiente del detector)
# ══════════════════════════════════════════════════════════════════════════
_SILENT = (0.0, "—", 0.0, "—")


class PitchStabilizer:
    """Convierte lecturas por frame en la nota suave que ve la UI.

    * mediana de los últimos ``history`` frames → ``detected_hz``;
    * fast-commit: si ``fast_votes`` de los últimos 3 frames coinciden en la
      misma nota MIDI, esa es la nota estable (~93 ms);
    * ``on_silence`` mantiene la última nota ``hold_frames`` antes de soltar.

    No depende de audio ni de pygame: se puede probar con números.
    """

    def __init__(self, hold_frames: int = PITCH_HOLD_FRAMES,
                 history: int = PITCH_HISTORY_FRAMES):
        self.hold_frames = hold_frames
        self._buf = deque(maxlen=history)
        self._hold = 0

    @property
    def hold_count(self) -> int:
        return self._hold

    def reset(self) -> None:
        self._buf.clear()
        self._hold = 0

    def on_silence(self):
        """Frame por debajo del gate de RMS.

        Devuelve ``(0, '—', 0, '—')`` cuando se agota el hold y ``None``
        mientras dura (no se publica nada, igual que antes).
        """
        self._hold += 1
        if self._hold >= self.hold_frames:
            self._buf.clear()
            return _SILENT
        return None

    def feed(self, hz: float, conf: float, conf_threshold: float):
        """Añade una lectura y devuelve ``(det_hz, det_note, stb_hz, stb_note)``."""
        if conf >= conf_threshold and hz > 0:
            folded = _octave_to_bass_range(hz)
            if MIN_HZ <= folded <= MAX_HZ:
                self._buf.append(folded)
                self._hold = 0
            else:
                self._hold += 1
        else:
            self._hold += 1

        if self._buf and self._hold < self.hold_frames:
            values = list(self._buf)
            det_hz = float(np.median(values))
            recent = values[-3:]
            stb_hz, stb_note = 0.0, "—"
            midi_votes = [int(round(hz_to_midi(h))) for h in recent]
            top_midi, top_count = Counter(midi_votes).most_common(1)[0]
            if top_count >= PITCH_FAST_VOTES:
                matching = [h for h in recent
                            if int(round(hz_to_midi(h))) == top_midi]
                stb_hz = float(np.median(matching))
                stb_note = hz_to_note_name(stb_hz)
            return det_hz, hz_to_note_name(det_hz), stb_hz, stb_note

        self._buf.clear()
        return _SILENT


class PitchEngine:
    """
    Hilo de captura y detección de pitch.

    Parámetros
    ----------
    method : str
        Método de detección: "mpm" | "aubio" | "crepe-tiny" | "crepe-full" |
        "pesto" | "pesto-onnx" | "basic-pitch"
    device_id : int
        Índice PyAudio del dispositivo de entrada.
    on_update : callable(detected_hz, detected_note, stable_hz, stable_note)
        Callback invocado con los valores actualizados.
    on_engine_label : callable(label: str)
        Callback para notificar el nombre del motor activo (para la UI).
    """

    def __init__(self, method: str, device_id: int,
                 on_update, on_engine_label=None, on_debug=None):
        self.method          = method
        self.device_id       = device_id
        self.on_update       = on_update
        self.on_engine_label = on_engine_label or (lambda _: None)
        self.on_debug        = on_debug or (lambda *_: None)
        self._stop_evt       = threading.Event()
        self._lifecycle      = threading.Lock()
        self._thread         = None

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self):
        """Arranca el hilo una sola vez (idempotente y seguro entre hilos)."""
        with self._lifecycle:
            if self.is_running:
                return
            # No limpiamos el flag hasta saber que no queda un hilo vivo:
            # si el stop anterior agotó el timeout, reactivarlo dejaría dos
            # hilos compitiendo por el micrófono.
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 1.5):
        """Pide al hilo que termine y espera (sin bloquearse indefinidamente)."""
        with self._lifecycle:
            self._stop_evt.set()
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                log.warning("PitchEngine: el hilo no terminó en %.1fs", timeout)

    # ─────────────────────────────────────────────────────────────────────────
    def _loop(self):
        if not PA_OK:
            return

        detector = create_detector(self.method, self.on_engine_label)
        stabilizer = PitchStabilizer()
        prefilter, _ = _build_prefilter(SAMPLERATE)
        log.info(f"[pitch] pre-filtro HP {HIGHPASS_HZ:.0f} Hz + LP {LOWPASS_HZ:.0f} Hz"
                 + ("  (scipy)" if SCIPY_OK else "  (biquads numpy)"))

        p = _pyaudio_mod.PyAudio()
        stream = None
        debug_count = 0
        try:
            stream = p.open(
                format=_pyaudio_mod.paFloat32, channels=1, rate=SAMPLERATE,
                input=True, input_device_index=self.device_id,
                frames_per_buffer=detector.chunk_size)

            while not self._stop_evt.is_set():
                try:
                    data = stream.read(
                        detector.chunk_size, exception_on_overflow=False)
                    samples = np.frombuffer(data, dtype=np.float32).copy()
                    rms = float(np.sqrt(np.mean(samples ** 2)))

                    # Pre-filtrado: quita rumble/DC y armónicos altos que
                    # desvían la detección a la octava superior.
                    samples = prefilter(samples)
                    # scipy.signal.sosfilt sube a float64 si los coeficientes
                    # son float64; aubio exige float32 y ONNX espera float.
                    samples = samples.astype(np.float32, copy=False)

                    if rms < PITCH_RMS_GATE:
                        values = stabilizer.on_silence()
                        if values is not None:
                            self.on_update(*values)
                        continue

                    reading = detector.detect(samples)
                    if reading is None:
                        continue

                    debug_count += 1
                    if debug_count % PITCH_DEBUG_EVERY == 0:
                        self.on_debug(reading.hz, reading.conf, detector.name)

                    self.on_update(*stabilizer.feed(
                        reading.hz, reading.conf, detector.conf_threshold))

                except Exception as _e:
                    log.info(f"[audio loop] {_e}")
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            p.terminate()
            detector.close()
