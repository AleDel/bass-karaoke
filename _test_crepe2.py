"""
Test CREPE para bajo - tabla simple como el original.
Columnas: Hz_crudo | period | RMS | nota_cruda | Hz_filtrado | nota_final
'<<<' = pasa el umbral; '---' = silencio/ruido descartado
Ctrl+C para salir.
"""
import pyaudio, numpy as np, torch, torchcrepe
from collections import deque

SR          = 44100
CHUNK       = 2048
WIN         = 8192
FMIN        = 32.70
FMAX        = 400.0
RMS_GATE    = 0.008   # por debajo → silencio
CONF_THRESH = 0.10    # period mínimo aceptable
HOLD_MAX    = 6       # frames sin señal antes de limpiar

NOTE_NAMES  = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

def hz2note(hz):
    if hz < 20: return "---"
    midi = round(12 * np.log2(hz / 440.0) + 69)
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"

# ── Dispositivo ─────────────────────────────────────────────────────────
p = pyaudio.PyAudio()
print("\nDispositivos de entrada:")
for i in range(p.get_device_count()):
    d = p.get_device_info_by_index(i)
    if d["maxInputChannels"] > 0:
        print(f"  [{i:>3}] {d['name']}")
idx = int(input("\nDispositivo: "))
stream = p.open(format=pyaudio.paFloat32, channels=1, rate=SR,
                input=True, input_device_index=idx,
                frames_per_buffer=CHUNK)

dev = "cuda" if torch.cuda.is_available() else "cpu"
print(f"\nCREPE-tiny en {dev.upper()}. Toca el bajo. Ctrl+C para salir.\n")
print(f"{'Hz_crudo':>9}  {'period':>6}  {'RMS':>8}  {'nota_cruda':<8}  {'Hz_filtrado':>11}  {'nota_final':<10}  estado")
print("-" * 80)

buf       = np.zeros(WIN, dtype=np.float32)
pitch_buf = deque(maxlen=5)
hold      = 0

try:
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        s    = np.frombuffer(data, dtype=np.float32).copy()
        buf[:-CHUNK] = buf[CHUNK:]
        buf[-CHUNK:] = s

        rms = float(np.sqrt(np.mean(buf ** 2)))

        # ── Silencio ────────────────────────────────────────────────────
        if rms < RMS_GATE:
            hold += 1
            if hold >= HOLD_MAX:
                pitch_buf.clear()
            print(f"{'---':>9}  {'---':>6}  {rms:8.5f}  {'---':<8}  {'---':>11}  {'---':<10}  silencio")
            continue

        # ── CREPE ────────────────────────────────────────────────────────
        t = torch.from_numpy(buf).unsqueeze(0)
        with torch.no_grad():
            freq, period = torchcrepe.predict(
                t, SR,
                hop_length=512,
                fmin=FMIN, fmax=FMAX,
                model="tiny",
                decoder=torchcrepe.decode.weighted_argmax,
                return_periodicity=True,
                device=dev,
                pad=True,
            )
        hz   = float(freq[0, -1].cpu())
        conf = float(period[0, -1].cpu())
        nota_cruda = hz2note(hz)

        # ── Filtro ───────────────────────────────────────────────────────
        if conf > CONF_THRESH and FMIN <= hz <= FMAX:
            pitch_buf.append(hz)
            hold = 0
            estado = "<<<"
        else:
            hold += 1
            estado = "   "

        if pitch_buf and hold < HOLD_MAX:
            hz_med    = float(np.median(list(pitch_buf)))
            nota_fil  = hz2note(hz_med)
            hz_med_s  = f"{hz_med:8.2f}"
        else:
            pitch_buf.clear()
            hz_med_s = "       ---"
            nota_fil = "---"

        print(f"{hz:9.2f}  {conf:6.3f}  {rms:8.5f}  {nota_cruda:<8}  {hz_med_s:>11}  {nota_fil:<10}  {estado}")

except KeyboardInterrupt:
    print("\n\nSaliendo.")
finally:
    stream.stop_stream(); stream.close(); p.terminate()
