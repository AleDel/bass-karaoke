"""
Test PESTO ONNX para bajo - misma tabla que _test_pesto.py pero con inferencia ONNX.
Columnas: Hz_crudo | conf | amp | RMS | nota_cruda | Hz_filtrado | nota_final | estado
'<<<' = pasa umbral; '---' = silencio/ruido descartado
Ctrl+C para salir.

ONNX es stateless -> cache manual entre chunks (igual que el buffer interno de streaming).
Ventaja: latencia ultraestable ~0.7 +/- 0.03ms por inferencia, sin overhead de PyTorch.
Modelo: mir-1k_g7_44100_512.onnx  (SR=44100, chunk=512, batch=1)
"""
import pyaudio
import numpy as np
import onnxruntime as ort
from pathlib import Path

SR          = 44100
CHUNK       = 512                 # ~11.6ms por chunk
AMP_GATE    = 2.0                 # vol_out del ONNX no es 0-1; observados ~5-50, silencio ~0-1
RMS_GATE    = 0.008               # gate rapida de RMS antes de llamar al modelo
CONF_THRESH = 0.30                # confianza minima (0-1)
HOLD_MAX    = 6                   # frames sin seal antes de limpiar buffer
WARMUP      = 8                   # chunks iniciales descartados hasta que el cache CQT se llena
from collections import deque

ONNX_MODEL  = str(Path(__file__).parent.parent / "models" / "mir-1k_g7_44100_512.onnx")

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def hz2note(hz):
    if hz < 20:
        return "---"
    midi = round(12 * np.log2(hz / 440.0) + 69)
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"

# ── Dispositivo audio ─────────────────────────────────────────────────────────
p = pyaudio.PyAudio()
print("\nDispositivos de entrada:")
for i in range(p.get_device_count()):
    d = p.get_device_info_by_index(i)
    if d["maxInputChannels"] > 0:
        print(f"  [{i:>3}] {d['name']}")
idx = int(input("\nDispositivo: "))
stream = p.open(
    format=pyaudio.paFloat32,
    channels=1,
    rate=SR,
    input=True,
    input_device_index=idx,
    frames_per_buffer=CHUNK,
)

# ── PESTO ONNX session ────────────────────────────────────────────────────────
# Forzar CPU: el nodo ScatterND del cache CQT causa cudaErrorIllegalAddress en CUDA EP
session = ort.InferenceSession(ONNX_MODEL, providers=["CPUExecutionProvider"])
ep = "CPUExecutionProvider"

cache_size = session.get_inputs()[1].shape[1]
cache_state = np.zeros((1, cache_size), dtype=np.float32)

print(f"\nPESTO ONNX cargado  --  EP={ep}  chunk={CHUNK}  cache={cache_size}  SR={SR}")
print("Modelo listo. Toca el bajo. Ctrl+C para salir.\n")

print(
    f"{'Hz_crudo':>9}  {'conf':>5}  {'amp':>8}  {'RMS':>8}  "
    f"{'nota_cruda':<8}  {'Hz_filtrado':>11}  {'nota_final':<10}  estado"
)
print("-" * 92)

pitch_buf  = deque(maxlen=5)
hold       = 0
warmup_cnt = 0          # contador de arranque

# Tabla de armonicos para bajo: si detectamos el 2do o 3er armonico de una nota
# de bajo y esa nota raiz esta en rango de bajo, bajamos la octava.
# Cubre: 2do arm. (octava arriba) y 3er arm. (quinta dos octavas arriba).
BASSLO, BASSHI = 28.0, 110.0   # rango de fundamentales de bajo

def reduce_harmonic(hz):
    """Si hz podria ser el 2do o 3er armonico de un bajo, devuelve el fundamental."""
    for divisor in (2, 3):
        root = hz / divisor
        if BASSLO <= root <= BASSHI:
            return root
    return hz

try:
    while True:
        data  = stream.read(CHUNK, exception_on_overflow=False)
        chunk = np.frombuffer(data, dtype=np.float32).copy()

        rms = float(np.sqrt(np.mean(chunk ** 2)))

        # ── Gate rapida de RMS (evita llamar al modelo en silencio) ──────────
        if rms < RMS_GATE:
            hold += 1
            if hold >= HOLD_MAX:
                pitch_buf.clear()
            print(
                f"{'---':>9}  {'---':>5}  {'---':>8}  {rms:8.5f}  "
                f"{'---':<8}  {'---':>11}  {'---':<10}  silencio"
            )
            continue

        # ── ONNX inferencia: audio + cache -> pred, conf, vol, act, cache_out ─
        audio_in = chunk[np.newaxis, :]   # (1, 512)
        outputs = session.run(
            None,
            {"audio": audio_in, "cache": cache_state}
        )
        pred, conf_out, vol_out, _act, cache_out = outputs
        cache_state = cache_out            # actualizar cache para el siguiente frame

        # Descartar primeros chunks hasta que el cache CQT este caliente
        warmup_cnt += 1
        if warmup_cnt <= WARMUP:
            print(f"{'---':>9}  {'---':>5}  {'---':>8}  {rms:8.5f}  "
                  f"{'---':<8}  {'---':>11}  {'---':<10}  warmup")
            continue

        # PESTO ONNX devuelve MIDI fraccionario (igual que PyTorch sin convert_to_freq).
        # Aplicar la misma conversion que model.py L264: hz = 440 * 2**((midi-69)/12)
        midi = float(pred.flat[0])
        hz   = 440.0 * 2.0 ** ((midi - 69.0) / 12.0)
        conf = float(conf_out.flat[0])
        amp  = float(vol_out.flat[0])

        # Reduccion de armonicos: si el modelo devuelve el 2do o 3er armonico
        # de un bajo (p.ej. B2=123Hz en vez de E1=41Hz), bajar al fundamental.
        hz_red = reduce_harmonic(hz)
        nota_cruda = hz2note(hz_red)

        # ── Filtro: amp + conf + rango de Hz ─────────────────────────────────
        if amp >= AMP_GATE and conf >= CONF_THRESH and 28.0 <= hz_red <= 400.0:
            hz = hz_red   # usar el fundamental corregido
            pitch_buf.append(hz)  # hz ya es el fundamental si fue reducido
            hold  = 0
            estado = "<<<"
        else:
            hold += 1
            estado = "   "

        if pitch_buf and hold < HOLD_MAX:
            hz_med   = float(np.median(list(pitch_buf)))
            nota_fil = hz2note(hz_med)
            hz_med_s = f"{hz_med:8.2f}"
        else:
            pitch_buf.clear()
            hz_med_s = "       ---"
            nota_fil = "---"

        print(
            f"{hz:9.2f}  {conf:5.3f}  {amp:8.5f}  {rms:8.5f}  "
            f"{nota_cruda:<8}  {hz_med_s:>11}  {nota_fil:<10}  {estado}"
        )

except KeyboardInterrupt:
    print("\n\nSaliendo.")
finally:
    stream.stop_stream()
    stream.close()
    p.terminate()
