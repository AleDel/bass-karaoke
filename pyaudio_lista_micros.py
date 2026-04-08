import pyaudio

p = pyaudio.PyAudio()
print("--- Dispositivos de Entrada Detectados ---")
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    # Solo mostramos los que tienen canales de entrada
    if info['maxInputChannels'] > 0:
        print(f"ID: {i} - Nombre: {info['name']}")
p.terminate()