# Bass Karaoke

**Bass Karaoke** is an electric bass karaoke app with real-time scrolling tablature, pitch detection, and score visualization.

Based on the song *Feet Don't Fail Me Now* — Joy Crookes | Bass: Dayna Fisher.

---

## Installation

```bash
pip install -r requirements.txt
```

If `aubio` fails on Windows:

```bash
pip install pygame sounddevice numpy
pip install aubio --find-links https://github.com/aubio/aubio/releases
```

Alternative if `aubio` won't install (heavier but works):

```bash
pip install crepe
```

---

## Usage

1. Place your song MP3 in the project root folder  
   → Name it `feet_dont_fail_me_now.mp3` (or any name — it auto-detects)

2. Connect your bass to the computer (USB/Jack audio interface)  
   → Make sure Windows recognizes it as a microphone input

3. Run:

```bash
python bass_karaoke_v3.py
```

---

## Controls

| Key | Action |
|---|---|
| `SPACE` | Play / Pause (with 4-3-2-1 countdown) |
| `C` | Toggle countdown |
| `R` | Restart |
| `← / →` | Previous / next bar |
| `↑ / ↓` | Tempo ±5 BPM |
| `, / .` | MP3 offset ±0.05 s (fine) |
| `Shift + , / .` | MP3 offset ±0.5 s (coarse) |
| `D` | Audio device selector |
| `P` | Pitch method selector |
| `S` | Switch score renderer (Verovio ↔ Music21) |
| `M` | Mute/unmute MP3 |
| `T` | Tuner |
| `F5` | Save configuration |
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
songs/             → example songs (MusicXML, TG, MIDI)
tests/             → pitch detector test scripts
scripts/           → utilities (list audio devices, etc.)
requirements.txt
```

---

## Troubleshooting

**`No module named aubio`**  
→ `pip install aubio`  
→ If it fails, the app still works but without pitch recognition

**`PortAudio library not found`**  
→ `pip install sounddevice --upgrade`  
→ Or reinstall: `pip install pipwin && pipwin install pyaudio`

**`Bass not detected`**  
→ Check that your audio interface appears in Windows devices  
→ Raise the input volume in the Windows mixer

---

Original tablature: [www.basslessons.be](https://www.basslessons.be)
