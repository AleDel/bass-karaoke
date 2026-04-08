import aubio
import numpy as np
import pyaudio

# --- CONFIGURACIÓN ---
ID_DISPOSITIVO = 3  # usar el script pyaudio_lista_micros.py para ver id de dispositivos
CHANNELS = 1
SAMPLERATE = 44100
CHUNK_SIZE = 2048   
WIN_S = 4096        # Ventana grande para detectar el Mi grave (41Hz)
HOP_S = CHUNK_SIZE

def hz_to_note(hz):
    if hz < 10: return "---"
    # Relación matemática entre frecuencia y notas MIDI
    # MIDI = 69 + 12 * log2(Hz / 440)
    midi = 12 * np.log2(hz / 440.0) + 69
    midi = int(np.round(midi))
    
    nombres = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    nombre_nota = nombres[midi % 12]
    octava = (midi // 12) - 1
    return f"{nombre_nota}{octava}"

# Inicializar detector
pitch_detector = aubio.pitch("yinfast", WIN_S, HOP_S, SAMPLERATE)
pitch_detector.set_unit("Hz")
pitch_detector.set_tolerance(0.8) 

p = pyaudio.PyAudio()

try:
    stream = p.open(
        format=pyaudio.paFloat32,
        channels=CHANNELS,
        rate=SAMPLERATE,
        input=True,
        input_device_index=ID_DISPOSITIVO,
        frames_per_buffer=CHUNK_SIZE
    )

    print(f"*** Identificador de Notas (Bajo) en ID {ID_DISPOSITIVO} ***")

    while True:
        data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        samples = np.frombuffer(data, dtype=np.float32)
        
        pitch = pitch_detector(samples)[0]
        confidence = pitch_detector.get_confidence()

        if confidence > 0.6 and pitch > 30: # 30Hz es el límite inferior útil
            nota_musical = hz_to_note(pitch)
            print(f"Nota: {nota_musical:4} | Frec: {pitch:7.2f} Hz | Conf: {confidence:.2f}")
            
except KeyboardInterrupt:
    print("\nDetenido.")
finally:
    if 'stream' in locals():
        stream.stop_stream()
        stream.close()
    p.terminate()