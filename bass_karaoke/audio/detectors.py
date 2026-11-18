"""Detectores de pitch con una interfaz común.

Cada detector recibe los samples ya pre-filtrados de un chunk y devuelve
``PitchReading(hz, conf)`` (o ``None`` si ese frame no produce estimación,
p. ej. el warm-up de PESTO-ONNX). El bucle de :class:`PitchEngine` solo se
ocupa de capturar, filtrar y estabilizar; así cada motor se puede probar sin
micrófono y añadir uno nuevo no toca el resto.

``create_detector`` construye el motor pedido y cae a aubio (o a un detector
nulo) si las dependencias opcionales no están instaladas, igual que antes.
"""

from __future__ import annotations

import logging
import os
from typing import NamedTuple

import numpy as np

from ..config import (
    AUBIO_FFTSIZE,
    AUBIO_METHOD,
    AUBIO_SILENCE_DB,
    AUBIO_TOLERANCE,
    BASIC_PITCH_CONF_THRESH,
    BASS_MAX_HZ,
    CHUNK_SIZE,
    CREPE_CONF_THRESH,
    HOP_S,
    MAX_HZ,
    MIN_HZ,
    MPM_THRESHOLD,
    MPM_WIN,
    PESTO_AMP_GATE,
    PESTO_CONF_THRESH,
    PESTO_ONNX_AMP_GATE,
    PESTO_ONNX_CHUNK,
    PESTO_ONNX_CONF_THRESH,
    PESTO_ONNX_PATH,
    PESTO_ONNX_WARMUP,
    SAMPLERATE,
    WIN_S,
)
from ..utils import midi_to_hz

log = logging.getLogger(__name__)

try:
    import aubio as _aubio_mod
    AUBIO_OK = True
except ImportError:
    _aubio_mod = None
    AUBIO_OK = False


class PitchReading(NamedTuple):
    """Estimación de un frame: frecuencia en Hz y confianza 0-1."""

    hz: float
    conf: float


def _octave_to_bass_range(hz: float) -> float:
    """
    Pliega una detección al rango fundamental del bajo de forma SEGURA:
    solo actúa cuando el valor está claramente fuera de ese rango, así que
    nunca altera una nota real del bajo.

    - Debajo de MIN_HZ: sube una octava (detección sub-armónica).
    - Muy por encima del rango del bajo: divide por 2 o 3 (armónico).
    """
    if hz <= 0:
        return hz
    if hz < MIN_HZ:
        up = hz * 2.0
        if MIN_HZ <= up <= BASS_MAX_HZ:
            return up
        return hz
    if hz > BASS_MAX_HZ * 1.3:
        for div in (2, 3):
            root = hz / div
            if MIN_HZ <= root <= BASS_MAX_HZ:
                return root
    return hz


# ─────────────────────────────────────────────────────────────────────────────
# MPM — McLeod Pitch Method (McLeod & Wyvill 2005). Es el algoritmo estándar
# de los afinadores monofónicos (guitarra/bajo/violín): robusto en graves y
# frente a armónicos. Variante vectorizada con FFT del NSDF (igual que
# TarsosDSP, pero O(N log N) en vez de O(N²)).
# ─────────────────────────────────────────────────────────────────────────────
def _mpm_pitch(x: np.ndarray, fs: float, f_min: float, f_max: float,
               threshold: float = 0.8):
    """
    Devuelve (f0_hz, claridad). claridad = valor NSDF del pico (0-1).
    0.0 si no hay una fundamental fiable por encima de `threshold`.
    """
    N = len(x)
    xf = x.astype(np.float64)

    # Autocorrelación lineal con zero-padding (evita contaminación circular).
    X2 = np.fft.rfft(xf, n=2 * N)
    acf = np.fft.irfft(X2 * np.conj(X2), n=2 * N)[:N]

    # Divisor de TarsosDSP: Σ x[i]² + x[i+τ]² sobre i∈[0, N-τ)
    x2 = xf * xf
    cum = np.empty(N + 1)
    cum[0] = 0.0
    np.cumsum(x2, out=cum[1:])
    tau = np.arange(N)
    divisor = np.maximum(cum[N - tau] + (cum[N] - cum[tau]), 1e-12)
    nsdf = 2.0 * acf / divisor

    t_min = max(2, int(fs / f_max))
    t_max = min(N - 3, int(fs / f_min))
    if t_max <= t_min:
        return 0.0, 0.0

    seg = nsdf[t_min:t_max + 1]
    mask = (seg[1:-1] > seg[:-2]) & (seg[1:-1] >= seg[2:]) & (seg[1:-1] > 0)
    idxs = np.flatnonzero(mask) + 1   # índices locales (con offset 1 del borde)

    # La fundamental es el PRIMER pico por encima del umbral: todo señal
    # periódica con periodo T cumple NSDF(T)=1, así que los picos en 2T, 3T…
    # (sub-armónicos) aparecen después y no deben ganarle.
    for k in idxs:
        t1 = t_min + k
        y0, y1, y2 = nsdf[t1 - 1], nsdf[t1], nsdf[t1 + 1]
        a = 0.5 * (y0 - 2.0 * y1 + y2)
        b = 0.5 * (y2 - y0)
        denom = 4.0 * a
        if abs(denom) < 1e-12:
            val, dt = y1, 0.0
        else:
            dt = -b / (2.0 * a)
            val = y1 - b * b / denom
        if val < threshold:
            continue
        best_tau = t1 + dt
        best_val = val
        break
    else:
        return 0.0, 0.0
    f0 = fs / best_tau
    if not (f_min <= f0 <= f_max):
        return 0.0, 0.0
    return f0, float(best_val)


# ══════════════════════════════════════════════════════════════════════════
#  Interfaz común
# ══════════════════════════════════════════════════════════════════════════
class Detector:
    """Motor de pitch de un frame.

    Atributos que el bucle consulta:

    * ``name``: etiqueta corta para depuración.
    * ``label``: nombre que se muestra en la UI.
    * ``conf_threshold``: confianza mínima para aceptar la lectura.
    * ``chunk_size``: muestras por lectura del micrófono (PESTO-ONNX usa 512).
    """

    name = "null"
    label = "sin pitch"
    conf_threshold = 0.0
    chunk_size = CHUNK_SIZE

    def detect(self, samples: np.ndarray) -> PitchReading | None:
        raise NotImplementedError

    def close(self) -> None:
        """Libera recursos opcionales (modelos, ficheros temporales…)."""


class NullDetector(Detector):
    """Sin motor disponible: el bucle sigue vivo pero no detecta nada."""

    def detect(self, samples: np.ndarray) -> PitchReading:
        return PitchReading(0.0, 0.0)


class MPMDetector(Detector):
    """MPM sobre una ventana deslizante de ``MPM_WIN`` muestras."""

    name = "mpm"
    label = "MPM McLeod"
    conf_threshold = 0.0

    def __init__(self):
        self._buf = np.zeros(MPM_WIN, dtype=np.float32)
        log.info(f"[pitch] MPM (McLeod)  win={MPM_WIN}  hop={HOP_S}")

    def detect(self, samples: np.ndarray) -> PitchReading:
        n = len(samples)
        if n >= len(self._buf):
            self._buf[:] = samples[-len(self._buf):]
        else:
            self._buf[:-n] = self._buf[n:]
            self._buf[-n:] = samples
        hz, conf = _mpm_pitch(self._buf, SAMPLERATE, MIN_HZ, MAX_HZ, MPM_THRESHOLD)
        return PitchReading(hz, conf)


class AubioDetector(Detector):
    """aubio yinfft. Su confianza en graves es poco fiable → sin gate."""

    name = "aubio"
    label = f"aubio {AUBIO_METHOD}"
    conf_threshold = 0.0

    def __init__(self):
        if not AUBIO_OK:
            raise ImportError("aubio no instalado")
        self._pitch = _aubio_mod.pitch(
            AUBIO_METHOD, AUBIO_FFTSIZE, HOP_S, SAMPLERATE)
        self._pitch.set_unit("Hz")
        self._pitch.set_tolerance(AUBIO_TOLERANCE)
        self._pitch.set_silence(AUBIO_SILENCE_DB)
        log.info(f"[pitch] aubio {AUBIO_METHOD}  fft={AUBIO_FFTSIZE}  "
                 f"tol={AUBIO_TOLERANCE}  sin gate de confianza")

    def detect(self, samples: np.ndarray) -> PitchReading:
        hz = float(self._pitch(samples)[0])
        return PitchReading(hz, float(self._pitch.get_confidence()))


class CrepeDetector(Detector):
    """CREPE (torchcrepe) sobre una ventana de ``WIN_S`` muestras."""

    name = "crepe"
    conf_threshold = CREPE_CONF_THRESH

    def __init__(self, size: str):
        import torch
        import torchcrepe

        self._torch = torch
        self._tc = torchcrepe
        self._size = size
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._buf = np.zeros(WIN_S, dtype=np.float32)
        self.label = f"CREPE-{size} ({self._device.upper()})"
        log.info(f"[pitch] CREPE-{size} ({self._device})")

    def detect(self, samples: np.ndarray) -> PitchReading:
        n = len(samples)
        if n >= len(self._buf):
            self._buf[:] = samples[-len(self._buf):]
        else:
            self._buf[:-n] = self._buf[n:]
            self._buf[-n:] = samples
        audio = self._torch.from_numpy(self._buf).unsqueeze(0).float()
        with self._torch.no_grad():
            freq, period = self._tc.predict(
                audio, SAMPLERATE,
                hop_length=512,
                fmin=32.70, fmax=MAX_HZ,
                model=self._size,
                decoder=self._tc.decode.weighted_argmax,
                return_periodicity=True,
                device=self._device,
                pad=True,
            )
        return PitchReading(
            float(freq[0, -1].cpu()),
            float(period[0, -1].cpu()),
        )


class PestoDetector(Detector):
    """PESTO en modo streaming (modelo PyTorch)."""

    name = "pesto"
    conf_threshold = PESTO_CONF_THRESH

    def __init__(self):
        import torch
        from pesto import load_model

        device = "cuda" if torch.cuda.is_available() else "cpu"
        step_ms = CHUNK_SIZE / SAMPLERATE * 1000
        self._torch = torch
        self._device = device
        self._model = load_model(
            "mir-1k_g7",
            step_size=step_ms,
            sampling_rate=SAMPLERATE,
            streaming=True,
            max_batch_size=1,
        ).to(device)
        self._model.eval()
        self._dtype = next(self._model.parameters()).dtype
        self.label = f"PESTO ({device.upper()})"
        log.info(f"[pitch] PESTO streaming ({device})  step={step_ms:.1f}ms")

    def detect(self, samples: np.ndarray) -> PitchReading:
        x = self._torch.from_numpy(samples).unsqueeze(0).to(
            device=self._device, dtype=self._dtype)
        with self._torch.no_grad():
            f0, conf_t, amp_t = self._model(
                x, convert_to_freq=True, return_activations=False)
        hz = float(f0.flatten()[-1].cpu())
        conf = float(conf_t.flatten()[-1].cpu())
        amp = float(amp_t.flatten()[-1].cpu())
        if amp < PESTO_AMP_GATE:
            conf = 0.0
        return PitchReading(_octave_to_bass_range(hz), conf)


class PestoOnnxDetector(Detector):
    """PESTO exportado a ONNX: cache de estado y chunks de 512 muestras."""

    name = "pesto-onnx"
    conf_threshold = PESTO_ONNX_CONF_THRESH
    chunk_size = PESTO_ONNX_CHUNK

    def __init__(self):
        import onnxruntime as ort

        if not os.path.exists(PESTO_ONNX_PATH):
            raise FileNotFoundError(f"Modelo ONNX no encontrado: {PESTO_ONNX_PATH}")
        self._session = ort.InferenceSession(
            PESTO_ONNX_PATH, providers=["CPUExecutionProvider"])
        cache_size = self._session.get_inputs()[1].shape[1]
        self._cache = np.zeros((1, cache_size), dtype=np.float32)
        self._count = 0
        self.label = "PESTO-ONNX (CPU)"
        log.info(f"[pitch] PESTO-ONNX  cache={cache_size}  chunk={PESTO_ONNX_CHUNK}")

    def detect(self, samples: np.ndarray) -> PitchReading | None:
        self._count += 1
        outs = self._session.run(
            None,
            {"audio": samples[np.newaxis, :], "cache": self._cache})
        pred_midi, conf_o, vol_o, _, cache_out = outs
        self._cache = cache_out
        if self._count <= PESTO_ONNX_WARMUP:
            return None
        hz = midi_to_hz(float(pred_midi.flat[0]))
        conf = float(conf_o.flat[0])
        if float(vol_o.flat[0]) < PESTO_ONNX_AMP_GATE:
            conf = 0.0
        return PitchReading(_octave_to_bass_range(hz), conf)


class BasicPitchDetector(Detector):
    """Basic Pitch con buffer deslizante de 1.5 s (infiere cada 0.5 s)."""

    name = "basic-pitch"
    conf_threshold = BASIC_PITCH_CONF_THRESH

    def __init__(self):
        import pathlib
        import tempfile

        import soundfile as sf
        from basic_pitch.inference import Model, predict

        os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

        onnx_path = None
        try:
            import basic_pitch as bp_pkg
            candidate = (pathlib.Path(bp_pkg.__file__).parent
                         / "saved_models" / "icassp_2022" / "nmp.onnx")
            if candidate.exists():
                onnx_path = str(candidate)
        except Exception:
            pass
        if onnx_path:
            model = Model(onnx_path)
            log.info(f"[pitch] Basic Pitch ONNX  {onnx_path}")
        else:
            from basic_pitch import ICASSP_2022_MODEL_PATH
            model = Model(ICASSP_2022_MODEL_PATH)
            log.info("[pitch] Basic Pitch (runtime por defecto)")

        self._sf = sf
        self._predict = predict
        self._model = model
        self._buf_sec = 1.5
        self._buf = np.zeros(int(self._buf_sec * SAMPLERATE), dtype=np.float32)
        self._hop_chunks = max(1, int(0.5 * SAMPLERATE / CHUNK_SIZE))
        self._chunk_count = 0
        self._latest_hz = 0.0
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self._tmp_path = tmp.name
        tmp.close()
        self.label = "Basic Pitch (ONNX)"

    def detect(self, samples: np.ndarray) -> PitchReading:
        n = len(samples)
        self._buf[:-n] = self._buf[n:]
        self._buf[-n:] = samples
        self._chunk_count += 1
        if self._chunk_count >= self._hop_chunks:
            self._chunk_count = 0
            try:
                self._sf.write(self._tmp_path, self._buf, SAMPLERATE)
                _, _, note_events = self._predict(self._tmp_path, self._model)
                win_start = self._buf_sec - 0.5
                recent = [n for n in note_events if n[0] >= win_start]
                if recent:
                    best = max(recent, key=lambda n: n[3])
                    self._latest_hz = midi_to_hz(float(best[2]))
                else:
                    self._latest_hz = 0.0
            except Exception as exc:
                log.info(f"[basic-pitch] {exc}")
        hz = self._latest_hz
        conf = 1.0 if MIN_HZ <= hz <= MAX_HZ else 0.0
        return PitchReading(hz, conf)

    def close(self) -> None:
        try:
            os.unlink(self._tmp_path)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════
#  Fábrica con los mismos fallbacks que tenía el bucle
# ══════════════════════════════════════════════════════════════════════════
def _build_aubio() -> Detector:
    if not AUBIO_OK:
        log.info("[pitch] aubio no disponible — sin detección")
        return NullDetector()
    return AubioDetector()


def _build_crepe(method: str) -> Detector:
    return CrepeDetector("tiny" if method == "crepe-tiny" else "full")


_BUILDERS = {
    "mpm": MPMDetector,
    "aubio": _build_aubio,
    "crepe-tiny": lambda: _build_crepe("crepe-tiny"),
    "crepe-full": lambda: _build_crepe("crepe-full"),
    "pesto": PestoDetector,
    "pesto-onnx": PestoOnnxDetector,
    "basic-pitch": BasicPitchDetector,
}


def create_detector(method: str, on_engine_label=None) -> Detector:
    """Construye el detector pedido, con fallback a aubio si falla.

    Nunca lanza: si el motor y aubio no están disponibles devuelve un
    :class:`NullDetector` para que el hilo siga capturando sin detección.
    """
    label = on_engine_label or (lambda _: None)
    builder = _BUILDERS.get(method)
    if builder is None:
        log.info(f"[pitch] método desconocido ({method}) → aubio")
        detector = _build_aubio()
    else:
        try:
            detector = builder()
        except Exception as exc:
            log.info(f"[pitch] {method} no disponible ({exc}) → aubio")
            detector = _build_aubio()
    label(detector.label)
    return detector
