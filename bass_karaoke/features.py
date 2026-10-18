"""
Gestor de funcionalidades opcionales (instalación bajo demanda).

El standalone básico solo incluye el núcleo (numpy + pygame + pyaudio).
Cada funcionalidad extra (motores de pitch con IA, partitura, time-stretch…)
se instala con pip en la carpeta ``features/`` junto al ejecutable y se añade
a ``sys.path`` para que esté disponible en el siguiente arranque.

La instalación usa pip de forma embebida (funciona también dentro de un
ejecutable PyInstaller, que lleva pip incluido). En modo desarrollo, si el
intérprete no tiene pip, se intenta ``python -m pip`` como alternativa.
"""
import io
import os
import re
import sys
import contextlib
import shutil
import threading

# ── Registro de funcionalidades ──────────────────────────────────────────────
#  id        : identificador interno
#  name      : nombre visible
#  category  : pitch | audio | score | core
#  packages  : paquetes pip que instala la funcionalidad
#  requires  : ids de otras funcionalidades que se instalan primero
#  size      : tamaño aproximado (información para el usuario)
#  needs     : requisitos (información para el usuario)
#  desc      : para qué sirve (se muestra en el menú)
FEATURES = [
    {
        "id": "aubio",
        "name": "aubio YIN — detector de pitch (CPU)",
        "category": "pitch",
        "packages": ["aubio"],
        "requires": [],
        "size": "~1 MB",
        "needs": "CPU",
        "desc": (
            "Detector de pitch alternativo al MPM por defecto (método YIN, "
            "mínima latencia, bueno en graves y sin GPU). Aparece como "
            "'aubio' en el menú de detección de pitch (tecla P). "
            "Ojo: aubio no tiene wheels en todas las versiones de Python; "
            "si pip pide compilarlo, necesitarás un compilador C instalado."
        ),
    },
    {
        "id": "torch-core",
        "name": "PyTorch — motor de detección con IA",
        "category": "core",
        "packages": ["torch"],
        "requires": [],
        "size": "~465 MB",
        "needs": "CPU o GPU (CUDA)",
        "desc": (
            "Motor de redes neuronales que necesitan los detectores con IA "
            "(CREPE y PESTO). Se instala una sola vez y lo comparten ambos. "
            "Con GPU compatible, la detección es mucho más rápida."
        ),
    },
    {
        "id": "crepe",
        "name": "CREPE — detección con IA (tiny/full)",
        "category": "pitch",
        "packages": ["torchcrepe"],
        "requires": ["torch-core"],
        "size": "~87 MB (+ PyTorch)",
        "needs": "GPU recomendada",
        "desc": (
            "Detector de pitch basado en red neuronal (CREPE): muy preciso, "
            "con GPU es rápido en tiempo real. Aparece como 'crepe-tiny' y "
            "'crepe-full' en el menú de detección de pitch (tecla P)."
        ),
    },
    {
        "id": "pesto",
        "name": "PESTO — detección con IA (streaming)",
        "category": "pitch",
        "packages": ["pesto"],
        "requires": ["torch-core"],
        "size": "~pocos MB (+ PyTorch)",
        "needs": "GPU recomendada",
        "desc": (
            "Detector de pitch en streaming con IA (modelo mir-1k). Pensado "
            "para tiempo real. Aparece como 'pesto' en el menú de detección "
            "de pitch (tecla P)."
        ),
    },
    {
        "id": "pesto-onnx",
        "name": "PESTO ONNX — detección con IA en CPU",
        "category": "pitch",
        "packages": ["onnxruntime"],
        "requires": [],
        "size": "~37 MB",
        "needs": "CPU + modelo ONNX",
        "desc": (
            "El mismo detector PESTO pero ejecutado con ONNX Runtime: IA sin "
            "PyTorch en la inferencia, más ligero. Requiere el modelo "
            "models/mir-1k_g7_44100_512.onnx. Aparece como 'pesto-onnx' en "
            "el menú de detección de pitch (tecla P)."
        ),
    },
    {
        "id": "basic-pitch",
        "name": "Basic Pitch — detección (Spotify)",
        "category": "pitch",
        "packages": ["basic-pitch"],
        "requires": [],
        "size": "~500 MB (con dependencias)",
        "needs": "CPU",
        "desc": (
            "Detector de Spotify con buffer deslizante de 1.5 s. Útil en "
            "pasajes con varias notas a la vez. Aparece como 'basic-pitch' "
            "en el menú de detección de pitch (tecla P)."
        ),
    },
    {
        "id": "demucs",
        "name": "Demucs — separación de bajo (transcripción)",
        "category": "audio",
        "packages": ["demucs"],
        "requires": ["torch-core"],
        "size": "~80 MB (+ PyTorch)",
        "needs": "CPU o GPU (CUDA) recomendada",
        "desc": (
            "Separa la pista de bajo del mix para transcribir canciones que "
            "solo tienen audio (tecla F7). Sin Demucs se usa el stem "
            "'<cancion>-bass.wav' si existe, o un filtro paso-bajo del mix. "
            "Con GPU compatible es mucho más rápido."
        ),
    },
    {
        "id": "varispeed",
        "name": "Time-stretch y análisis de tempo",
        "category": "audio",
        "packages": ["librosa", "sounddevice"],
        "requires": [],
        "size": "~250 MB (con dependencias)",
        "needs": "CPU",
        "desc": (
            "Reproduce el MP3 con time-stretch: cambia el tempo sin cambiar "
            "el tono. Además habilita la tecla F en el editor de alineación "
            "(W) para detectar automáticamente tempo y compases. Sin esto, "
            "la canción suena a velocidad fija (el waveform del editor sí "
            "funciona siempre, incluso sin esta funcionalidad)."
        ),
    },
    {
        "id": "scipy",
        "name": "Pre-filtrado de precisión del audio",
        "category": "audio",
        "packages": ["scipy"],
        "requires": [],
        "size": "~104 MB",
        "needs": "CPU",
        "desc": (
            "Filtros paso-alto/paso-bajo de mayor precisión antes del "
            "detector de pitch (evita que se enganche una octava arriba). "
            "Sin él se usan filtros biquad escritos en numpy: mismo "
            "resultado, algo más lento."
        ),
    },
    {
        "id": "music21",
        "name": "Partitura estándar (music21)",
        "category": "score",
        "packages": ["music21"],
        "requires": [],
        "size": "~120 MB",
        "needs": "CPU",
        "desc": (
            "Renderizador alternativo de partitura (music21) para el mismo "
            "MusicXML. Se elige en lugar de Verovio con la tecla S. "
            "No necesita dependencias de sistema (recomendado en Windows)."
        ),
    },
]


def by_id(fid: str):
    for f in FEATURES:
        if f["id"] == fid:
            return f
    raise KeyError(fid)


def features_dir() -> str:
    """Carpeta donde se instalan las funcionalidades (junto al .exe o al proyecto)."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "features")


def _patch_frozen_quirks():
    """Corrige paquetes instalados bajo demanda que detectan PyInstaller.

    Algunos paquetes (p. ej. cairosvg) comprueban ``sys.frozen`` / 
    ``sys._MEIPASS`` para localizar sus archivos de datos dentro del bundle
    del ejecutable. Aquí se instalan en ``features/`` (fuera del .exe), así
    que ese camino no existe y falla (p. ej. cairosvg lee su archivo VERSION).
    Si el paquete tiene el patrón ``if hasattr(sys, 'frozen'): … ROOT =
    Path(__file__).resolve().parent`` se reescribe para resolver SIEMPRE con
    ``__file__`` (la ubicación real en features/). Idempotente: al segundo
    arranque el patrón ya no está y no se toca nada.
    """
    root = features_dir()
    init = os.path.join(root, "cairosvg", "__init__.py")
    if not os.path.isfile(init):
        return
    try:
        with open(init, "r", encoding="utf-8") as fh:
            text = fh.read()
        new = re.sub(
            r"if hasattr\(sys,\s*'frozen'\):.*?ROOT = Path\(__file__\)\.resolve\(\)\.parent",
            "ROOT = Path(__file__).resolve().parent",
            text,
            flags=re.DOTALL,
        )
        if new != text:
            with open(init, "w", encoding="utf-8") as fh:
                fh.write(new)
            print("[features] cairosvg: ruta de datos corregida para ejecutable")
    except Exception as exc:
        print(f"[features] aviso: no se pudo parchear cairosvg: {exc}")


def ensure_on_path():
    """Añade features/ a sys.path al PRINCIPIO.

    Los paquetes instalados bajo demanda traen su propio numpy (pip resuelve
    una versión consistente con sus extensiones compiladas, p. ej. aubio o
    scipy). Al poner features/ primero, cada feature usa ese numpy coherente
    en vez del numpy del núcleo; si no hay features instaladas, la carpeta no
    existe y no se modifica nada.
    """
    d = features_dir()
    if os.path.isdir(d) and d not in sys.path:
        sys.path.insert(0, d)
    _patch_frozen_quirks()


def _has(pkg: str) -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec(pkg) is not None
    except (ImportError, ValueError):
        return False


def installed(fid: str) -> bool:
    f = by_id(fid)
    return all(_has(p) for p in f["packages"])


def status() -> dict:
    """Devuelve {id: instalado(bool)} para todas las funcionalidades."""
    return {f["id"]: installed(f["id"]) for f in FEATURES}


def session_flag(fid: str):
    """True/False si la app de la sesión actual ya puede usar la funcionalidad,
    o None si se carga de forma perezosa (basta reiniciar)."""
    try:
        if fid == "aubio":
            from .audio.pitch_engine import AUBIO_OK
            return bool(AUBIO_OK)
        if fid == "scipy":
            from .audio.pitch_engine import SCIPY_OK
            return bool(SCIPY_OK)
        if fid == "varispeed":
            from .audio import VARSPEED_OK
            return bool(VARSPEED_OK)
        if fid == "verovio":
            from .score import VEROVIO_OK, CAIROSVG_OK
            return bool(VEROVIO_OK and CAIROSVG_OK)
        if fid == "music21":
            from .score import MUSIC21_OK
            return bool(MUSIC21_OK)
    except Exception:
        return False
    return None


# ── pip ──────────────────────────────────────────────────────────────────────
def _run_pip(args, on_log=None):
    """Ejecuta pip (embebido si es posible, si no por subproceso) y devuelve el código."""
    def log(msg):
        if on_log:
            on_log(msg)

    env = dict(os.environ)
    env.setdefault("PIP_NO_WARN_SCRIPT_LOCATION", "1")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PIP_REQUIRE_VIRTUALENV", "0")

    # 1) pip embebido (funciona en un ejecutable PyInstaller)
    try:
        import pip._internal.cli.main as _pip_main

        # En apps congeladas, distlib no puede localizar los launchers de
        # scripts (t32/t64.exe) dentro del bundle y falla al crear las
        # consolas de comando de paquetes como verovio o cairosvg. Aquí solo
        # importamos los paquetes, esos scripts de CLI no hacen falta, así
        # que se desactiva su generación.
        _patched = None
        try:
            from pip._vendor.distlib.scripts import ScriptMaker as _SM
            _orig_multi = _SM.make_multiple
            def _no_scripts(self, specifications, options=None):
                return []
            _SM.make_multiple = _no_scripts
            _patched = (_SM, _orig_multi)
        except Exception:
            pass

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                try:
                    code = _pip_main.main(list(args))
                except SystemExit as exc:
                    code = exc.code or 0
        finally:
            if _patched:
                _SM, _orig_multi = _patched
                _SM.make_multiple = _orig_multi
        for line in buf.getvalue().splitlines():
            log(line)
        return 0 if code in (None, 0) else int(code)
    except Exception as exc:
        log(f"[pip] embebido no disponible: {exc}")

    # 2) subproceso python -m pip (modo desarrollo)
    try:
        import subprocess
        proc = subprocess.run(
            [sys.executable, "-m", "pip", *args],
            capture_output=True, text=True, env=env)
        for line in (proc.stdout or "").splitlines():
            log(line)
        for line in (proc.stderr or "").splitlines():
            log(line)
        return proc.returncode
    except Exception as exc:
        log(f"[pip] no disponible: {exc}")
    return -1


def _base_args(target: str):
    return ["install", "--target", target, "--upgrade",
            "--no-input", "--disable-pip-version-check",
            "--no-warn-script-location"]


def _install_sync(fid: str, on_log=None) -> tuple:
    f = by_id(fid)
    target = features_dir()
    os.makedirs(target, exist_ok=True)
    for dep_id in f["requires"]:
        if installed(dep_id):
            continue
        dep = by_id(dep_id)
        if on_log:
            on_log(f"[features] dependencia: {dep['name']}")
        code = _run_pip([*_base_args(target), *dep["packages"]], on_log)
        if code != 0:
            return False, f"Fallo al instalar {dep['name']} (pip={code})"
    code = _run_pip([*_base_args(target), *f["packages"]], on_log)
    if code != 0:
        return False, f"Fallo al instalar {f['name']} (pip={code})"
    ensure_on_path()
    return True, f"{f['name']} instalado. Reinicia la app para activarlo."


def _uninstall_sync(fid: str, on_log=None) -> tuple:
    f = by_id(fid)
    target = features_dir()
    if not os.path.isdir(target):
        return True, "No hay nada que quitar."
    removed = []
    for pkg in f["packages"]:
        base = pkg.split(">=")[0].split("==")[0]
        stem = base.replace("-", "_")
        # Carpeta del paquete (p. ej. torch, torchcrepe, onnxruntime, scipy…)
        if os.path.isdir(os.path.join(target, stem)):
            shutil.rmtree(os.path.join(target, stem), ignore_errors=True)
            removed.append(stem)
        # metadata dist-info / egg-info
        for entry in list(os.listdir(target)):
            low = entry.lower()
            if low.startswith(stem) and (low.endswith(".dist-info") or low.endswith(".egg-info")):
                shutil.rmtree(os.path.join(target, entry), ignore_errors=True)
    if not os.listdir(target):
        shutil.rmtree(target, ignore_errors=True)
    ensure_on_path()
    if on_log:
        for r in removed:
            on_log(f"[features] eliminado: {r}")
    return True, f"{f['name']} eliminado. Reinicia la app para aplicarlo."


def install(fid: str, on_log=None, on_done=None):
    """Instala una funcionalidad (y sus dependencias) en segundo plano."""
    def work():
        try:
            ok, msg = _install_sync(fid, on_log)
        except Exception as exc:
            ok, msg = False, f"Error: {exc}"
        if on_done:
            on_done(fid, ok, msg)
    threading.Thread(target=work, daemon=True).start()


def uninstall(fid: str, on_log=None, on_done=None):
    """Desinstala una funcionalidad en segundo plano."""
    def work():
        try:
            ok, msg = _uninstall_sync(fid, on_log)
        except Exception as exc:
            ok, msg = False, f"Error: {exc}"
        if on_done:
            on_done(fid, ok, msg)
    threading.Thread(target=work, daemon=True).start()