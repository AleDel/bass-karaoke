"""
╔══════════════════════════════════════════════════════════════════╗
║         BASS KARAOKE v3 — Feet Don't Fail Me Now               ║
║         Joy Crookes | Bass: Dayna Fisher                        ║
║         Notas leídas desde MusicXML · PyAudio + aubio           ║
╚══════════════════════════════════════════════════════════════════╝

INSTALACIÓN:
  pip install pygame aubio pyaudio numpy

EN WINDOWS si pyaudio falla:
  pip install pipwin && pipwin install pyaudio

CONTROLES:
  ESPACIO    → Play / Pausa (con countdown 4-3-2-1)
  R          → Reiniciar
  ↑ / ↓     → Subir / Bajar tempo (+/-5 BPM)
  < / >      → Ajustar offset MP3 (±0.25 seg)
  D          → Abrir/cerrar selector de dispositivo de audio
  ↑ / ↓     → (en menú de dispositivos) navegar lista
  ENTER      → (en menú de dispositivos) confirmar dispositivo
  M          → Silenciar/activar MP3
  ESC        → Salir (o cerrar menú dispositivos)
"""

import pygame
import numpy as np
import threading
import time
import os
import math
import xml.etree.ElementTree as ET

# ─── Imports opcionales ───────────────────────────────────────────────────────
try:
    import aubio
    AUBIO_OK = True
except ImportError:
    AUBIO_OK = False
    print("[WARN] aubio no encontrado - sin reconocimiento de pitch")

try:
    import pyaudio
    PA_OK = True
except ImportError:
    PA_OK = False
    print("[WARN] pyaudio no encontrado - sin reconocimiento de pitch")

PITCH_AVAILABLE = AUBIO_OK and PA_OK

# ═══════════════════════════════════════════════════════════════════════════════
#  PARÁMETROS DE AUDIO (optimizados para bajo)
# ═══════════════════════════════════════════════════════════════════════════════
SAMPLERATE   = 44100
CHUNK_SIZE   = 2048
WIN_S        = 4096     # ventana grande: captura Mi grave (~41 Hz)
HOP_S        = CHUNK_SIZE
CONF_THRESH  = 0.6
MIN_HZ       = 28.0     # límite inferior del bajo (Si0 ≈ 30 Hz)
MAX_HZ       = 400.0    # límite superior del bajo (nota más aguda útil)

# ═══════════════════════════════════════════════════════════════════════════════
#  CUERDAS DEL BAJO (afinación estándar)
#  Convención MusicXML: string 1=G, 2=D, 3=A, 4=E  (igual que la app antigua)
# ═══════════════════════════════════════════════════════════════════════════════
STRING_OPEN_HZ = {4: 41.20, 3: 55.00, 2: 73.42, 1: 98.00}
STRING_NAMES   = {4: "E", 3: "A", 2: "D", 1: "G"}
STRING_COLORS  = {
    4: (255,  90,  90),   # E — rojo
    3: (255, 200,  70),   # A — amarillo
    2: ( 80, 185, 255),   # D — azul
    1: (120, 255, 140),   # G — verde
}


def fret_to_hz(fret, string):
    return STRING_OPEN_HZ[string] * (2 ** (fret / 12.0))


def hz_to_note_name(hz):
    if hz < 10:
        return "—"
    midi  = 12 * np.log2(hz / 440.0) + 69
    midi  = int(np.round(midi))
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    return f"{names[midi % 12]}{(midi // 12) - 1}"


def notes_match(detected_hz, expected_hz):
    """Compara notas por pitch class (octava independiente). Robusto para bajo."""
    if detected_hz < MIN_HZ or detected_hz > MAX_HZ or expected_hz <= 0:
        return False
    # Primero intento: comparar pitch class (mod 12 del MIDI)
    midi_det = 12 * math.log2(detected_hz / 440.0) + 69
    midi_exp = 12 * math.log2(expected_hz / 440.0) + 69
    if int(round(midi_det)) % 12 == int(round(midi_exp)) % 12:
        return True
    # Segundo intento: ±50 cents con cualquier transposición de octava
    diff = abs(midi_det - midi_exp)
    diff_mod = diff % 12
    cents = min(diff_mod, 12 - diff_mod) * 100
    return cents < 50


# ═══════════════════════════════════════════════════════════════════════════════
#  PARSER MusicXML
# ═══════════════════════════════════════════════════════════════════════════════
def parse_musicxml(filepath):
    """
    Lee mitab.musicxml y devuelve:
        notes   : list[dict] — notas con fret, string, dur (en 1/16), start16, hz, note_name, measure_num
        sections: list[(label, start16)] — marcas de sección (vacío si no las hay en el XML)
        bpm     : float
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    DIVS_DEFAULT = 960      # 960 divisiones por negra (las divide el MusicXML de TuxGuitar)
    bpm          = 113.0    # por defecto; se sobreescribe si hay <metronome>

    notes    = []
    sections = []

    for part in root.findall("part"):
        divs        = DIVS_DEFAULT
        abs_pos     = 0         # posición absoluta en divisiones desde el comienzo de la parte
        measure_abs = 0         # posición absoluta al inicio del compás actual

        for measure in part.findall("measure"):
            measure_num = int(measure.get("number", "0"))
            cur_pos     = 0                 # posición dentro del compás, en divisiones

            # Detectar cambio de divisions y BPM en <attributes> / <direction>
            attr = measure.find("attributes")
            if attr is not None:
                d = attr.find("divisions")
                if d is not None:
                    divs = int(d.text)

            for direction in measure.findall("direction"):
                for metro in direction.findall(".//metronome"):
                    pm = metro.find("per-minute")
                    if pm is not None:
                        bpm = float(pm.text)
                # Marcas de ensayo / texto pueden ser secciones
                for reh in direction.findall(".//rehearsal"):
                    if reh.text:
                        start16 = round((measure_abs + cur_pos) / divs * 4)
                        sections.append((reh.text.strip(), start16))

            # ── Iterar todos los hijos del compás para rastrear posición ────────
            for child in list(measure):
                tag = child.tag

                if tag == "backup":
                    dur_divs = int(child.find("duration").text)
                    cur_pos -= dur_divs

                elif tag == "forward":
                    dur_divs = int(child.find("duration").text)
                    cur_pos += dur_divs

                elif tag == "note":
                    # ¿Es una nota en acorde (no avanza la posición)?
                    is_chord = child.find("chord") is not None
                    # ¿Está en el pentagrama de tablatura?
                    staff_el = child.find("staff")
                    staff    = int(staff_el.text) if staff_el is not None else 1

                    dur_el   = child.find("duration")
                    dur_divs = int(dur_el.text) if dur_el is not None else 0

                    is_rest  = child.find("rest") is not None

                    fret_el   = child.find(".//notations/technical/fret")
                    string_el = child.find(".//notations/technical/string")

                    if (staff == 2
                            and not is_rest
                            and not is_chord
                            and fret_el is not None
                            and string_el is not None):

                        fret   = int(fret_el.text)
                        string = int(string_el.text)
                        hz     = fret_to_hz(fret, string)

                        # Convertir a semicorcheas absolutas (1/16)
                        abs_divs = measure_abs + cur_pos
                        start16  = round(abs_divs / divs * 4)
                        dur16    = max(1, round(dur_divs / divs * 4))

                        notes.append({
                            "fret":        fret,
                            "string":      string,
                            "dur":         dur16,
                            "start16":     start16,
                            "hz":          hz,
                            "note_name":   hz_to_note_name(hz),
                            "measure_num": measure_num,
                            "section":     f"Compás {measure_num}",   # se actualiza abajo
                        })

                    if not is_chord:
                        cur_pos += dur_divs

            # Longitud del compás en divisiones (beats * beat-type factor * divs)
            # TuxGuitar siempre pone time en el primer measure y en cambios
            # Usamos cur_pos máximo o calculamos desde time signature
            # Método simple: avanzar measure_abs en divs*beats (4/4 = 4*divs)
            # Si hay cambio de compás habrá <attributes><time> en este measure
            time_el = measure.find("attributes/time")
            if time_el is not None:
                beats     = int(time_el.find("beats").text)
                beat_type = int(time_el.find("beat-type").text)
                # divisiones por compás
                measure_divs = int(divs * beats * (4 / beat_type))
            else:
                # sin cambio: usar la posición máxima registrada en el compás
                measure_divs = max(cur_pos, divs * 4)   # fallback 4/4

            measure_abs += measure_divs

    # ── Propagar etiquetas de sección a las notas ────────────────────────────
    if sections:
        sec_idx = 0
        for note in notes:
            while (sec_idx + 1 < len(sections)
                   and note["start16"] >= sections[sec_idx + 1][1]):
                sec_idx += 1
            note["section"] = sections[sec_idx][0]

    return notes, sections, bpm


# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES DE UI
# ═══════════════════════════════════════════════════════════════════════════════
W, H        = 1280, 760
FPS         = 60
BPM_DEFAULT = 113

C_BG      = ( 10,  10,  18)
C_BG2     = ( 16,  16,  30)
C_PANEL   = ( 22,  22,  42)
C_DGRAY   = ( 35,  35,  55)
C_ACCENT  = (255, 185,   0)
C_GREEN   = ( 50, 230, 110)
C_RED     = (255,  70,  70)
C_BLUE    = ( 80, 170, 255)
C_WHITE   = (235, 235, 250)
C_GRAY    = ( 95,  95, 115)
C_SECTION = (255, 120,  50)
C_OK      = ( 50, 230, 110)
C_ERR     = (255,  70,  70)
C_WAIT    = (255, 185,   0)
C_OVERLAY = ( 10,  10,  25, 210)     # rgba — fondo modal

# Ruta del MusicXML relativa al script
MUSICXML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "cancion", "mitab.musicxml")


# ═══════════════════════════════════════════════════════════════════════════════
class BassKaraoke:

    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("🎸 Bass Karaoke v3 — Feet Don't Fail Me Now")
        self.clock  = pygame.time.Clock()

        # Fuentes
        self.font_title = pygame.font.SysFont("consolas", 24, bold=True)
        self.font_huge  = pygame.font.SysFont("consolas", 84, bold=True)
        self.font_big   = pygame.font.SysFont("consolas", 34, bold=True)
        self.font_med   = pygame.font.SysFont("consolas", 22, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 16)
        self.font_tiny  = pygame.font.SysFont("consolas", 13)

        # ── Estado de reproducción ──────────────────────────────────────────
        self.bpm         = BPM_DEFAULT
        self.playing     = False
        self.muted       = False
        self.note_idx    = 0
        self.beat_time   = 0.0       # en semicorcheas (1/16)
        self.score_ok    = 0
        self.score_total = 0

        # ── Offset MP3 ──────────────────────────────────────────────────────
        # Segundos de música antes del primer beat de bajo
        # Puede ajustarse con < / > en caliente
        self.mp3_offset_sec = 0.0

        # ── Countdown ────────────────────────────────────────────────────────
        self.counting_down  = False
        self.countdown_beat = 4          # contaremos 4 → 3 → 2 → 1
        self.countdown_timer= 0.0        # acumulador de tiempo en el beat actual
        self._beat_sec      = 60.0 / self.bpm

        # ── Pitch ──────────────────────────────────────────────────────────
        self.detected_hz   = 0.0
        self.detected_note = "—"
        self.note_match    = None        # True / False / None
        self.pitch_lock    = threading.Lock()
        self.audio_running = False
        self.audio_thread  = None

        # ── Dispositivos ───────────────────────────────────────────────────
        self.audio_devices    = []
        self.device_idx       = 0          # índice en la lista filtrada
        self.device_menu_open = False
        self.device_menu_sel  = 0          # selección temporal en el menú
        self._enumerate_devices()

        # ── Estadísticas por sección ───────────────────────────────────────
        self.section_stats = {}    # {section_name: {'ok': 0, 'total': 0}}

        # ── Metrónomo ──────────────────────────────────────────────────────
        self.metro_beat  = 0
        self.metro_flash = 0.0

        # ── Scroll horizontal ──────────────────────────────────────────────
        self.px_per_16th = 32
        self.viewport_x  = 0.0
        self.target_x    = 0.0

        # ── Cargar notas desde MusicXML ────────────────────────────────────
        self.notes    = []
        self.sections = []
        self._load_notes()

        # ── MP3 ────────────────────────────────────────────────────────────
        self.mp3_loaded = False
        self.mp3_path   = self._find_mp3()
        if self.mp3_path:
            try:
                pygame.mixer.music.load(self.mp3_path)
                self.mp3_loaded = True
                print(f"[OK] MP3: {self.mp3_path}")
            except Exception as e:
                print(f"[WARN] MP3: {e}")
        else:
            print("[WARN] No se encontró el MP3 en ./cancion/ ni en ./")

        if PITCH_AVAILABLE and self.audio_devices:
            self._start_audio()

    # ══════════════════════════════════════════════════════════════════════════
    #  CARGA DE NOTAS
    # ══════════════════════════════════════════════════════════════════════════
    def _load_notes(self):
        if not os.path.exists(MUSICXML_PATH):
            print(f"[ERROR] No se encuentra el MusicXML: {MUSICXML_PATH}")
            return
        try:
            notes, sections, bpm = parse_musicxml(MUSICXML_PATH)
            self.notes    = notes
            self.sections = sections
            self.bpm      = bpm
            # Inicializar stats por sección
            for note in notes:
                sec = note["section"]
                if sec not in self.section_stats:
                    self.section_stats[sec] = {"ok": 0, "total": 0}
            print(f"[OK] MusicXML: {len(notes)} notas, {bpm} BPM, {len(sections)} secciones")
        except Exception as e:
            print(f"[ERROR] Parseando MusicXML: {e}")
            import traceback
            traceback.print_exc()

    def _find_mp3(self):
        # Buscar primero en cancion/, luego en el directorio actual
        base = os.path.dirname(os.path.abspath(__file__))
        for folder in [os.path.join(base, "cancion"), base]:
            for f in os.listdir(folder):
                if f.lower().endswith(".mp3"):
                    return os.path.join(folder, f)
        return None

    # ══════════════════════════════════════════════════════════════════════════
    #  AUDIO / PITCH
    # ══════════════════════════════════════════════════════════════════════════
    def _enumerate_devices(self):
        if not PA_OK:
            return
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                self.audio_devices.append((i, info["name"]))
        p.terminate()
        print(f"[Audio] {len(self.audio_devices)} dispositivos de entrada:")
        for li, (did, name) in enumerate(self.audio_devices):
            print(f"  [{li}] ID={did} — {name}")

    def _start_audio(self, list_idx=None):
        self.audio_running = False
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=1.5)
        if list_idx is not None:
            self.device_idx = list_idx % len(self.audio_devices)
        self.audio_running = True
        self.audio_thread  = threading.Thread(target=self._audio_loop, daemon=True)
        self.audio_thread.start()

    def _audio_loop(self):
        dev_id   = self.audio_devices[self.device_idx][0]
        dev_name = self.audio_devices[self.device_idx][1]
        print(f"[Audio] Iniciando: ID={dev_id} — {dev_name}")

        pitch_o = aubio.pitch("yinfast", WIN_S, HOP_S, SAMPLERATE)
        pitch_o.set_unit("Hz")
        pitch_o.set_tolerance(0.8)

        p = pyaudio.PyAudio()
        try:
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=SAMPLERATE,
                input=True,
                input_device_index=dev_id,
                frames_per_buffer=CHUNK_SIZE,
            )
            while self.audio_running:
                try:
                    data    = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    samples = np.frombuffer(data, dtype=np.float32)
                    pitch   = pitch_o(samples)[0]
                    conf    = pitch_o.get_confidence()

                    with self.pitch_lock:
                        if conf > CONF_THRESH and MIN_HZ <= pitch <= MAX_HZ:
                            self.detected_hz   = float(pitch)
                            self.detected_note = hz_to_note_name(float(pitch))
                        else:
                            self.detected_hz   = 0.0
                            self.detected_note = "—"
                except Exception:
                    pass
        except Exception as e:
            print(f"[Audio ERROR] {e}")
        finally:
            try:
                stream.stop_stream(); stream.close()
            except Exception:
                pass
            p.terminate()

    # ══════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════════════
    def px_of(self, beat16):
        return int(beat16 * self.px_per_16th)

    def current_note(self):
        if self.note_idx < len(self.notes):
            return self.notes[self.note_idx]
        return None

    def _beat_duration_sec(self):
        return 60.0 / self.bpm

    # ══════════════════════════════════════════════════════════════════════════
    #  UPDATE
    # ══════════════════════════════════════════════════════════════════════════
    def update(self, dt):
        # ── Countdown ────────────────────────────────────────────────────────
        if self.counting_down:
            self.countdown_timer += dt
            beat_sec = self._beat_duration_sec()
            if self.countdown_timer >= beat_sec:
                self.countdown_timer -= beat_sec
                self.metro_flash = 1.0
                # Actualizar beat visual del metrónomo durante countdown
                self.metro_beat = (4 - self.countdown_beat) % 4
                self.countdown_beat -= 1
                if self.countdown_beat <= 0:
                    self.counting_down = False
                    self._begin_play()
            return

        if not self.playing:
            return

        # 1 negra = 4 semicorcheas, bpm = negras/min
        delta16 = dt * (self.bpm / 60.0) * 4.0
        self.beat_time += delta16

        # Metrónomo visual (cada negra = 4 semicorcheas)
        prev_q = int((self.beat_time - delta16) / 4)
        cur_q  = int(self.beat_time / 4)
        if cur_q > prev_q:
            self.metro_beat  = cur_q % 4
            self.metro_flash = 1.0
        self.metro_flash = max(0.0, self.metro_flash - dt * 5)

        # Solo interactuar con notas cuando beat_time >= 0
        if self.beat_time < 0:
            return

        # Avanzar nota
        while self.note_idx < len(self.notes):
            n = self.notes[self.note_idx]
            if self.beat_time >= n["start16"] + n["dur"]:
                self.note_idx += 1
            else:
                break

        # Comparar pitch con nota actual
        cur = self.current_note()
        if cur and PITCH_AVAILABLE:
            with self.pitch_lock:
                det = self.detected_hz
            if det > 0 and cur["hz"] > 0:
                match = notes_match(det, cur["hz"])
                sec   = cur["section"]
                self.note_match   = match
                self.score_total += 1
                if match:
                    self.score_ok += 1
                    if sec in self.section_stats:
                        self.section_stats[sec]["ok"]    += 1
                if sec in self.section_stats:
                    self.section_stats[sec]["total"] += 1
            else:
                self.note_match = None
        else:
            self.note_match = None

        # Scroll suave: el cursor está en W//3 desde la izquierda
        if cur and self.beat_time >= 0:
            want_x = self.px_of(cur["start16"]) - W // 3
            self.target_x = max(0, want_x)
        self.viewport_x += (self.target_x - self.viewport_x) * min(1.0, dt * 9)

        if self.note_idx >= len(self.notes):
            self.playing = False

    # ══════════════════════════════════════════════════════════════════════════
    #  DRAW
    # ══════════════════════════════════════════════════════════════════════════
    def draw(self):
        self.screen.fill(C_BG)
        self._draw_header()
        self._draw_tab()
        self._draw_note_panel()
        self._draw_metronome()
        self._draw_pitch_panel()
        self._draw_stats_panel()
        self._draw_bottom_bar()

        if self.counting_down:
            self._draw_countdown()

        if self.device_menu_open:
            self._draw_device_menu()

        pygame.display.flip()

    # ── Header ────────────────────────────────────────────────────────────────
    def _draw_header(self):
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, W, 55))
        pygame.draw.line(self.screen, C_ACCENT, (0, 55), (W, 55), 2)

        title = self.font_title.render(
            "🎸  Feet Don't Fail Me Now  —  Joy Crookes  |  Bass: Dayna Fisher",
            True, C_WHITE)
        self.screen.blit(title, (16, 16))

        bpm_t = self.font_med.render(f"♩ {self.bpm:.0f} BPM", True, C_ACCENT)
        self.screen.blit(bpm_t, (W - 170, 16))

        if self.score_total > 0:
            pct  = int(100 * self.score_ok / self.score_total)
            col  = C_GREEN if pct > 70 else C_RED if pct < 40 else C_ACCENT
            sc_t = self.font_med.render(f"{pct}%  ✓", True, col)
            self.screen.blit(sc_t, (W - 350, 16))

        # Offset MP3
        off_col = C_GRAY if self.mp3_offset_sec == 0 else C_BLUE
        off_t   = self.font_tiny.render(
            f"offset MP3: {self.mp3_offset_sec:+.2f}s  < >", True, off_col)
        self.screen.blit(off_t, (W - 350, 40))

    # ── Tablatura ─────────────────────────────────────────────────────────────
    def _draw_tab(self):
        TAB_Y    = 60
        TAB_H    = 330
        CURSOR_X = W // 3

        # Y de cada cuerda (G arriba → E abajo)
        # string 1=G, 2=D, 3=A, 4=E
        LINE_MARGIN = 10
        USABLE_H    = TAB_H - LINE_MARGIN * 2
        STR_Y = {
            1: TAB_Y + LINE_MARGIN + int(USABLE_H * 0 / 3),   # G — arriba
            2: TAB_Y + LINE_MARGIN + int(USABLE_H * 1 / 3),   # D
            3: TAB_Y + LINE_MARGIN + int(USABLE_H * 2 / 3),   # A
            4: TAB_Y + LINE_MARGIN + int(USABLE_H * 3 / 3),   # E — abajo
        }

        pygame.draw.rect(self.screen, C_BG2, (0, TAB_Y, W, TAB_H))

        # Etiquetas de cuerda (izquierda)
        for s, y in STR_Y.items():
            label = self.font_med.render(STRING_NAMES[s], True, STRING_COLORS[s])
            self.screen.blit(label, (6, y - label.get_height() // 2))

        # Líneas de cuerda
        for s, y in STR_Y.items():
            thick = 2 if s == 4 else 1
            pygame.draw.line(self.screen, STRING_COLORS[s],
                             (36, y), (W, y), thick)

        # Cursor dorado vertical
        pygame.draw.line(self.screen, C_ACCENT,
                         (CURSOR_X, TAB_Y + 4), (CURSOR_X, TAB_Y + TAB_H - 4), 2)
        # Triángulo indicador arriba
        pygame.draw.polygon(self.screen, C_ACCENT, [
            (CURSOR_X - 8, TAB_Y + 2),
            (CURSOR_X + 8, TAB_Y + 2),
            (CURSOR_X,     TAB_Y + 18),
        ])

        vx = int(self.viewport_x)

        # Barras de compás (cada 16 semicorcheas)
        if self.notes:
            total16 = self.notes[-1]["start16"] + self.notes[-1]["dur"]
        else:
            total16 = 0

        # Número de compás encima
        prev_measure = -1
        for note in self.notes:
            nx = self.px_of(note["start16"]) - vx + CURSOR_X
            if 36 < nx < W and note["measure_num"] != prev_measure:
                prev_measure = note["measure_num"]
                m_lbl = self.font_tiny.render(str(note["measure_num"]), True, C_DGRAY)
                self.screen.blit(m_lbl, (nx - m_lbl.get_width() // 2, TAB_Y + 2))

        # Barras de compás
        for b in range(0, total16 + 16, 16):
            bx = self.px_of(b) - vx + CURSOR_X
            if 36 < bx < W:
                pygame.draw.line(self.screen, C_DGRAY,
                                 (bx, TAB_Y + LINE_MARGIN),
                                 (bx, TAB_Y + TAB_H - LINE_MARGIN), 1)

        # Marcadores de sección
        for label, b16 in self.sections:
            sx = self.px_of(b16) - vx + CURSOR_X
            if 36 < sx < W:
                pygame.draw.line(self.screen, C_SECTION,
                                 (sx, TAB_Y), (sx, TAB_Y + TAB_H), 1)
                lbl = self.font_tiny.render(f"[{label}]", True, C_SECTION)
                self.screen.blit(lbl, (sx + 3, TAB_Y + LINE_MARGIN + 2))

        # Notas
        FRET_RADIUS = 14     # radio del círculo de la nota normal
        CUR_RADIUS  = 18     # nota actual (más grande)

        for i, note in enumerate(self.notes):
            nx = self.px_of(note["start16"]) - vx + CURSOR_X
            if nx < 20 or nx > W + 100:
                continue

            ny      = STR_Y[note["string"]]
            is_cur  = (i == self.note_idx)
            is_past = (i < self.note_idx)

            # ── Color según estado ────────────────────────────────────────
            if is_cur:
                if self.note_match is True:
                    col = C_OK
                elif self.note_match is False:
                    col = C_ERR
                else:
                    col = C_WAIT
                r = CUR_RADIUS
                # Halo pulsante animado
                pulse = 0.5 + 0.5 * math.sin(time.time() * 9)
                hr    = int(r + 8 + pulse * 5)
                hs    = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
                pygame.draw.circle(hs, (*col, 55), (hr, hr), hr)
                self.screen.blit(hs, (nx - hr, ny - hr))
            elif is_past:
                col = (45, 45, 70)
                r   = 11
            else:
                col = STRING_COLORS[note["string"]]
                r   = FRET_RADIUS

            # ── Barra de duración ──────────────────────────────────────────
            dur_px = int(note["dur"] * self.px_per_16th) - 2
            if dur_px > r * 2 + 4 and not is_past:
                bar_color = col if is_cur else (*col, 110)
                if is_cur:
                    pygame.draw.line(self.screen, col,
                                     (nx, ny), (nx + dur_px, ny), 3)
                else:
                    s = pygame.Surface((dur_px, 3), pygame.SRCALPHA)
                    pygame.draw.line(s, (*col, 110), (0, 1), (dur_px, 1), 3)
                    self.screen.blit(s, (nx, ny - 1))

            # ── Círculo de nota ────────────────────────────────────────────
            pygame.draw.circle(self.screen, col,     (nx, ny), r)
            if not is_past:
                pygame.draw.circle(self.screen, C_BG, (nx, ny), r - 3)

            # ── Número de traste ───────────────────────────────────────────
            f   = self.font_med   if is_cur  else \
                  self.font_small if not is_past else self.font_tiny
            txt_col = col if is_past else C_WHITE
            txt = f.render(str(note["fret"]), True, txt_col)
            self.screen.blit(txt, (nx - txt.get_width() // 2,
                                   ny - txt.get_height() // 2))

        pygame.draw.line(self.screen, C_DGRAY,
                         (0, TAB_Y + TAB_H), (W, TAB_Y + TAB_H), 1)

    # ── Panel de nota actual (izquierda inferior) ─────────────────────────────
    def _draw_note_panel(self):
        px, py, pw, ph = 8, 396, 220, 200
        pygame.draw.rect(self.screen, C_PANEL, (px, py, pw, ph), border_radius=10)
        pygame.draw.rect(self.screen, C_ACCENT, (px, py, pw, ph), 2, border_radius=10)

        lbl_s = self.font_tiny.render("SIGUIENTE NOTA", True, C_GRAY)
        self.screen.blit(lbl_s, (px + pw // 2 - lbl_s.get_width() // 2, py + 6))

        cur = self.current_note()
        if not cur:
            t = self.font_big.render("FIN 🎉", True, C_GREEN)
            self.screen.blit(t, (px + pw // 2 - t.get_width() // 2,
                                 py + ph // 2 - 20))
            return

        fret_big = self.font_huge.render(str(cur["fret"]), True, C_ACCENT)
        self.screen.blit(fret_big, (px + pw // 2 - fret_big.get_width() // 2,
                                    py + 20))

        scol  = STRING_COLORS[cur["string"]]
        s_lbl = self.font_med.render(
            f"Cuerda {STRING_NAMES[cur['string']]}", True, scol)
        self.screen.blit(s_lbl, (px + pw // 2 - s_lbl.get_width() // 2, py + 120))

        n_lbl = self.font_med.render(cur["note_name"], True, C_BLUE)
        self.screen.blit(n_lbl, (px + pw // 2 - n_lbl.get_width() // 2, py + 150))

        sec = self.font_tiny.render(cur["section"], True, C_GRAY)
        self.screen.blit(sec, (px + pw // 2 - sec.get_width() // 2, py + 178))

    # ── Metrónomo ─────────────────────────────────────────────────────────────
    def _draw_metronome(self):
        mx, my, bw = 238, 402, 48
        lbl = self.font_tiny.render("METRÓNOMO", True, C_GRAY)
        self.screen.blit(lbl, (mx, my - 15))
        for b in range(4):
            bx     = mx + b * (bw + 5)
            active = (self.playing or self.counting_down) and (b == self.metro_beat)
            c = C_ACCENT if (active and b == 0) else C_WHITE if active else C_DGRAY
            pygame.draw.rect(self.screen, c,
                             (bx, my, bw, 34), border_radius=5)
            if b == 0:
                pygame.draw.rect(self.screen, C_ACCENT,
                                 (bx, my, bw, 34), 2, border_radius=5)
            n = self.font_med.render(str(b + 1), True,
                                     C_BG if active else C_GRAY)
            self.screen.blit(n, (bx + bw // 2 - n.get_width() // 2, my + 6))

    # ── Panel pitch ───────────────────────────────────────────────────────────
    def _draw_pitch_panel(self):
        px, py, pw, ph = 238, 448, 640, 148
        pygame.draw.rect(self.screen, C_PANEL, (px, py, pw, ph), border_radius=10)

        with self.pitch_lock:
            det_hz   = self.detected_hz
            det_note = self.detected_note

        cur = self.current_note()

        # Título / dispositivo activo
        if PITCH_AVAILABLE and self.audio_devices:
            dev_name = self.audio_devices[self.device_idx][1][:40]
            t = self.font_tiny.render(
                f"ENTRADA [{self.device_idx}]: {dev_name}   |  D = cambiar",
                True, C_GRAY)
        else:
            t = self.font_tiny.render(
                "pip install pyaudio aubio  →  reconocimiento de pitch",
                True, C_RED)
        self.screen.blit(t, (px + 10, py + 8))

        # Nota detectada (grande)
        col = C_OK if self.note_match is True else \
              C_ERR if self.note_match is False else C_GRAY
        big = self.font_big.render(det_note, True, col)
        self.screen.blit(big, (px + 12, py + 26))

        if det_hz > 0:
            hz_t = self.font_small.render(f"{det_hz:.1f} Hz", True, C_GRAY)
            self.screen.blit(hz_t, (px + 12, py + 78))

        # Nota esperada
        if cur:
            exp = self.font_med.render(
                f"Esperada:  {cur['note_name']}  (traste {cur['fret']}  cuerda {STRING_NAMES[cur['string']]})",
                True, C_WHITE)
            self.screen.blit(exp, (px + 12, py + 110))

        # OK / FAIL
        if self.note_match is True:
            ok = self.font_big.render("✓  CORRECTO", True, C_OK)
            self.screen.blit(ok, (px + 160, py + 30))
        elif self.note_match is False:
            er = self.font_big.render("✗  AJUSTA", True, C_ERR)
            self.screen.blit(er, (px + 160, py + 30))

        # Barra de cents
        if PITCH_AVAILABLE and cur and det_hz > 0 and cur["hz"] > 0:
            ratio = det_hz / cur["hz"]
            if ratio > 0:
                cents = 1200 * math.log2(ratio)
                # Ajustar a octava más cercana
                while cents > 600:
                    cents -= 1200
                while cents < -600:
                    cents += 1200
                cents_c = max(-120, min(120, cents))
                bx, by2, bw2, bh = px + 160, py + 82, 460, 16
                pygame.draw.rect(self.screen, C_DGRAY, (bx, by2, bw2, bh), border_radius=4)
                cx = bx + bw2 // 2
                mk = cx + int(cents_c / 120 * (bw2 // 2))
                bc = C_OK if abs(cents) < 20 else C_ACCENT if abs(cents) < 60 else C_ERR
                pygame.draw.rect(self.screen, bc,
                                 (min(cx, mk), by2 + 3, abs(mk - cx) + 2, bh - 6),
                                 border_radius=3)
                pygame.draw.line(self.screen, C_WHITE, (cx, by2), (cx, by2 + bh), 2)
                cl = self.font_tiny.render(f"{cents:+.0f} cents", True, C_GRAY)
                self.screen.blit(cl, (bx, by2 + bh + 3))

    # ── Panel de estadísticas por sección ────────────────────────────────────
    def _draw_stats_panel(self):
        px, py, pw, ph = 885, 396, 385, 200
        pygame.draw.rect(self.screen, C_PANEL, (px, py, pw, ph), border_radius=10)

        hdr = self.font_tiny.render("ACIERTOS POR SECCIÓN", True, C_GRAY)
        self.screen.blit(hdr, (px + 10, py + 8))

        if not self.section_stats:
            return

        # Mostrar solo las secciones que tienen actividad (pasan por pantalla)
        secciones_con_datos = [
            (sec, d) for sec, d in self.section_stats.items() if d["total"] > 0
        ]
        # Si no hay aún, mostrar todas
        if not secciones_con_datos:
            secciones_con_datos = list(self.section_stats.items())[:10]

        max_visible = 9
        secciones_con_datos = secciones_con_datos[-max_visible:]   # últimas N

        row_h = (ph - 30) // max(len(secciones_con_datos), 1)
        row_h = min(row_h, 18)

        for idx, (sec, d) in enumerate(secciones_con_datos):
            ry = py + 26 + idx * row_h

            # Nombre de sección truncado
            name = sec[:18]
            n_lbl = self.font_tiny.render(name, True, C_GRAY)
            self.screen.blit(n_lbl, (px + 8, ry))

            # Barra de progreso
            bar_x, bar_w, bar_h = px + 145, 180, 10
            pygame.draw.rect(self.screen, C_DGRAY,
                             (bar_x, ry + 2, bar_w, bar_h), border_radius=3)
            if d["total"] > 0:
                pct    = d["ok"] / d["total"]
                fill_w = int(bar_w * pct)
                col    = C_GREEN if pct > 0.70 else C_ACCENT if pct > 0.40 else C_RED
                if fill_w > 0:
                    pygame.draw.rect(self.screen, col,
                                     (bar_x, ry + 2, fill_w, bar_h), border_radius=3)
                pct_t = self.font_tiny.render(f"{int(pct*100):3d}%", True, col)
                self.screen.blit(pct_t, (bar_x + bar_w + 4, ry))

    # ── Bottom bar ────────────────────────────────────────────────────────────
    def _draw_bottom_bar(self):
        by = H - 52
        pygame.draw.rect(self.screen, C_PANEL, (0, by, W, 52))
        pygame.draw.line(self.screen, C_DGRAY, (0, by), (W, by), 1)

        hints = [
            ("SPC", "Play/Pausa"), ("R", "Reiniciar"),
            ("↑↓", "Tempo"), ("<>", "Offset MP3"),
            ("D", "Dispositivo"), ("M", "Mute"), ("ESC", "Salir"),
        ]
        x = 10
        for key, desc in hints:
            k = self.font_small.render(key, True, C_ACCENT)
            d = self.font_small.render(f" {desc}  ", True, C_GRAY)
            self.screen.blit(k, (x, by + 8))
            x += k.get_width()
            self.screen.blit(d, (x, by + 8))
            x += d.get_width()

        # Estado MP3
        if self.mp3_loaded:
            col  = C_GREEN if not self.muted else C_GRAY
            mp3s = os.path.basename(self.mp3_path) + (" [MUTE]" if self.muted else " ♫")
        else:
            col  = C_RED
            mp3s = "MP3 no encontrado — coloca el archivo en cancion/"
        mp3t = self.font_small.render(mp3s, True, col)
        self.screen.blit(mp3t, (10, by + 30))

        # Estado del parser
        num_notes = len(self.notes)
        src_lbl   = self.font_tiny.render(
            f"MusicXML: {num_notes} notas  |  {os.path.basename(MUSICXML_PATH)}",
            True, C_GRAY if num_notes > 0 else C_RED)
        self.screen.blit(src_lbl, (W - src_lbl.get_width() - 10, by + 32))

    # ── Countdown overlay ─────────────────────────────────────────────────────
    def _draw_countdown(self):
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        num   = str(self.countdown_beat)
        txt   = self.font_huge.render(num, True, C_ACCENT)
        self.screen.blit(txt, (W // 2 - txt.get_width() // 2,
                                H // 2 - txt.get_height() // 2 - 20))

        sub = self.font_med.render("preparado…", True, C_GRAY)
        self.screen.blit(sub, (W // 2 - sub.get_width() // 2,
                                H // 2 + txt.get_height() // 2))

    # ── Menú selector de dispositivo ─────────────────────────────────────────
    def _draw_device_menu(self):
        mw, mh = 660, 340
        mx, my = W // 2 - mw // 2, H // 2 - mh // 2

        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill(C_OVERLAY)
        self.screen.blit(overlay, (0, 0))

        pygame.draw.rect(self.screen, C_PANEL, (mx, my, mw, mh), border_radius=12)
        pygame.draw.rect(self.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

        hdr = self.font_med.render("SELECCIONA DISPOSITIVO DE ENTRADA", True, C_ACCENT)
        self.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))

        pygame.draw.line(self.screen, C_DGRAY,
                         (mx + 10, my + 44), (mx + mw - 10, my + 44), 1)

        if not self.audio_devices:
            err = self.font_med.render("No se encontraron dispositivos de entrada",
                                       True, C_RED)
            self.screen.blit(err, (mx + 20, my + 80))
        else:
            row_h    = 28
            max_rows = (mh - 80) // row_h
            start    = max(0, self.device_menu_sel - max_rows + 1)
            for i, (did, name) in enumerate(self.audio_devices):
                if i < start:
                    continue
                row_i = i - start
                if row_i >= max_rows:
                    break
                ry     = my + 52 + row_i * row_h
                is_sel = (i == self.device_menu_sel)
                is_cur = (i == self.device_idx)
                if is_sel:
                    pygame.draw.rect(self.screen, C_DGRAY,
                                     (mx + 6, ry - 2, mw - 12, row_h - 2),
                                     border_radius=5)
                marker = "●" if is_cur else " "
                col    = C_GREEN if is_cur else C_WHITE if is_sel else C_GRAY
                lbl    = self.font_small.render(
                    f"{marker} [{i}]  {name[:56]}", True, col)
                self.screen.blit(lbl, (mx + 16, ry))

        hint = self.font_tiny.render(
            "↑↓ navegar    ENTER confirmar    ESC cerrar", True, C_GRAY)
        self.screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 24))

    # ══════════════════════════════════════════════════════════════════════════
    #  CONTROLES
    # ══════════════════════════════════════════════════════════════════════════
    def toggle_play(self):
        if self.counting_down:
            # Cancelar countdown
            self.counting_down = False
            return
        if self.playing:
            self.playing = False
            if self.mp3_loaded:
                pygame.mixer.music.pause()
        else:
            # Iniciar countdown (4 beats) antes de tocar
            self.counting_down  = True
            self.countdown_beat = 4
            self.countdown_timer = 0.0
            self.metro_beat     = 0

    def _begin_play(self):
        """Llamado cuando el countdown termina."""
        self.playing   = True
        # beat_time parte en negativo según el offset del MP3
        self.beat_time = -(self.mp3_offset_sec * (self.bpm / 60.0) * 4.0)
        if self.mp3_loaded:
            if self.score_total == 0 and self.note_idx == 0:
                pygame.mixer.music.play()
            else:
                # Reanudar desde la posición actual
                try:
                    pygame.mixer.music.unpause()
                except Exception:
                    pygame.mixer.music.play()

    def restart(self):
        self.playing        = False
        self.counting_down  = False
        self.note_idx       = 0
        self.beat_time      = 0.0
        self.viewport_x     = 0.0
        self.target_x       = 0.0
        self.score_ok       = 0
        self.score_total    = 0
        self.note_match     = None
        self.metro_beat     = 0
        self.metro_flash    = 0.0
        # Resetear stats
        for sec in self.section_stats:
            self.section_stats[sec] = {"ok": 0, "total": 0}
        if self.mp3_loaded:
            pygame.mixer.music.stop()

    def change_bpm(self, d):
        self.bpm = max(40, min(220, self.bpm + d))

    def change_offset(self, d):
        self.mp3_offset_sec = round(self.mp3_offset_sec + d, 2)

    def toggle_mute(self):
        if self.mp3_loaded:
            self.muted = not self.muted
            pygame.mixer.music.set_volume(0.0 if self.muted else 1.0)

    def open_device_menu(self):
        self.device_menu_open = True
        self.device_menu_sel  = self.device_idx

    def close_device_menu(self):
        self.device_menu_open = False

    def confirm_device(self):
        if not self.audio_devices:
            return
        if PITCH_AVAILABLE:
            self._start_audio(self.device_menu_sel)
        self.close_device_menu()

    # ══════════════════════════════════════════════════════════════════════════
    #  LOOP PRINCIPAL
    # ══════════════════════════════════════════════════════════════════════════
    def run(self):
        last    = time.time()
        running = True

        while running:
            now = time.time()
            dt  = min(now - last, 0.05)
            last = now

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    k = event.key

                    # ── Menú de dispositivos abierto ──────────────────────
                    if self.device_menu_open:
                        if k == pygame.K_ESCAPE:
                            self.close_device_menu()
                        elif k == pygame.K_d:
                            self.close_device_menu()
                        elif k == pygame.K_UP:
                            self.device_menu_sel = max(0, self.device_menu_sel - 1)
                        elif k == pygame.K_DOWN:
                            self.device_menu_sel = min(
                                len(self.audio_devices) - 1,
                                self.device_menu_sel + 1)
                        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            self.confirm_device()
                        continue   # no procesar más teclas mientras el menú está abierto

                    # ── Teclas normales ───────────────────────────────────
                    if   k == pygame.K_ESCAPE:         running = False
                    elif k == pygame.K_SPACE:          self.toggle_play()
                    elif k == pygame.K_r:              self.restart()
                    elif k == pygame.K_UP:             self.change_bpm(+5)
                    elif k == pygame.K_DOWN:           self.change_bpm(-5)
                    elif k == pygame.K_m:              self.toggle_mute()
                    elif k == pygame.K_d:              self.open_device_menu()
                    elif k == pygame.K_COMMA:          self.change_offset(-0.25)   # <
                    elif k == pygame.K_PERIOD:         self.change_offset(+0.25)   # >
                    # Soporte alternativo con < > sin shift en teclados es
                    elif k == pygame.K_LESS:           self.change_offset(-0.25)
                    elif k == pygame.K_GREATER:        self.change_offset(+0.25)

            self.update(dt)
            self.draw()
            self.clock.tick(FPS)

        self.audio_running = False
        pygame.quit()


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 64)
    print("  BASS KARAOKE v3 — Feet Don't Fail Me Now | Joy Crookes")
    print("=" * 64)
    print(f"  PyAudio  : {'✓ OK' if PA_OK    else '✗  pip install pyaudio'}")
    print(f"  Aubio    : {'✓ OK' if AUBIO_OK else '✗  pip install aubio'}")
    print(f"  Pitch    : {'✓ ACTIVO' if PITCH_AVAILABLE else '✗ DESACTIVADO'}")
    print(f"  MusicXML : {MUSICXML_PATH}")
    print("=" * 64)
    BassKaraoke().run()
