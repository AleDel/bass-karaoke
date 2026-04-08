import aubio
import numpy as np
from pydub import AudioSegment

filename = "feet_dont_fail_me_now.mp3"

# 1. Cargar el audio con pydub (que usa tu FFmpeg correctamente)
audio = AudioSegment.from_file(filename)
audio = audio.set_channels(1).set_frame_rate(44100) # Convertir a mono y 44.1kHz
samples = np.array(audio.get_array_of_samples()).astype(np.float32)
# Normalizar a rango [-1, 1] que es lo que espera aubio
samples /= np.iinfo(np.int16).max 

# 2. Configuración de Aubio
samplerate = 44100
#hop_size = 256
#win_s = 512
#Para detectar frecuencias graves (como el bajo de esa canción), necesitas una "ventana" de tiempo más larga. Si la ventana es muy pequeña, las ondas largas no caben y no se detectan.
hop_size = 512
win_s = 1024

onset_detector = aubio.onset("default", win_s, hop_size, samplerate)
#pitch_detector = aubio.pitch("default", win_s, hop_size, samplerate)
pitch_detector = aubio.pitch("mcomb", win_s, hop_size, samplerate)

print(f"Analizando: {filename}...")

# 3. Procesar los samples en bloques (simulando el source de aubio)
for i in range(0, len(samples) - hop_size, hop_size):
    block = samples[i : i + hop_size]
    
    # Detectar Ritmo
    if onset_detector(block):
        print(f"¡Golpe! en segundo: {i / samplerate:.2f}")

    # Detectar Tono
    pitch = pitch_detector(block)[0]
    #if pitch_detector.get_confidence() > 0.8:
    #    print(f"Tono: {pitch:.2f} Hz")
    conf = pitch_detector.get_confidence()
    print(f"Pitch: {pitch:.2f} Hz | Confianza: {conf:.4f}")

print("Análisis finalizado.")