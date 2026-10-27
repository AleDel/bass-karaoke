"""Puente con el motor real de JJazzLab (JJazzLab Toolkit).

JJazzLab genera la línea de bajo al vuelo: un ``.sng`` no contiene notas. Para
que el resultado sea *exactamente* el de JJazzLab no se reimplementa el motor,
se le pide el MIDI al propio JJazzLab (el ``jjazzlab-toolkit`` es su núcleo sin
interfaz gráfica) mediante un pequeño puente Java (``jjazz/jjazz-bridge.jar``).

Requisitos (se detectan solos):

- Java 25 o superior: sirve el JRE que instala JJazzLab en ``jdk/``.
- ``vendor/jjazzlab-toolkit-5.2.1.jar``: se descarga de Maven Central la
  primera vez (21 MB) si no está.

Si falta cualquiera de los dos, :func:`available` devuelve ``False`` y
``sng.build_song`` usa el generador interno (``yjz``) como hasta ahora.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

TOOLKIT_VERSION = "5.2.1"
TOOLKIT_URL = (
    "https://repo1.maven.org/maven2/org/jjazzlab/toolkit/"
    f"jjazzlab-toolkit/{TOOLKIT_VERSION}/jjazzlab-toolkit-{TOOLKIT_VERSION}.jar"
)
MIN_JAVA = 25

_ROOT = (Path(sys.executable).parent if getattr(sys, "frozen", False)
         else Path(__file__).resolve().parents[1])
_BRIDGE = Path(__file__).resolve().parent / "jjazz" / "jjazz-bridge.jar"
_VENDOR = _ROOT / "vendor"

_java: str | None | bool = False       # False = aún sin buscar
_toolkit: str | None | bool = False
_userdir: str | None = None


# ── localización de Java y del toolkit ─────────────────────────────────────
def _java_major(exe: str) -> int:
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True,
                             timeout=20, creationflags=_no_window()).stderr
    except (OSError, subprocess.SubprocessError):
        return 0
    m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
    if not m:
        return 0
    major = int(m.group(1))
    if major == 1 and m.group(2):       # 1.8.0
        major = int(m.group(2))
    return major


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _candidates() -> list[str]:
    res = []
    env = os.environ.get("JJAZZLAB_JAVA")
    if env:
        res.append(env)
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
        if base:
            res.append(os.path.join(base, "JJazzLab", "jdk", "bin",
                                    "java.exe"))
    home = os.environ.get("JAVA_HOME")
    if home:
        res.append(os.path.join(home, "bin", "java.exe"))
    res.append(shutil.which("java") or "")
    return [p for p in res if p and os.path.isfile(p)]


def find_java() -> str | None:
    """Ruta a un ``java`` >= 25 (el que trae JJazzLab sirve)."""
    global _java
    if _java is not False:
        return _java or None
    for exe in _candidates():
        if _java_major(exe) >= MIN_JAVA:
            _java = exe
            return exe
    _java = None
    return None


def toolkit_jar(download: bool = True) -> str | None:
    """Jar del toolkit, descargándolo de Maven Central si hace falta."""
    global _toolkit
    if _toolkit is not False:
        return _toolkit or None
    env = os.environ.get("JJAZZ_TOOLKIT_JAR")
    if env and os.path.isfile(env):
        _toolkit = env
        return env
    local = _VENDOR / f"jjazzlab-toolkit-{TOOLKIT_VERSION}.jar"
    if local.is_file():
        _toolkit = str(local)
        return _toolkit
    if not download:
        return None
    try:
        local.parent.mkdir(parents=True, exist_ok=True)
        log.info(f"[JJazzLab] descargando {TOOLKIT_URL} …")
        tmp = local.with_suffix(".part")
        with urllib.request.urlopen(TOOLKIT_URL, timeout=120) as resp:
            with open(tmp, "wb") as fh:
                shutil.copyfileobj(resp, fh)
        tmp.replace(local)
        _toolkit = str(local)
        return _toolkit
    except Exception as exc:                # red caída, sin permisos…
        log.warning(f"[JJazzLab] no puedo descargar el toolkit: {exc}")
        _toolkit = None
        return None


def available() -> bool:
    """True si se puede pedir el MIDI al motor de JJazzLab."""
    return bool(find_java() and toolkit_jar() and _BRIDGE.is_file())


def engine_info() -> dict:
    return {
        "toolkit": TOOLKIT_VERSION,
        "java": find_java() or "",
        "bridge": str(_BRIDGE),
    }


def _netbeans_userdir() -> str:
    global _userdir
    if _userdir is None:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        _userdir = os.path.join(base, "bass_karaoke", "jjazz-user")
        os.makedirs(_userdir, exist_ok=True)
    return _userdir


# ── conversión .sng -> .mid ────────────────────────────────────────────────
def sng_to_midi(sng_path: str, mid_path: str, timeout: int = 240) -> bool:
    """Genera el MIDI de la canción con el motor de JJazzLab.

    Escribe ``mid_path`` (todas las pistas: batería, bajo, acordes…) y
    devuelve ``True`` si el fichero se creó.
    """
    java = find_java()
    jar = toolkit_jar()
    if not (java and jar and _BRIDGE.is_file()):
        return False
    if os.path.exists(mid_path):
        try:
            os.remove(mid_path)
        except OSError:
            pass
    cmd = [
        java,
        # XStream lee EnumSet de ChordRenderingInfo por reflexión.
        "--add-opens=java.base/java.util=ALL-UNNAMED",
        "-Djava.awt.headless=true",
        f"-Dnetbeans.user={_netbeans_userdir()}",
        "-cp", f"{_BRIDGE}{os.pathsep}{jar}",
        "bk.JjazzExport", os.path.abspath(sng_path), os.path.abspath(mid_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, creationflags=_no_window())
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning(f"[JJazzLab] error ejecutando el puente: {exc}")
        return False
    if proc.returncode != 0 or not os.path.isfile(mid_path):
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        log.warning("[JJazzLab] no pude convertir %s (código %s): %s",
                    os.path.basename(sng_path), proc.returncode,
                    " | ".join(tail))
        return False
    log.info(f"[JJazzLab] MIDI generado: {mid_path}")
    return True


# ── lectura del MIDI generado ──────────────────────────────────────────────
def midi_tracks(path: str) -> list[dict]:
    """Pistas del MIDI con su nombre, canal y notas en negras."""
    import mido

    mid = mido.MidiFile(path)
    ppq = mid.ticks_per_beat or 480
    out = []
    for track in mid.tracks:
        name = next((m.name for m in track if m.type == "track_name"), "")
        tick, held, notes = 0, {}, []
        channels = set()
        for msg in track:
            tick += msg.time
            if msg.type == "note_on" and msg.velocity:
                held[(msg.channel, msg.note)] = (tick, msg.velocity)
                channels.add(msg.channel)
            elif msg.type in ("note_off", "note_on"):
                start = held.pop((msg.channel, msg.note), None)
                if start is None:
                    continue
                t0, vel = start
                notes.append((t0 / ppq, max(1, tick - t0) / ppq,
                              int(msg.note), int(vel)))
        notes.sort()
        out.append({"name": name, "channel": min(channels) if channels else None,
                    "notes": notes})
    return out


def bass_track(path: str) -> dict | None:
    """Pista de bajo (nombre ``…Bass…``) del MIDI de JJazzLab."""
    tracks = midi_tracks(path)
    for tr in tracks:
        if "bass" in tr["name"].lower() and tr["notes"]:
            return tr
    for tr in tracks:                       # sin nombre: canal 10 por defecto
        if tr["channel"] == 10 and tr["notes"]:
            return tr
    return None


def write_marker(out_dir: str, name: str, midi: str, track: dict) -> str:
    """Deja ``<nombre>.jjazz.json``: la app lo usa para sonar igual que JJazzLab."""
    path = os.path.join(out_dir, name + ".jjazz.json")
    data = {
        "engine": f"jjazzlab-{TOOLKIT_VERSION}",
        "midi": os.path.basename(midi),
        "bass_channel": track.get("channel"),
        "bass_track": track.get("name", ""),
        "bass_notes": len(track.get("notes") or []),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return path


def read_marker(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None
