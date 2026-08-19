# Bass Karaoke

**Bass Karaoke** is an electric bass karaoke app with real-time scrolling tablature, pitch detection, and score visualization.

Includes songs like *Feet Don't Fail Me Now* — Joy Crookes | Bass: Dayna Fisher.

![Bass Karaoke Screenshot](assets/Screenshot.png)

---

## Installation

Recomendado (entorno virtual con `uv`):

```bash
uv venv .venv --python 3.10
uv pip install --python .venv\Scripts\python.exe -r requirements.txt \
   --find-links https://github.com/aubio/aubio/releases
```

o con `pip` clásico:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Si `aubio` falla en Windows:

```bash
pip install aubio --find-links https://github.com/aubio/aubio/releases
```

Alternativa si `aubio` no instala (más pesada, pero funciona):

```bash
pip install crepe
```

> Nota: `requirements.txt` pide `aubio==0.5.0a0`, que ya no está en PyPI;
> usa `aubio==0.4.9`.

---

## Canciones

Cada canción vive en una subcarpeta de `songs/`:

```
songs/
  mitab/          mitab.musicxml, mitab.tg, feet_dont_fail_me_now.mp3
  maitreya/       maitreya_partitura1.musicxml, maitreya_partitura1.tg
  infant_eyes/    infanteyes_bass.musicxml
```

Para añadir una canción:

1. Crea `songs/<nombre>/`
2. Pon ahí el `musicxml` (obligatorio), un `.tg` de TuxGuitar (opcional, notas de gracia) y un `.mp3` (opcional — sin MP3 se practica solo con metrónomo/tablatura).
3. Pulsa **`L`** en la app para abrir el selector de canciones.

El MusicXML puede ser:
- Export de **TuxGuitar** (2 pentagramas: notación + tablatura con trastes) — recomendado.
- Export de **MuseScore** con solo notación estándar: la app deriva automáticamente traste/cuerda desde la altura de cada nota (la tablatura resultante puede diferir de la original).

### Tempo de la canción

El tempo original se lee de las **marcas de tempo del MusicXML** (`<metronome>`),
no del MP3. Si la partitura no tiene marcas, se usa 113 BPM por defecto.

Puedes añadir las marcas desde **MuseScore** (Texto → Tempo) y re-exportar el
MusicXML. Si la canción cambia de tempo a mitad (p.ej. primeros 5 compases a
60 corcheas y el resto a 50), la app lo respeta: el scroll, el metrónomo y la
sincronización con el MP3 siguen cada tramo a su tempo. Ajusta los valores en
la partitura si el tempo real de tu grabación difiere.

El ajuste con `↑/↓` (estirar el MP3 más lento/rápido) se guarda **por canción**
(F5) — cada canción recuerda su propio tempo de práctica.

### Si el bajo no empieza al inicio del MP3

En jazz y temas con intro, el bajo suele entrar más tarde (p.ej. a 0:25). Usa
el **offset del MP3**: `,`/`.` (0,05 s), `Shift+,`/`Shift+.` (0,5 s) o
`Ctrl+,`/`Ctrl+.` (5 s) para retrasar la entrada del MP3 hasta que el compás 1
coincida con el bajo. El offset se guarda **por canción** con F5.

### Editor de alineación (W)

Cuando el tempo o la entrada del bajo no cuadran con la partitura (típico en
jazz, donde el solista se estira un compás), pulsa **`W`** para ver el
**waveform del MP3** y alinear visualmente:

- **Línea roja = PRIMERA nota del bajo** (offset): **arrástrala** para
  moverla. En ese instante la partitura corre por el compás donde entra el
  bajo (si el tema tiene compases vacíos de introducción, quedan antes).
- **Clic** en cualquier punto del waveform: mueve solo el **cursor** blanco.
- **Marcas verdes = cambios de tempo** (con su BPM). Se abren colocadas donde
  **dice la partitura**, y mientras no las toques se mueven junto con la línea
  roja. **Arrástralas** a donde **suenan de verdad** en la canción y quedan
  fijadas ahí.
- **`R`**: restablece todas las marcas a lo que dice la partitura (la línea
  roja se mantiene).
- Si una marca coincide exactamente con la línea roja, se dibuja 3 px a la
  derecha para poder distinguirla y arrastrarla.
- **Clic derecho**: añade una marca de tempo en ese punto (hereda el BPM
  vigente).
- **Rueda del ratón**: zoom temporal sobre el waveform (centrado en el cursor).
- **Botón central (o clic central) y arrastrar**: paneo horizontal cuando
  estás con zoom. El cursor (blanco) se mantiene visible al navegar con `←/→`.
- **`SPACE`**: reproduce/pausa el MP3 a velocidad natural desde el cursor,
  para escuchar y colocar las marcas a oído.
- **`F`**: analiza la canción con librosa (tempo estimado + onsets).
- **`↑`/`↓`**: sube/baja el BPM del tramo bajo el cursor blanco.
- **`←`/`→`**: mueve el cursor (±1 s, ±5 s con `Ctrl`).
- **`Supr`**: elimina la marca de tempo del tramo activo.
- **`W`/`ESC`**: guarda y cierra (guarda offset + mapa de tempo por canción).

En el waveform se dibujan también: la **banda verde** (zona que cubre la
transcripción), **ticks de compás**, **secciones de la partitura** (en
amarillo, si el MusicXML tiene indicaciones tipo ensayo), y las **referencias
de la partitura** en **cián** (`Σ 50`): solo aparecen cuando ya has movido esa
marca, mostrando dónde la sitúa el MusicXML. La detección con `F` es solo
orientativa (tempo medio + onsets). Todo se guarda por canción en la config.

---

## Usage

1. Conecta el bajo al ordenador (interfaz USB/Jack)
   → asegúrate de que Windows lo reconoce como entrada de micrófono.

2. Arranca la app:

```bash
python bass_karaoke_v3.py
```

   o desde el venv:

```bash
.venv\Scripts\python.exe bass_karaoke_v3.py
```

3. Pulsa **`L`** para elegir la canción y **`SPACE`** para empezar (con countdown 4-3-2-1).

---

## Controls

| Key | Action |
|---|---|
| `SPACE` | Play / Pause (with 4-3-2-1 countdown) |
| `L` | Song selector |
| `W` | Alignment editor (waveform MP3) |
| `C` | Toggle countdown |
| `R` | Restart |
| `← / →` | Previous / next bar |
| `↑ / ↓` | Tempo ±5 BPM |
| `, / .` | MP3 offset ±0.05 s (fine) |
| `Shift + , / .` | MP3 offset ±0.5 s (coarse) |
| `Ctrl + , / .` | MP3 offset ±5 s (fast) |
| `D` | Audio device selector |
| `P` | Pitch method selector |
| `S` | Switch score renderer (Verovio ↔ Music21) |
| `M` | Mute/unmute MP3 |
| `N` | Metronome sound |
| `T` | Tuner |
| `H` | Neck map |
| `F5` | Save configuration |
| `F6` | Load configuration |
| `ESC` | Quit |

---

## How it works

- The tablature scrolls from right to left
- The vertical golden line = the note you should play now
- The large number in the left panel = fret to press
- String colors: E=red, A=yellow, D=blue, G=green

**Current note colors:**
- **Yellow** — waiting for your input
- **Green** — correct! note played right
- **Red** — wrong note

**Pitch panel (right):**
Shows the note you are playing in real time. The horizontal bar indicates if you are sharp/flat. Score in % = overall accuracy.

---

## Audio requirements

- An audio interface (Focusrite, Behringer, etc.)
- Or bass cable → 3.5mm jack → PC microphone input
- On Windows: Control Panel → Sound → select your interface

---

## Project structure

```
bass_karaoke/      → main package
bass_karaoke_v3.py → entry point
models/            → pitch detection models (ONNX)
assets/            → static resources (glyphnames, etc.)
songs/             → songs (each one in its own subfolder)
tests/             → pitch detector test scripts
scripts/           → utilities (list audio devices, etc.)
requirements.txt
```

---

## Standalone build (Windows)

Build a folder with the `.exe` and all dependencies (PyInstaller):

```bash
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller build/bass_karaoke.spec --noconfirm
```

Resultado: `dist/BassKaraoke/`. Copia las carpetas `songs/` y `models/` junto al exe
(no van empaquetadas para que puedas añadir canciones sin recompilar).

---

## Troubleshooting

**`No module named aubio`**
→ `pip install aubio --find-links https://github.com/aubio/aubio/releases`
→ If it fails, the app still works but without pitch recognition

**`PortAudio library not found`**
→ `pip install sounddevice --upgrade`
→ Or reinstall: `pip install pipwin && pipwin install pyaudio`

**`Bass not detected`**
→ Check that your audio interface appears in Windows devices
→ Raise the input volume in the Windows mixer

---

Original tablature: [www.basslessons.be](https://www.basslessons.be)