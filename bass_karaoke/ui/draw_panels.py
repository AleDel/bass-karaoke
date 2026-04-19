"""
Dibuja los paneles de la zona inferior:
  - Panel nota actual
  - Metrónomo
  - Panel pitch
  - Panel estadísticas por sección
  - Bottom bar
"""
import math
import pygame

from ..config import (
    W, H, LOWER_Y, LOWER_H, BOTTOM_Y,
    PIANO_START_MIDI, PIANO_END_MIDI,
    STRING_NAMES, STRING_COLORS,
    C_BG, C_ACCENT, C_DGRAY, C_GRAY, C_WHITE, C_PANEL, C_BLUE,
    C_OK, C_ERR, C_WAIT, C_GREEN, C_RED,
    PITCH_METHODS, MIN_HZ,
)


def draw_note_panel(app) -> None:
    px, py, pw, ph = 8, LOWER_Y, 205, LOWER_H
    pygame.draw.rect(app.screen, C_PANEL, (px, py, pw, ph), border_radius=10)
    pygame.draw.rect(app.screen, C_ACCENT, (px, py, pw, ph), 2, border_radius=10)

    hdr = app.font_tiny.render("SIGUIENTE NOTA", True, C_GRAY)
    app.screen.blit(hdr, (px + pw // 2 - hdr.get_width() // 2, py + 6))

    cur = app.current_note()
    if not cur:
        t = app.font_big.render("FIN!", True, C_GREEN)
        app.screen.blit(t, (px + pw // 2 - t.get_width() // 2,
                             py + ph // 2 - 20))
        return

    fret_big = app.font_huge.render(str(cur["fret"]), True, C_ACCENT)
    app.screen.blit(fret_big, (px + pw // 2 - fret_big.get_width() // 2, py + 16))

    scol  = STRING_COLORS[cur["string"]]
    s_lbl = app.font_med.render(
        f"Cuerda {STRING_NAMES[cur['string']]}", True, scol)
    app.screen.blit(s_lbl, (px + pw // 2 - s_lbl.get_width() // 2, py + 102))

    n_lbl = app.font_small.render(cur["note_name"], True, C_BLUE)
    app.screen.blit(n_lbl, (px + pw // 2 - n_lbl.get_width() // 2, py + 128))

    sec = app.font_tiny.render(cur["section"], True, C_GRAY)
    app.screen.blit(sec, (px + pw // 2 - sec.get_width() // 2, py + 152))


def draw_metronome(app) -> None:
    mx, my, bw = 220, LOWER_Y + 4, 42
    lbl = app.font_tiny.render("METRO", True, C_GRAY)
    app.screen.blit(lbl, (mx, my - 13))
    for b in range(4):
        bx     = mx + b * (bw + 4)
        active = (app.playing or app.counting_down) and (b == app.metro_beat)
        c = C_ACCENT if (active and b == 0) else C_WHITE if active else C_DGRAY
        pygame.draw.rect(app.screen, c, (bx, my, bw, 28), border_radius=5)
        if b == 0:
            pygame.draw.rect(app.screen, C_ACCENT, (bx, my, bw, 28), 2, border_radius=5)
        n = app.font_med.render(str(b + 1), True, (10, 10, 18) if active else C_GRAY)
        app.screen.blit(n, (bx + bw // 2 - n.get_width() // 2, my + 4))


def draw_pitch_panel(app) -> None:
    from ..audio import PITCH_AVAILABLE

    px, py, pw, ph = 220, LOWER_Y + 38, 634, 154
    pygame.draw.rect(app.screen, C_PANEL, (px, py, pw, ph), border_radius=10)

    with app.pitch_lock:
        det_hz   = app.detected_hz
        det_note = app.detected_note
        stb_hz   = app.stable_hz
        stb_note = app.stable_note
    cur = app.current_note()

    if PITCH_AVAILABLE and app.audio_devices:
        dev_name = app.audio_devices[app.device_idx][1][:44]
        t = app.font_tiny.render(
            f"ENTRADA [{app.device_idx}]: {dev_name}  |  D=cambiar",
            True, C_GRAY)
    else:
        t = app.font_tiny.render("pip install pyaudio aubio", True, C_RED)
    app.screen.blit(t, (px + 10, py + 8))

    col = (C_OK  if app.note_match is True  else
           C_ERR if app.note_match is False else C_GRAY)
    big = app.font_big.render(stb_note, True, col)
    app.screen.blit(big, (px + 10, py + 24))
    if det_hz > 0 and det_note != stb_note:
        raw_t = app.font_tiny.render(f"crudo: {det_note}", True, C_DGRAY)
        app.screen.blit(raw_t, (px + 10, py + 62))

    if stb_hz > 0:
        hz_t = app.font_small.render(f"{stb_hz:.1f} Hz", True, C_GRAY)
        app.screen.blit(hz_t, (px + 10, py + 72))

    if cur:
        exp = app.font_small.render(
            f"Esperada: {cur['note_name']}  (tr.{cur['fret']} Cuerda {STRING_NAMES[cur['string']]})",
            True, C_WHITE)
        app.screen.blit(exp, (px + 10, py + 116))

    if app.note_match is True:
        app.screen.blit(app.font_big.render("OK!", True, C_OK),
                        (px + 160, py + 28))
    elif app.note_match is False:
        app.screen.blit(app.font_big.render("Ajusta", True, C_ERR),
                        (px + 160, py + 28))

    if PITCH_AVAILABLE and cur and stb_hz > 0 and cur["hz"] > 0:
        ratio = stb_hz / cur["hz"]
        if ratio > 0:
            cents = 1200 * math.log2(ratio)
            while cents >  600: cents -= 1200
            while cents < -600: cents += 1200
            cents_c = max(-120, min(120, cents))
            bx, by2, bw2, bh = px + 160, py + 75, 450, 13
            pygame.draw.rect(app.screen, C_DGRAY, (bx, by2, bw2, bh), border_radius=3)
            cx = bx + bw2 // 2
            mk = cx + int(cents_c / 120 * (bw2 // 2))
            bc = C_OK if abs(cents) < 20 else C_ACCENT if abs(cents) < 60 else C_ERR
            if mk != cx:
                pygame.draw.rect(app.screen, bc,
                                 (min(cx, mk), by2 + 2, abs(mk - cx) + 2, bh - 4),
                                 border_radius=2)
            pygame.draw.line(app.screen, C_WHITE, (cx, by2), (cx, by2 + bh), 2)
            app.screen.blit(
                app.font_tiny.render(f"{cents:+.0f} cents", True, C_GRAY),
                (bx, by2 + bh + 3))


def draw_stats_panel(app) -> None:
    px, py, pw, ph = 860, LOWER_Y, 412, LOWER_H
    pygame.draw.rect(app.screen, C_PANEL, (px, py, pw, ph), border_radius=10)

    hdr = app.font_tiny.render("ACIERTOS POR SECCION", True, C_GRAY)
    app.screen.blit(hdr, (px + 8, py + 6))

    with_data = [(s, d) for s, d in app.section_stats.items() if d["total"] > 0]
    if not with_data:
        with_data = list(app.section_stats.items())[:10]

    max_vis  = 10
    with_data = with_data[-max_vis:]
    row_h    = max(14, min(18, (ph - 26) // max(len(with_data), 1)))

    for idx, (sec, d) in enumerate(with_data):
        ry = py + 22 + idx * row_h
        lbl = app.font_tiny.render(sec[:18], True, C_GRAY)
        app.screen.blit(lbl, (px + 6, ry))
        bx, bw2, bh = px + 148, 196, 9
        pygame.draw.rect(app.screen, C_DGRAY, (bx, ry + 2, bw2, bh), border_radius=2)
        if d["total"] > 0:
            pct = d["ok"] / d["total"]
            fw  = int(bw2 * pct)
            bc  = C_GREEN if pct > 0.70 else C_ACCENT if pct > 0.40 else C_RED
            if fw > 0:
                pygame.draw.rect(app.screen, bc,
                                 (bx, ry + 2, fw, bh), border_radius=2)
            app.screen.blit(
                app.font_tiny.render(f"{int(pct*100):3d}%", True, bc),
                (bx + bw2 + 4, ry))


def draw_bottom_bar(app) -> None:
    import os
    pygame.draw.rect(app.screen, C_PANEL, (0, BOTTOM_Y, W, H - BOTTOM_Y))
    pygame.draw.line(app.screen, C_DGRAY, (0, BOTTOM_Y), (W, BOTTOM_Y), 1)

    hints = [
        ("SPC", "Play"), ("R", "Reinicio"), ("Up/Dn", "Tempo"),
        (",.", "offset±0.05"), ("S+,.", "offset±0.5"),
        ("D", "Disp"), ("T", "Tuner"), ("M", "Mute"),
        ("F5", "Guardar"), ("F6", "Cargar"), ("ESC", "Salir"),
    ]
    x = 8
    for key, desc in hints:
        k = app.font_small.render(key, True, C_ACCENT)
        d = app.font_small.render(f" {desc}  ", True, C_GRAY)
        app.screen.blit(k, (x, BOTTOM_Y + 7))
        x += k.get_width()
        app.screen.blit(d, (x, BOTTOM_Y + 7))
        x += d.get_width()

    if app.mp3_path:
        engine = " [varispeed]" if (app._vsp and app._vsp.loaded) else " [fixed]"
        sfx    = " [MUTE]" if app.muted else ""
        col    = C_GREEN if not app.muted else C_GRAY
        mp3s   = os.path.basename(app.mp3_path) + sfx + engine
    else:
        col  = C_RED
        mp3s = "MP3 no encontrado"
    app.screen.blit(app.font_small.render(mp3s, True, col), (8, BOTTOM_Y + 30))

    src = app.font_tiny.render(
        f"MusicXML: {len(app.notes)} notas",
        True, C_GRAY if app.notes else C_RED)
    app.screen.blit(src, (W - src.get_width() - 8, BOTTOM_Y + 34))

    if getattr(app, '_config_msg_timer', 0) > 0:
        msg = app.font_med.render(app._config_msg, True, app._config_msg_col)
        app.screen.blit(msg, (W // 2 - msg.get_width() // 2, BOTTOM_Y + 14))
