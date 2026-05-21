"""
Test PESTO streaming para bajo - tabla igual que _test_crepe2.py.
Columnas: Hz_crudo | conf | RMS | nota_cruda | Hz_filtrado | nota_final | estado
'<<<' = pasa umbral; '---' = silencio/ruido descartado
Ctrl+C para salir.

Con streaming=True PESTO mantiene internamente el ring buffer CQT.
Cada chunk de 2048 muestras (~46ms) produce exactamente 1 estimacion.
Sin anillo manual: mucho mas sencillo y menor latencia.

Instalacion requerida (git master para tener utils/):
  Copiar pesto_git/pesto/utils/ -> site-packages/pesto/utils/  (ya hecho)
"""
import pyaudio
import numpy as np
import torch
from pesto import load_model
from collections import deque

SR          = 44100
CHUNK       = 512                 # ~11.6ms por chunk (vs 2048=46ms) -> menor latencia
STEP_MS     = CHUNK / SR * 1000   # ~11.61 ms
AMP_GATE    = 1e-5                # umbral de amplitud CQT de PESTO (calibrar mirando columna 'amp' en silencio)
RMS_GATE    = 0.008               # gate de RMS adicional (primer filtro rapido)
CONF_THRESH = 0.30                # confianza minima PESTO (0-1)
HOLD_MAX    = 6                   # frames sin seal antes de limpiar

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def hz2note(hz):
    if hz < 20:
        return "---"
    midi = round(12 * np.log2(hz / 440.0) + 69)
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"

# ── Dispositivo ──────────────────────────────────────────────────────────────
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

# ── PESTO modelo en modo streaming ───────────────────────────────────────────
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"\nCargando PESTO (mir-1k_g7, streaming) en {str(dev).upper()} -- {STEP_MS:.1f}ms/chunk ...")
pesto_model = load_model(
    "mir-1k_g7",
    step_size=STEP_MS,
    sampling_rate=SR,
    streaming=True,
    max_batch_size=1,
).to(dev)
pesto_model.eval()
print("Modelo listo. Toca el bajo. Ctrl+C para salir.\n")

print(
    f"{'Hz_crudo':>9}  {'conf':>5}  {'amp':>8}  {'RMS':>8}  "
    f"{'nota_cruda':<8}  {'Hz_filtrado':>11}  {'nota_final':<10}  estado"
)
print("-" * 92)

pitch_buf = deque(maxlen=5)
hold = 0

try:
    while True:
        data  = stream.read(CHUNK, exception_on_overflow=False)
        chunk = np.frombuffer(data, dtype=np.float32).copy()

        rms = float(np.sqrt(np.mean(chunk ** 2)))

        # ── Silencio (gate rapida por RMS antes de llamar al modelo) ─────────
        if rms < RMS_GATE:
            hold += 1
            if hold >= HOLD_MAX:
                pitch_buf.clear()
            print(
                f"{'---':>9}  {'---':>5}  {'---':>8}  {rms:8.5f}  "
                f"{'---':<8}  {'---':>11}  {'---':<10}  silencio"
            )
            continue

        # ── PESTO streaming: (1, CHUNK) -> (1, 1) ────────────────────────────
        x = torch.from_numpy(chunk).unsqueeze(0).to(dev)
        with torch.no_grad():
            f0, conf_t, amp_t = pesto_model(x, convert_to_freq=True, return_activations=False)

        hz   = float(f0.flatten()[-1].cpu())
        conf = float(conf_t.flatten()[-1].cpu())
        amp  = float(amp_t.flatten()[-1].cpu())   # amplitud CQT interna de PESTO
        nota_cruda = hz2note(hz)

        # ── Filtro: gate por amplitud PESTO + umbral de confianza ────────────
        if amp >= AMP_GATE and conf >= CONF_THRESH and 28.0 <= hz <= 400.0:
            pitch_buf.append(hz)
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
