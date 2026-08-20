# Bass Karaoke

**Bass Karaoke** es un karaoke de bajo eléctrico con tablatura que se desplaza en
tiempo real, detección de tono (pitch) y visualización de partitura. Toca con el
bajo conectado al PC y la app te dice qué nota tocar, cuándo suena correcta y
tu precisión global.

Incluye canciones como *Feet Don't Fail Me Now* — Joy Crookes | Bajo: Dayna Fisher.

![Bass Karaoke Screenshot](assets/Screenshot.png)

---

## Funcionalidades

- **Tablatura en scroll** con línea guía y resaltado de la nota actual (solo se
  ilumina cuando la nota *realmente* suena; en los silencios no queda nada marcado).
- **Detección de pitch en tiempo real** (aubio/MPM por defecto) con feedback
  verde/rojo y panel de afinación (cents, agudo/grave).
- **Partitura estándar** renderizada con Verovio + CairoSVG (incluidos en el exe;
  también se puede usar Music21 como alternativa).
- **Editor de alineación** con waveform del MP3 para ajustar offset y tempo por
  canción a oído.
- **Ajuste de tempo por canción** (↑/↓): con varispeed el MP3 se estira/encoge
  manteniendo el tono para que música y tablatura sigan sincronizadas.
- **Metrónomo, afinador y mapa del mástil** integrados.
- **Standalone** de un solo archivo (`dist/BassKaraoke.exe`) que instala
  funcionalidades opcionales desde el propio menú `I`.

---

## Requisitos

- Python **3.10** (Windows)
- Bajo conectado al PC: interfaz USB (Focusrite, Behringer…) o cable a la
  entrada de micrófono (jack 3.5 mm)

---

## Instalación

Recomendado — entorno virtual con `uv`:

```bash
uv venv .venv --python 3.10
uv pip install --python .venv\Scripts\python.exe -r requirements.txt ^
   --find-links https://github.com/aubio/aubio/releases
```

O con `pip` clásico:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> Nota: `requirements.txt` pide `aubio==0.5.0a0`, que ya no está en PyPI; si
> falla, usa `aubio==0.4.9` o instálalo con `--find-links` (ver Solución de
> problemas). La app funciona sin aubio, solo pierde la detección de tono.

---

## Ejecutar en desarrollo

```bash
.venv\Scripts\python.exe bass_karaoke_v3.py
```

o simplemente `python bass_karaoke_v3.py` (si el venv está activado).

Pulsa **`L`** para elegir canción y **`SPACE`** para empezar (countdown 4-3-2-1).

> La app lee la configuración de `bass_karaoke_config.json` (offsets, tempos y
> ajustes por canción). En el standalone usa el que esté junto al exe.

---

## Canciones

Cada canción vive en una subcarpeta de `songs/`:

```
songs/
  feet_dont_fail_me_now/   <nombre>.musicxml, <nombre>.tg, feet_dont_fail_me_now.mp3
  maitreya/                <nombre>.musicxml, <nombre>.tg
  infant_eyes/             <nombre>.musicxml
```

Para añadir una:

1. Crea `songs/<nombre>/`.
2. Añade el `musicxml` (obligatorio), un `.tg` de TuxGuitar (opcional, notas de
   gracia) y un `.mp3` (opcional — sin MP3 se practica solo con metrónomo/tablatura).
3. Pulsa **`L`** en la app para abrir el selector.

El MusicXML puede ser:
- Export de **TuxGuitar** (notación + tablatura con trastes) — recomendado.
- Export de **MuseScore** solo con notación: la app deriva traste/cuerda desde la
  altura de cada nota (la tablatura puede diferir de la original).

### Tempo de la canción

El tempo original se lee de las **marcas de tempo del MusicXML** (`<metronome>`),
no del MP3. Si no hay marcas, se usa 113 BPM por defecto. Añade las marcas desde
MuseScore (Texto → Tempo) y re-exporta. La app respeta los cambios de tempo a
mitad de tema (scroll, metrónomo y sincronización siguen cada tramo).

El ajuste con `↑/↓` (estirar el MP3 más lento/rápido) se guarda **por canción**
con **`F5`**.

### Si el bajo no empieza al inicio del MP3

En jazz y temas con intro el bajo suele entrar más tarde (p. ej. a 0:25). Usa el
**offset del MP3**: `,`/`.` (0,05 s), `Shift+,`/`Shift+.` (0,5 s) o
`Ctrl+,`/`Ctrl+.` (5 s) para retrasar la entrada del MP3 hasta que el compás 1
coincida con el bajo. El offset se guarda **por canción** con **`F5`**.

### Editor de alineación (`W`)

Cuando el tempo o la entrada del bajo no cuadran con la partitura (típico en
jazz, donde el solista se estira un compás), pulsa **`W`** para ver el
**waveform del MP3** y alinear visualmente:

- **Línea roja = PRIMERA nota del bajo** (offset): arrástrala para moverla.
- **Clic** en el waveform: mueve solo el cursor blanco.
- **Marcas verdes = cambios de tempo** (con su BPM): se abren donde dice la
  partitura; arrástralas a donde **suenan de verdad** y quedan fijadas ahí.
- **`R`**: restablece todas las marcas a lo que dice la partitura (la línea roja se mantiene).
- **Clic derecho**: añade una marca de tempo (hereda el BPM vigente).
- **Rueda**: zoom temporal sobre el waveform. **Clic central + arrastrar**: paneo horizontal.
- **`SPACE`**: reproduce/pausa el MP3 a velocidad natural desde el cursor.
- **`F`**: análisis orientativo con librosa (tempo medio + onsets).
- **`↑`/`↓`**: sube/baja el BPM del tramo bajo el cursor.
- **`←`/`→`**: mueve el cursor (±1 s, ±5 s con `Ctrl`).
- **`Supr`**: elimina la marca de tempo del tramo activo.
- **`W`/`ESC`**: guarda y cierra (offset + mapa de tempo por canción).

El waveform también dibuja la banda verde (zona transcrita), ticks de compás,
secciones de la partitura (amarillo) y referencias del MusicXML (cián) cuando has
movido una marca. Todo se guarda por canción en la config.

---

## Controles

| Tecla | Acción |
|---|---|
| `SPACE` | Reproducir / pausar (con countdown 4-3-2-1) |
| `L` | Selector de canciones |
| `W` | Editor de alineación (waveform del MP3) |
| `C` | Activar/desactivar countdown |
| `R` | Reiniciar |
| `← / →` | Compás anterior / siguiente |
| `↑ / ↓` | Tempo ±5 BPM (con varispeed estira el MP3) |
| `, / .` | Offset del MP3 ±0,05 s (fino) |
| `Shift + , / .` | Offset ±0,5 s (medio) |
| `Ctrl + , / .` | Offset ±5 s (rápido) |
| `D` | Selector de dispositivo de audio (si la entrada está disponible) |
| `P` | Selector de método de pitch |
| `S` | Cambiar renderizador de partitura (Verovio ↔ Music21) |
| `M` | Silenciar MP3 |
| `N` | Sonido de metrónomo |
| `T` | Afinador |
| `H` | Mapa del mástil |
| `B` | Alternar display de tempo (BPM ↔ figura) |
| `I` | Menú de funcionalidades opcionales (solo standalone) |
| `F5` | Guardar configuración |
| `F6` | Cargar configuración |
| `ESC` | Salir |

---

## Cómo funciona

- La tablatura se desplaza de derecha a izquierda; la línea dorada vertical
  marca la nota que debes tocar ahora.
- El número grande del panel izquierdo indica el traste a pulsar.
- Colores de cuerda: E=rojo, A=amarillo, D=azul, G=verde.

**Colores de la nota actual:**
- **Amarillo** — esperando tu entrada
- **Verde** — correcta (has tocado la nota bien)
- **Rojo** — nota errónea

**Panel de pitch (derecha):** muestra la nota que estás tocando en tiempo real.
La barra horizontal indica si estás agudo/grave. El % es la precisión global.

---

## Standalone (Windows)

Build de un **único exe** con todas las dependencias (PyInstaller):

```powershell
.\build.ps1                # build normal
.\build.ps1 -Verify        # build + auto-check del exe (BK_VERIFY=1)
```

Equivalente manual:

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\pyinstaller.exe build_basic.spec --clean --noconfirm
```

El resultado es `dist/BassKaraoke.exe` (~50 MB). Para desplegarlo en otro PC:

1. Copia el exe junto con las carpetas **`songs/`** y **`models/`** (no van
   empaquetadas para poder añadir canciones sin recompilar).
2. Las funcionalidades opcionales (torch/crepe, pesto, varispeed, etc.) se
   instalan desde el menú **`I`** y se guardan en `./features` junto al exe;
   tras instalarlas hay que reiniciar la app.

El build empaqueta por defecto (ya no son opcionales):

- **verovio + cairosvg** con los DLLs de cairo del GTK2-Runtime (funciona en
  cualquier PC sin instalarlos en el sistema).
- **soundfile**: decodificación de MP3 para el waveform del editor de alineación.

Detalles técnicos en la cabecera de `build_basic.spec`.

---

## Estructura del proyecto

```
bass_karaoke/      → paquete principal (app, audio, score, ui…)
bass_karaoke_v3.py → punto de entrada en desarrollo
launcher.py        → punto de entrada del exe (modo BK_VERIFY=1 para auto-check)
build_basic.spec   → spec de PyInstaller del standalone básico
build.ps1          → script de build
models/            → modelos de detección de pitch (ONNX)
assets/            → recursos estáticos (captura, fuentes, etc.)
songs/             → canciones (cada una en su subcarpeta)
tests/             → scripts de prueba del detector de pitch
scripts/           → utilidades (listar dispositivos de audio, etc.)
requirements.txt
```

---

## Solución de problemas

**`No module named aubio`**
→ `pip install aubio --find-links https://github.com/aubio/aubio/releases`
→ Si falla, la app sigue funcionando, solo sin reconocimiento de pitch.

**`PortAudio library not found`**
→ `pip install sounddevice --upgrade`
→ O reinstala: `pip install pipwin && pipwin install pyaudio`

**`Bass not detected`** (el micrófono no capta el bajo)
→ Comprueba que tu interfaz aparece como dispositivo de entrada en Windows
→ Sube el volumen de entrada en el mezclador de Windows
→ Usa la tecla **`D`** para elegir el dispositivo correcto

**La partitura no se renderiza en el standalone**
→ Los DLLs de cairo se toman del GTK2-Runtime de la máquina de build. Si en el
PC destino falla, reinstala el GTK2-Runtime y reconstruye, o apunta la variable
`GTK2_RUNTIME_BIN` a su `bin` antes de `build.ps1`.

---

Original tablature: [www.basslessons.be](https://www.basslessons.be)