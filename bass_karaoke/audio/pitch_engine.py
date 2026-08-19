"""
Motor de detección de pitch en tiempo real.

La clase PitchEngine arranca un hilo de audio que captura del micrófono,
aplica el método de pitch seleccionado y llama al callback on_update(hz, note).
"""
import os
import math
import threading
import numpy as np
from collections import deque, Counter

from ..config import (
    SAMPLERATE, CHUNK_SIZE, WIN_S, HOP_S, CONF_THRESH,
    PITCH_HOLD_FRAMES, MIN_HZ, MAX_HZ, PESTO_ONNX_PATH,
    LOWPASS_HZ, HIGHPASS_HZ, AUBIO_METHOD, AUBIO_FFTSIZE, AUBIO_TOLERANCE,
    AUBIO_CONF_THRESH, AUBIO_SILENCE_DB, BASS_MAX_HZ,
    MPM_WIN, MPM_THRESHOLD,
)
from ..utils import hz_to_note_name

try:
    import aubio as _aubio_mod
    AUBIO_OK = True
except ImportError:
    AUBIO_OK = False

try:
    import pyaudio as _pyaudio_mod
    PA_OK = True
except ImportError:
    PA_OK = False

try:
    from scipy.signal import butter as _sci_butter, sosfilt as _sci_sosfilt
    SCIPY_OK = True
except ImportError:
    SCIPY_OK = False

PITCH_AVAILABLE = AUBIO_OK and PA_OK


def enumerate_devices():
    """Devuelve lista de (device_idx, name) de dispositivos de entrada disponibles."""
    if not PA_OK:
        return []
    p = _pyaudio_mod.PyAudio()
    devices = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            devices.append((i, info["name"]))
    p.terminate()
    return devices


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
        a  = 0.5 * (y0 - 2.0 * y1 + y2)
        b  = 0.5 * (y2 - y0)
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
        self._running        = False
        self._thread         = None

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.5):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # ─────────────────────────────────────────────────────────────────────────
    def _loop(self):
        if not PA_OK:
            return

        method = self.method

        _torch = _tc = _pesto_model = _ort_session = _pesto_cache = None
        _pitch_o = None
        _rms_gate    = 0.008
        _conf_thresh = 0.20
        _chunk_audio = CHUNK_SIZE
        _win         = WIN_S
        _bp_tmppath  = None

        # ── Inicializar motor ─────────────────────────────────────────────────
        if method in ("crepe-tiny", "crepe-full"):
            try:
                import torch as _torch
                import torchcrepe as _tc
                _dev = "cuda" if _torch.cuda.is_available() else "cpu"
                _model_size = "tiny" if method == "crepe-tiny" else "full"
                print(f"[pitch] CREPE-{_model_size} ({_dev})")
                self.on_engine_label(f"CREPE-{_model_size} ({_dev.upper()})")
                _conf_thresh = 0.18
            except ImportError:
                print("[pitch] torchcrepe no disponible → aubio")
                method = "aubio"

        if method == "pesto":
            try:
                import torch as _torch
                from pesto import load_model as _pesto_load
                _dev = "cuda" if _torch.cuda.is_available() else "cpu"
                _step_ms = CHUNK_SIZE / SAMPLERATE * 1000
                print(f"[pitch] PESTO streaming ({_dev})  step={_step_ms:.1f}ms")
                self.on_engine_label(f"PESTO ({_dev.upper()})")
                _pesto_model = _pesto_load(
                    "mir-1k_g7",
                    step_size=_step_ms,
                    sampling_rate=SAMPLERATE,
                    streaming=True,
                    max_batch_size=1,
                ).to(_dev)
                _pesto_model.eval()
                _pesto_dtype = next(_pesto_model.parameters()).dtype
                _chunk_audio = CHUNK_SIZE
                _conf_thresh = 0.30
            except Exception as _e:
                print(f"[pitch] PESTO no disponible ({_e}) → aubio")
                method = "aubio"

        if method == "pesto-onnx":
            try:
                import onnxruntime as _ort
                if not os.path.exists(PESTO_ONNX_PATH):
                    raise FileNotFoundError(f"Modelo ONNX no encontrado: {PESTO_ONNX_PATH}")
                _ort_session = _ort.InferenceSession(
                    PESTO_ONNX_PATH, providers=["CPUExecutionProvider"])
                _cache_size  = _ort_session.get_inputs()[1].shape[1]
                _pesto_cache = np.zeros((1, _cache_size), dtype=np.float32)
                _chunk_audio = 512
                _conf_thresh = 0.30
                _pesto_onnx_warmup = 8
                _pesto_onnx_cnt    = 0
                print(f"[pitch] PESTO-ONNX  cache={_cache_size}  chunk={_chunk_audio}")
                self.on_engine_label("PESTO-ONNX (CPU)")
            except Exception as _e:
                print(f"[pitch] PESTO-ONNX no disponible ({_e}) → aubio")
                method = "aubio"

        if method == "aubio":
            if AUBIO_OK:
                _pitch_o = _aubio_mod.pitch(AUBIO_METHOD, AUBIO_FFTSIZE, HOP_S, SAMPLERATE)
                _pitch_o.set_unit("Hz")
                _pitch_o.set_tolerance(AUBIO_TOLERANCE)
                _pitch_o.set_silence(AUBIO_SILENCE_DB)
                _conf_thresh = AUBIO_CONF_THRESH
                print(f"[pitch] aubio {AUBIO_METHOD}  fft={AUBIO_FFTSIZE}  "
                      f"tol={AUBIO_TOLERANCE}  conf>{AUBIO_CONF_THRESH}")
                self.on_engine_label(f"aubio {AUBIO_METHOD}")
            else:
                print("[pitch] aubio no disponible — sin detección")
                self.on_engine_label("sin pitch")

        if method == "basic-pitch":
            try:
                import soundfile as _sf
                import tempfile as _tmpmod
                os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
                from basic_pitch.inference import predict as _bp_predict, Model as _BP_Model
                import pathlib as _pl
                _bp_onnx = None
                try:
                    import basic_pitch as _bp_pkg
                    _pkg_dir = _pl.Path(_bp_pkg.__file__).parent
                    _onnx_candidate = _pkg_dir / "saved_models" / "icassp_2022" / "nmp.onnx"
                    if _onnx_candidate.exists():
                        _bp_onnx = str(_onnx_candidate)
                except Exception:
                    pass
                if _bp_onnx:
                    _bp_model = _BP_Model(_bp_onnx)
                    print(f"[pitch] Basic Pitch ONNX  {_bp_onnx}")
                else:
                    from basic_pitch import ICASSP_2022_MODEL_PATH as _BP_MODEL_PATH
                    _bp_model = _BP_Model(_BP_MODEL_PATH)
                    print("[pitch] Basic Pitch (runtime por defecto)")
                _bp_buf_sec    = 1.5
                _bp_buf_n      = int(_bp_buf_sec * SAMPLERATE)
                _bp_buf        = np.zeros(_bp_buf_n, dtype=np.float32)
                _bp_hop_chunks = max(1, int(0.5 * SAMPLERATE / CHUNK_SIZE))
                _bp_chunk_cnt  = 0
                _bp_latest_hz  = 0.0
                _bp_tmp        = _tmpmod.NamedTemporaryFile(suffix='.wav', delete=False)
                _bp_tmppath    = _bp_tmp.name
                _bp_tmp.close()
                self.on_engine_label("Basic Pitch (ONNX)")
            except Exception as _e:
                print(f"[pitch] basic-pitch no disponible ({_e}) → aubio")
                method = "aubio"

        # ── Bucle de captura ─────────────────────────────────────────────────
        audio_buf = np.zeros(_win, dtype=np.float32)
        mpm_buf   = np.zeros(MPM_WIN, dtype=np.float32)
        pitch_buf = deque(maxlen=9)
        hold_count = 0
        _debug_cnt  = 0
        _prefilter, _pf_state = _build_prefilter(SAMPLERATE)
        print(f"[pitch] pre-filtro HP {HIGHPASS_HZ:.0f} Hz + LP {LOWPASS_HZ:.0f} Hz"
              + ("  (scipy)" if SCIPY_OK else "  (biquads numpy)"))

        p = _pyaudio_mod.PyAudio()
        try:
            stream = p.open(
                format=_pyaudio_mod.paFloat32, channels=1, rate=SAMPLERATE,
                input=True, input_device_index=self.device_id,
                frames_per_buffer=_chunk_audio)

            while self._running:
                try:
                    data    = stream.read(_chunk_audio, exception_on_overflow=False)
                    samples = np.frombuffer(data, dtype=np.float32).copy()
                    rms     = float(np.sqrt(np.mean(samples ** 2)))

                    # Pre-filtrado: quita rumble/DC y armónicos altos que
                    # desvían la detección a la octava superior.
                    samples = _prefilter(samples)

                    # Gate de silencio
                    if rms < 0.008:
                        hold_count += 1
                        if hold_count >= PITCH_HOLD_FRAMES:
                            pitch_buf.clear()
                            self.on_update(0.0, "—", 0.0, "—")
                        continue

                    pitch = 0.0
                    conf  = 0.0

                    if method in ("crepe-tiny", "crepe-full"):
                        audio_buf[:-_chunk_audio] = audio_buf[_chunk_audio:]
                        audio_buf[-_chunk_audio:] = samples
                        audio_t = _torch.from_numpy(audio_buf).unsqueeze(0).float()
                        with _torch.no_grad():
                            freq, period = _tc.predict(
                                audio_t, SAMPLERATE,
                                hop_length=512,
                                fmin=32.70, fmax=MAX_HZ,
                                model=_model_size,
                                decoder=_tc.decode.weighted_argmax,
                                return_periodicity=True,
                                device=_dev,
                                pad=True,
                            )
                        pitch = float(freq[0, -1].cpu())
                        conf  = float(period[0, -1].cpu())

                    elif method == "pesto":
                        x = _torch.from_numpy(samples).unsqueeze(0).to(
                            device=_dev, dtype=_pesto_dtype)
                        with _torch.no_grad():
                            f0, conf_t, amp_t = _pesto_model(
                                x, convert_to_freq=True, return_activations=False)
                        pitch = float(f0.flatten()[-1].cpu())
                        conf  = float(conf_t.flatten()[-1].cpu())
                        amp   = float(amp_t.flatten()[-1].cpu())
                        if amp < 1e-5:
                            conf = 0.0
                        pitch = _octave_to_bass_range(pitch)

                    elif method == "pesto-onnx":
                        _pesto_onnx_cnt += 1
                        outs = _ort_session.run(
                            None,
                            {"audio":  samples[np.newaxis, :],
                             "cache":  _pesto_cache})
                        pred_midi, conf_o, vol_o, _, cache_out = outs
                        _pesto_cache = cache_out
                        if _pesto_onnx_cnt <= _pesto_onnx_warmup:
                            continue
                        pitch = 440.0 * 2.0 ** ((float(pred_midi.flat[0]) - 69.0) / 12.0)
                        conf  = float(conf_o.flat[0])
                        amp   = float(vol_o.flat[0])
                        if amp < 2.0:
                            conf = 0.0
                        pitch = _octave_to_bass_range(pitch)

                    elif method == "aubio":
                        pitch = float(_pitch_o(samples)[0])
                        conf  = float(_pitch_o.get_confidence())

                    elif method == "mpm":
                        mpm_buf[:-_chunk_audio] = mpm_buf[_chunk_audio:]
                        mpm_buf[-_chunk_audio:] = samples
                        pitch, conf = _mpm_pitch(
                            mpm_buf, SAMPLERATE, MIN_HZ, MAX_HZ, MPM_THRESHOLD)

                    elif method == "basic-pitch":
                        _bp_buf[:-_chunk_audio] = _bp_buf[_chunk_audio:]
                        _bp_buf[-_chunk_audio:] = samples
                        _bp_chunk_cnt += 1
                        if _bp_chunk_cnt >= _bp_hop_chunks:
                            _bp_chunk_cnt = 0
                            try:
                                _sf.write(_bp_tmppath, _bp_buf, SAMPLERATE)
                                _, _, note_events = _bp_predict(_bp_tmppath, _bp_model)
                                win_start = _bp_buf_sec - 0.5
                                recent = [n for n in note_events if n[0] >= win_start]
                                if recent:
                                    best = max(recent, key=lambda n: n[3])
                                    midi_n = float(best[2])
                                    _bp_latest_hz = 440.0 * 2.0 ** ((midi_n - 69.0) / 12.0)
                                else:
                                    _bp_latest_hz = 0.0
                            except Exception as _bp_e:
                                print(f"[basic-pitch] {_bp_e}")
                        pitch = _bp_latest_hz
                        conf  = 1.0 if (MIN_HZ <= pitch <= MAX_HZ) else 0.0

                    # ── Filtro y buffer ───────────────────────────────────────
                    _debug_cnt += 1
                    if _debug_cnt % 15 == 0:
                        self.on_debug(pitch, conf, method)

                    if conf > _conf_thresh:
                        folded = _octave_to_bass_range(pitch)
                        if MIN_HZ <= folded <= MAX_HZ:
                            pitch_buf.append(folded)
                            hold_count = 0
                        else:
                            hold_count += 1
                    else:
                        hold_count += 1

                    if pitch_buf and hold_count < PITCH_HOLD_FRAMES:
                        det_hz   = float(np.median(list(pitch_buf)))
                        det_note = hz_to_note_name(det_hz)

                        midi_votes = [int(round(12 * math.log2(h / 440) + 69))
                                      for h in pitch_buf if h > MIN_HZ]
                        stb_hz, stb_note = 0.0, "—"
                        if midi_votes:
                            counts = Counter(midi_votes)
                            top_midi, top_count = counts.most_common(1)[0]
                            if top_count >= len(pitch_buf) * 0.55:
                                matching = [h for h in pitch_buf
                                            if int(round(12 * math.log2(h / 440) + 69)) == top_midi]
                                stb_hz   = float(np.median(matching))
                                stb_note = hz_to_note_name(stb_hz)
                        self.on_update(det_hz, det_note, stb_hz, stb_note)
                    else:
                        pitch_buf.clear()
                        self.on_update(0.0, "—", 0.0, "—")

                except Exception as _e:
                    print(f"[audio loop] {_e}")
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            p.terminate()
            if _bp_tmppath:
                try:
                    os.unlink(_bp_tmppath)
                except Exception:
                    pass
