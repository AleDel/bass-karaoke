# Bass Karaoke

**Bass Karaoke** es una aplicación de karaoke para bajo eléctrico con scroll de tablatura en tiempo real, detección de pitch y visualización de partitura.

Basada en la canción *Feet Don't Fail Me Now* — Joy Crookes | Bajo: Dayna Fisher.

---

## Instalación

```bash
pip install -r requirements.txt
```

Si `aubio` da error en Windows:

```bash
pip install pygame sounddevice numpy
pip install aubio --find-links https://github.com/aubio/aubio/releases
```

Alternativa si `aubio` no instala (más pesado pero funciona):

```bash
pip install crepe
```

---

## Uso

1. Pon tu MP3 de la canción en la carpeta raíz del proyecto  
   → Nómbralo `feet_dont_fail_me_now.mp3` (o cualquier nombre, lo detecta automático)

2. Conecta tu bajo al ordenador (interfaz de audio USB/Jack)  
   → Asegúrate de que Windows lo reconoce como entrada de micrófono

3. Ejecuta:

```bash
python bass_karaoke_v3.py
```

---

## Controles

| Tecla | Acción |
|---|---|
| `ESPACIO` | Play / Pausa (con countdown 4-3-2-1) |
| `C` | Activar/desactivar countdown |
| `R` | Reiniciar |
| `← / →` | Compás anterior / siguiente |
| `↑ / ↓` | Tempo ±5 BPM |
| `, / .` | Offset MP3 ±0.05 s (fino) |
| `Shift + , / .` | Offset MP3 ±0.5 s (grueso) |
| `D` | Selector de dispositivo de audio |
| `P` | Selector de método de pitch |
| `S` | Cambiar renderer partitura (Verovio ↔ Music21) |
| `M` | Silenciar/activar MP3 |
| `T` | Afinador |
| `F5` | Guardar configuración |
| `ESC` | Salir |

---

## Cómo funciona

- La tablatura desfila de derecha a izquierda
- La línea dorada vertical = nota que debes tocar ahora
- El número grande en el panel izquierdo = traste a pulsar
- Colores de cuerda: E=rojo, A=amarillo, D=azul, G=verde

**Colores de la nota actual:**
- **Amarillo** — esperando tu input
- **Verde** — ¡correcto! nota bien tocada
- **Rojo** — nota incorrecta

**Panel de pitch (derecha):**  
Muestra la nota que estás tocando en tiempo real. La barra horizontal indica si estás alto/bajo de afinación. Score en % = precisión general.

---

## Requisitos de audio

- Una interfaz de audio (Focusrite, Behringer, etc.)
- O cable bajo → jack 3.5mm → entrada micrófono del PC
- En Windows: Panel de Control → Sonido → selecciona tu interfaz

---

## Estructura del proyecto

```
bass_karaoke/      → paquete principal
bass_karaoke_v3.py → punto de entrada
models/            → modelos de detección de pitch (ONNX)
assets/            → recursos estáticos (glyphnames, etc.)
songs/             → canciones de ejemplo (MusicXML, TG, MIDI)
tests/             → scripts de prueba de los detectores de pitch
scripts/           → utilidades (listar dispositivos de audio, etc.)
requirements.txt
```

---

## Solución de problemas

**`No module named aubio`**  
→ `pip install aubio`  
→ Si falla, la app funciona igual pero sin reconocimiento de pitch

**`PortAudio library not found`**  
→ `pip install sounddevice --upgrade`  
→ O reinstala: `pip install pipwin && pipwin install pyaudio`

**`No se detecta el bajo`**  
→ Verifica que la interfaz de audio aparece en dispositivos de Windows  
→ Sube el volumen de entrada en el mezclador de Windows

---

Tablatura original: [www.basslessons.be](https://www.basslessons.be)
