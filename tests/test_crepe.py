"""
Afinador cromático en terminal usando CREPE (torchcrepe).
Muestra: nota, cents de desafinación y barra visual en tiempo real.
"""
import os, sys, time
import pyaudio
import numpy as np
import torch
import torchcrepe
from collections import deque

SR         = 44100
CHUNK      = 2048
WIN        = 8192
FMIN       = 32.70
FMAX       = 400.0
RMS_GATE   = 0.005
CONF_THRESH = 0.10
NOTE_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
# Notas al aire del bajo 4 cuerdas (referencia rápida)
OPEN_STRINGS = {41.20: "E1 (4ª)", 55.00: "A1 (3ª)", 73.42: "D2 (2ª)", 98.00: "G2 (1ª)"}

def hz2midi(hz):
    return 12 * np.log2(hz / 440.0) + 69

def hz2note(hz):
    midi = round(hz2midi(hz))
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}", midi

def cents_bar(cents, width=40):
    """Barra ASCII: '|' en centro, aguja '█', zona verde ±15c."""
    half = width // 2
    pos  = int(np.clip(cents / 50.0 * half, -half, half))
    bar  = ["-"] * width
    bar[half] = "|"
    needle = half + pos
    bar[needle] = "█"
    # Zona verde ±15 cents (±15/50*half px)
    zone = max(1, int(15 / 50 * half))
    for i in range(half - zone, half + zone + 1):
        if 0 <= i < width and bar[i] == "-":
            bar[i] = "·"
    return "".join(bar)

def color(text, code):
    """ANSI color si el terminal lo soporta."""
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text

GREEN  = "32"
YELLOW = "33"
RED    = "31"
CYAN   = "36"
GRAY   = "90"

# ── Selección de dispositivo ────────────────────────────────────────────
p = pyaudio.PyAudio()
print("\nDispositivos de entrada:")
for i in range(p.get_device_count()):
    d = p.get_device_info_by_index(i)
    if d["maxInputChannels"] > 0:
        print(f"  [{i:>3}] {d['name']}")

idx = int(input("\nDispositivo (número): "))
stream = p.open(format=pyaudio.paFloat32, channels=1, rate=SR,
                input=True, input_device_index=idx,
                frames_per_buffer=CHUNK)

dev = "cuda" if torch.cuda.is_available() else "cpu"
print(f"\nCREPE-tiny en {dev.upper()}. Toca notas del bajo. Ctrl+C para salir.\n")

print(color("Referencia cuerdas al aire:", CYAN))
for hz, name in OPEN_STRINGS.items():
    n, _ = hz2note(hz)
    print(color(f"  {name:10s}  {n}  ({hz:.2f} Hz)", GRAY))
print()

buf       = np.zeros(WIN, dtype=np.float32)
pitch_buf = deque(maxlen=5)
hold      = 0
HOLD_MAX  = 6

try:
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        s    = np.frombuffer(data, dtype=np.float32).copy()
        buf[:-CHUNK] = buf[CHUNK:]
        buf[-CHUNK:] = s

        rms = float(np.sqrt(np.mean(buf ** 2)))
        if rms < RMS_GATE:
            hold += 1
            if hold >= HOLD_MAX:
                pitch_buf.clear()
                print(f"\r  {color('--- silencio ---', GRAY):<55}", end="", flush=True)
            continue

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

        if conf > CONF_THRESH and FMIN <= hz <= FMAX:
            pitch_buf.append(hz)
            hold = 0
        else:
            hold += 1

        if pitch_buf and hold < HOLD_MAX:
            hz_med  = float(np.median(list(pitch_buf)))
            nota, _ = hz2note(hz_med)
            midi_f  = hz2midi(hz_med)
            midi_r  = round(midi_f)
            cents   = (midi_f - midi_r) * 100

            # Color según afinación
            if abs(cents) < 8:
                col = GREEN;  tune = "AFINADO  "
            elif abs(cents) < 20:
                col = YELLOW; tune = f"{cents:+.1f}c  "
            else:
                col = RED;    tune = f"{cents:+.1f}c  "

            bar   = cents_bar(cents)
            hz_ref = 440.0 * 2 ** ((midi_r - 69) / 12)

            line = (f"  {color(nota, col):>6}  "
                    f"{hz_med:6.2f}Hz  "
                    f"[{color(bar, col)}]  "
                    f"{color(tune, col)}"
                    f"  period={conf:.2f}  rms={rms:.4f}")
            print(f"\r{line:<100}", end="", flush=True)

except KeyboardInterrupt:
    print("\n\nSaliendo...")
finally:
    stream.stop_stream()
    stream.close()
    p.terminate()
