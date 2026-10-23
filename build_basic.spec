# -*- mode: python ; coding: utf-8 -*-
"""
Spec de PyInstaller para el STANDALONE BÁSICO de Bass Karaoke.

El ejecutable incluye el núcleo:
    numpy + pygame + pyaudio  (+ pip embebido para instalar funcionalidades)

Y empaquetadas por defecto (ya no son funcionalidades opcionales):
    - verovio + cairosvg: partitura estándar (tecla S). Los DLLs de cairo
      (GTK2-Runtime) se copian dentro del exe para que funcione en cualquier
      PC sin necesidad de instalarlos en el sistema.
    - soundfile: decodificación de MP3 para el waveform del editor de
      alineación (W), sin depender de librosa.

El resto de funcionalidades opcionales (torch/torchcrepe, pesto,
onnxruntime, librosa/sounddevice, scipy, aubio, music21, basic-pitch…)
se EXCLUYEN del build y el usuario puede instalarlas desde el propio
ejecutable con el menú "I → Funcionalidades" (se guardan en ./features junto
al .exe). Tras instalarlas hay que reiniciar la app.

Uso:
    pyinstaller build_basic.spec --clean --noconfirm

Notas:
    - Las carpetas songs/, models/ y assets/ NO se empaquetan: deben estar
      junto al .exe (el código ya las busca en la carpeta del ejecutable).
    - console=False → app sin ventana de consola; los print() de depuración
      no se ven. Si quieres verlos, cambia console a True.
"""
import os

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(SPECPATH)  # carpeta donde está este .spec
block_cipher = None

# ── Módulos del propio paquete ───────────────────────────────────────────────
hiddenimports = [
    "bass_karaoke",
    "bass_karaoke.main",
    "bass_karaoke.app",
    "bass_karaoke.config",
    "bass_karaoke.parser",
    "bass_karaoke.utils",
    "bass_karaoke.features",
    "bass_karaoke.audio",
    "bass_karaoke.audio.player",
    "bass_karaoke.audio.bass_track",
    "bass_karaoke.audio.pitch_engine",
    "bass_karaoke.score",
    "bass_karaoke.score.verovio_renderer",
    "bass_karaoke.score.music21_renderer",
    "bass_karaoke.ui",
    "bass_karaoke.ui.widgets",
    "bass_karaoke.ui.draw_tab",
    "bass_karaoke.ui.draw_score",
    "bass_karaoke.ui.draw_guitartab",
    "bass_karaoke.ui.draw_neck",
    "bass_karaoke.ui.draw_piano",
    "bass_karaoke.ui.draw_panels",
    "bass_karaoke.ui.draw_overlays",
]

# ── Funcionalidades opcionales que NO entran en el básico ────────────────────
excludes = [
    # Detectores de pitch con IA / alternativos
    "torch", "torchcrepe", "pesto", "onnxruntime", "basic_pitch",
    "aubio",
    # Reproducción avanzada (time-stretch) y análisis
    "librosa", "sounddevice", "resampy", "soxr", "pooch",
    # Ciencia de datos que arrastran librosa/scipy
    "scipy", "numba", "llvmlite", "sklearn", "scikit_learn",
    "matplotlib", "sympy", "networkx", "pretty_midi", "joblib",
    # SoundFont opcional del mixer (el .sf2 sí va en assets/)
    "tinysoundfont",
    # Renderizado de partitura (solo music21 queda opcional: verovio y
    # cairosvg van empaquetados por defecto)
    "music21",
    # Cosas de desarrollo que solo ensucian
    "IPython", "jupyter", "notebook", "tkinter", "pydoc", "pdb",
    "doctest", "unittest",
]

# ── pip embebido: necesario para el instalador de funcionalidades ───────────
_pip_datas, _pip_binaries, _pip_hidden = collect_all("pip")
hiddenimports += _pip_hidden
hiddenimports += collect_submodules("pip._internal")

datas     = list(_pip_datas)
binaries  = list(_pip_binaries)

# DLL de ABI estable (python3.dll): la necesitan extensiones .pyd "stable ABI"
# instaladas bajo demanda (p. ej. verovio, cuyo _verovio.pyd importa de
# python3.dll). PyInstaller solo empaqueta python3XX.dll, no el puente de
# ABI estable; sin él, el import de la extensión falla con "DLL load failed".
import sys as _sys
_py3dll = os.path.join(_sys.base_prefix, "python3.dll")
if os.path.isfile(_py3dll):
    binaries.append((_py3dll, "."))

# ── Partitura (verovio + cairosvg) y waveform (soundfile) por defecto ────────
# Se empaquetan dentro del exe (ya no son funcionalidades opcionales).
# collect_all asegura que se copien los datos (fuentes de verovio, VERSION y
# assets de cairosvg, libsndfile de soundfile) además de los módulos.
_vrv_d, _vrv_b, _vrv_h = collect_all("verovio")
_cs_d,  _cs_b,  _cs_h  = collect_all("cairosvg")
_sf_d,  _sf_b,  _sf_h  = collect_all("soundfile")
datas          += _vrv_d + _cs_d + _sf_d
binaries       += _vrv_b + _cs_b + _sf_b
hiddenimports  += _vrv_h + _cs_h + _sf_h
hiddenimports  += [
    "cairocffi", "cffi", "PIL", "cssselect2", "tinycss2", "defusedxml",
]

# ── DLLs de cairo (GTK2-Runtime) para que cairosvg funcione en cualquier PC ──
# cairocffi localiza libcairo-2.dll con ctypes.find_library, que en PyInstaller
# busca primero en sys._MEIPASS; los DLLs dependientes (glib, gobject,
# fontconfig, freetype, pixman…) quedan también en _MEIPASS y se resuelven
# desde PATH. Se copia TODO el bin/ del GTK2-Runtime de la máquina de build
# (se puede apuntar a otra ruta con la variable GTK2_RUNTIME_BIN).
_gtk_bin = os.environ.get(
    "GTK2_RUNTIME_BIN", r"C:\Program Files (x86)\GTK2-Runtime\bin")
if os.path.isdir(_gtk_bin):
    for _f in sorted(os.listdir(_gtk_bin)):
        if _f.lower().endswith(".dll"):
            binaries.append((os.path.join(_gtk_bin, _f), "."))
    print(f"[build] DLLs de cairo empaquetados desde {_gtk_bin} "
          f"({sum(1 for _f in os.listdir(_gtk_bin) if _f.lower().endswith('.dll'))})")
else:
    print("[build] ATENCIÓN: no se encontró GTK2-Runtime; cairosvg requerirá "
          "cairo instalado en el sistema destino para renderizar la partitura.")

# Carpetas de datos junto al proyecto (si existen): se copian al .exe.
for _d in ("assets",):
    _p = os.path.join(ROOT, _d)
    if os.path.isdir(_p):
        datas.append((_p, _d))

a = Analysis(
    [os.path.join(ROOT, "launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BassKaraoke",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)

# ── Copia de canciones de ejemplo junto al .exe ──────────────────────────────
# Solo las que tienen mp3 + musicxml, y solo esos dos tipos de archivo
# (se descartan .mid/.mscz/.tab/.tg/.png…). La app busca songs/ en la
# carpeta del ejecutable (ver config._BASE_DIR cuando es frozen).
import shutil as _shutil

def _copy_song(src_dir: str, dst_dir: str):
    if not os.path.isdir(src_dir):
        return False
    os.makedirs(dst_dir, exist_ok=True)
    copied = []
    for ext in (".mp3", ".musicxml"):
        for f in sorted(os.listdir(src_dir)):
            if f.lower().endswith(ext) and not f.startswith("."):
                _shutil.copy2(os.path.join(src_dir, f), os.path.join(dst_dir, f))
                copied.append(f)
    return bool(copied)

for _song in ("feet_dont_fail_me_now", "infant_eyes"):
    _copy_song(os.path.join(ROOT, "songs", _song),
               os.path.join(DISTPATH, "songs", _song))