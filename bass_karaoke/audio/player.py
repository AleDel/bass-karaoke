"""
Reproductor de audio con time-stretch (librosa + sounddevice).
Permite cambiar el tempo sin alterar el tono (pitch-preserving).
"""
import threading
import os
import numpy as np

from ..config import SAMPLERATE

try:
    import librosa
    import sounddevice as sd
    VARSPEED_OK = True
except ImportError:
    VARSPEED_OK = False


class VarispeedPlayer:
    """
    Carga el MP3 con librosa y lo reproduce con time stretching
    (librosa.effects.time_stretch). El estiramiento se aplica en un hilo
    de fondo; mientras procesa la UI muestra "(estirando…)".
    """

    def __init__(self):
        self.data_orig      = None   # audio original (frames, 2) float32
        self.data           = None   # audio con time-stretch aplicado
        self.sr             = SAMPLERATE
        self.pos            = 0.0   # posición en frames dentro de self.data
        self._applied_ratio = 1.0
        self._target_ratio  = 1.0
        self.volume         = 1.0
        self._playing       = False
        self._lock          = threading.Lock()
        self._stream        = None
        self._loaded        = False
        self.stretching     = False  # True mientras procesa (para la UI)

    def load(self, path: str) -> bool:
        if not VARSPEED_OK:
            return False
        try:
            y, sr = librosa.load(path, sr=SAMPLERATE, mono=False)
            if y.ndim == 1:
                y = np.stack([y, y], axis=1)
            else:
                y = y.T                           # (ch, frames) → (frames, ch)
            arr = y.astype(np.float32)
            self.data_orig      = arr
            self.data           = arr
            self._applied_ratio = 1.0
            self._target_ratio  = 1.0
            self.sr             = SAMPLERATE
            self._loaded        = True
            dur = len(arr) / SAMPLERATE
            print(f"[TimeStretch] {os.path.basename(path)}  {dur:.1f}s  frames={len(arr)}")
            return True
        except Exception as e:
            print(f"[TimeStretch ERROR al cargar] {e}")
            return False

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            if not self._playing or self.data is None:
                outdata[:] = 0
                return
            start = int(self.pos)
            end   = start + frames
            if start >= len(self.data):
                outdata[:] = 0
                self._playing = False
                return
            end   = min(end, len(self.data))
            chunk = self.data[start:end]
            if len(chunk) == 0:
                outdata[:] = 0
                return
            if len(chunk) < frames:
                out = np.zeros((frames, 2), dtype=np.float32)
                out[:len(chunk)] = chunk
            else:
                out = chunk
            outdata[:] = (out * self.volume).reshape(outdata.shape)
            self.pos += frames

    def play(self, offset_sec: float = 0.0):
        if not self._loaded:
            return
        self.stop()
        with self._lock:
            self.pos      = max(0.0, offset_sec * self.sr / max(self._applied_ratio, 0.01))
            self._playing = True
        self._stream = sd.OutputStream(
            samplerate=self.sr, channels=2,
            dtype='float32', blocksize=512,
            callback=self._callback)
        self._stream.start()

    def pause(self):
        with self._lock:
            self._playing = False

    def resume(self):
        with self._lock:
            self._playing = True
        if self._stream is None or not self._stream.active:
            self._stream = sd.OutputStream(
                samplerate=self.sr, channels=2,
                dtype='float32', blocksize=512,
                callback=self._callback)
            self._stream.start()

    def stop(self):
        with self._lock:
            self._playing = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        with self._lock:
            self.pos = 0.0

    def set_speed(self, ratio: float):
        ratio = max(0.3, min(2.5, float(ratio)))
        self._target_ratio = ratio
        if abs(ratio - self._applied_ratio) < 0.005:
            return
        t = threading.Thread(target=self._apply_stretch, args=(ratio,), daemon=True)
        t.start()

    def _apply_stretch(self, ratio: float):
        if self.data_orig is None or self.stretching:
            return
        self.stretching = True
        try:
            orig = self.data_orig
            print(f"[TimeStretch] aplicando rate={ratio:.3f}  ({ratio:.0%} tempo)  …")
            ch0 = librosa.effects.time_stretch(orig[:, 0], rate=ratio)
            ch1 = librosa.effects.time_stretch(orig[:, 1], rate=ratio)
            new_data = np.stack([ch0, ch1], axis=1).astype(np.float32)
            with self._lock:
                old_ratio = self._applied_ratio
                new_pos   = self.pos * old_ratio / ratio if ratio > 0 else 0.0
                self.data           = new_data
                self._applied_ratio = ratio
                self.pos            = max(0.0, min(new_pos, len(new_data) - 1))
            print(f"[TimeStretch] listo  frames={len(new_data)}  dur={len(new_data)/self.sr:.1f}s")
        except Exception as e:
            print(f"[TimeStretch ERROR] {e}")
        finally:
            self.stretching = False
            if abs(self._target_ratio - self._applied_ratio) > 0.005:
                self._apply_stretch(self._target_ratio)

    def set_volume(self, v: float):
        with self._lock:
            self.volume = max(0.0, min(1.0, float(v)))

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._playing
