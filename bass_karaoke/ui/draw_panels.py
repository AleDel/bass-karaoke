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

    if not app.notes:
        t = app.font_big.render("SIN NOTAS", True, C_RED)
        app.screen.blit(t, (px + pw // 2 - t.get_width() // 2,
                             py + ph // 2 - 28))
        h = app.font_tiny.render("revisa el MusicXML", True, C_GRAY)
        app.screen.blit(h, (px + pw // 2 - h.get_width() // 2,
                             py + ph // 2 + 12))
        return

    cur = app.current_note()
    if not cur:
        # En intros y silencios no hay nota sonando, pero el panel se llama
        # SIGUIENTE NOTA: mostrar la próxima en vez de un "FIN!" engañoso.
        # FIN! solo cuando ya no quedan notas (note_idx al final).
        if app.note_idx < len(app.notes):
            cur = app.notes[app.note_idx]
        else:
            t = app.font_big.render("FIN!", True, C_GREEN)
            app.screen.blit(t, (px + pw // 2 - t.get_width() // 2,
                                 py + ph // 2 - 20))
            return

    fret_big = app.font_huge.render(str(cur["fret"]), True, C_ACCENT)
    app.screen.blit(fret_big, (px + pw // 2 - fret_big.get_width() // 2, py + 12))

    scol  = STRING_COLORS[cur["string"]]
    s_lbl = app.font_med.render(
        f"Cuerda {STRING_NAMES[cur['string']]}", True, scol)
    app.screen.blit(s_lbl, (px + pw // 2 - s_lbl.get_width() // 2, py + 90))

    n_lbl = app.font_small.render(cur["note_name"], True, C_BLUE)
    app.screen.blit(n_lbl, (px + pw // 2 - n_lbl.get_width() // 2, py + 112))

    sec = app.font_tiny.render(cur["section"], True, C_GRAY)
    app.screen.blit(sec, (px + pw // 2 - sec.get_width() // 2, py + 130))


def draw_metronome(app) -> None:
    mx, my, bw = 220, LOWER_Y + 4, 42
    nbeats   = max(2, min(12, int(getattr(app, 'beats_per_bar', 4) or 4)))
    metro_on = getattr(app, 'metro_sound', True)
    lbl_col  = C_GRAY if metro_on else (60, 60, 80)
    lbl_str  = ("METRO" if metro_on else "METRO(off)") + f"  {nbeats}/4"
    lbl = app.font_tiny.render(lbl_str, True, lbl_col)
    app.screen.blit(lbl, (mx, my - 13))
    for b in range(nbeats):
        bx     = mx + b * (bw + 4)
        active = (app.playing or app.counting_down) and (b == app.metro_beat)
        c = C_ACCENT if (active and b == 0) else C_WHITE if active else C_DGRAY
        if not metro_on:
            c = (30, 30, 45) if not active else (50, 50, 70)
        pygame.draw.rect(app.screen, c, (bx, my, bw, 28), border_radius=5)
        if b == 0:
            border_col = C_ACCENT if metro_on else (60, 60, 80)
            pygame.draw.rect(app.screen, border_col, (bx, my, bw, 28), 2, border_radius=5)
        n = app.font_med.render(str(b + 1), True, (10, 10, 18) if active else C_GRAY)
        app.screen.blit(n, (bx + bw // 2 - n.get_width() // 2, my + 4))


def draw_pitch_panel(app) -> None:
    from ..audio import INPUT_AVAILABLE

    px, py, pw, ph = 220, LOWER_Y + 36, 634, 110
    pygame.draw.rect(app.screen, C_PANEL, (px, py, pw, ph), border_radius=10)

    with app.pitch_lock:
        det_hz   = app.detected_hz
        det_note = app.detected_note
        stb_hz   = app.stable_hz
        stb_note = app.stable_note
    cur = app.current_note()

    if INPUT_AVAILABLE and app.audio_devices:
        from ..audio import device_name_warning
        devs = app.audio_devices
        dev = devs[app.device_idx] if 0 <= app.device_idx < len(devs) else devs[0]
        dev_name = dev[1][:44]
        t = app.font_tiny.render(
            f"ENTRADA [{app.device_idx}]: {dev_name}  |  D=cambiar",
            True, C_GRAY)
        app.screen.blit(t, (px + 10, py + 6))
        warn = device_name_warning(dev[1])
        if warn:
            wt = app.font_tiny.render(f"({warn} ¿es la entrada del bajo?)", True, C_WAIT)
            app.screen.blit(wt, (px + 12 + t.get_width(), py + 6))
    else:
        t = app.font_tiny.render("pyaudio no disponible (entrada de audio)", True, C_RED)
        app.screen.blit(t, (px + 10, py + 6))

    # El motor avisa en cada chunk aunque haya silencio: si pasan >2.5 s sin
    # callbacks, el stream está roto (dispositivo inválido, p.open falló…).
    import time as _time
    no_signal = (getattr(app, "_pitch_engine", None) is not None
                 and _time.time() - (getattr(app, "_pitch_last_cb", 0.0) or 0.0) > 2.5)

    col = (C_OK  if app.note_match is True  else
           C_ERR if app.note_match is False else C_GRAY)
    big = app.font_big.render(stb_note, True, col)
    app.screen.blit(big, (px + 10, py + 20))
    if det_hz > 0 and det_note != stb_note:
        raw_t = app.font_tiny.render(f"crudo: {det_note}", True, C_DGRAY)
        app.screen.blit(raw_t, (px + 10, py + 52))

    if stb_hz > 0:
        hz_t = app.font_small.render(f"{stb_hz:.1f} Hz", True, C_GRAY)
        app.screen.blit(hz_t, (px + 10, py + 62))

    if cur:
        exp = app.font_small.render(
            f"Esperada: {cur['note_name']}  (tr.{cur['fret']} Cuerda {STRING_NAMES[cur['string']]})",
            True, C_WHITE)
        app.screen.blit(exp, (px + 10, py + 90))

    if no_signal:
        app.screen.blit(app.font_big.render("SIN SEÑAL", True, C_RED),
                        (px + 160, py + 24))
        ns_hint = app.font_tiny.render("revisa volumen o pulsa D", True, C_GRAY)
        app.screen.blit(ns_hint, (px + 162, py + 58))
    elif app.note_match is True:
        app.screen.blit(app.font_big.render("OK!", True, C_OK),
                        (px + 160, py + 24))
    elif app.note_match is False:
        app.screen.blit(app.font_big.render("Ajusta", True, C_ERR),
                        (px + 160, py + 24))

    if INPUT_AVAILABLE and cur and stb_hz > 0 and cur["hz"] > 0:
        ratio = stb_hz / cur["hz"]
        if ratio > 0:
            cents = 1200 * math.log2(ratio)
            while cents >  600: cents -= 1200
            while cents < -600: cents += 1200
            cents_c = max(-120, min(120, cents))
            bx, by2, bw2, bh = px + 160, py + 68, 450, 13
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

    # Una sola fila con lo esencial; el resto vive en la ayuda (F1)
    hints = [
        ("SPC", "Play"), ("R", "Reinicio"), ("←/→", "Compás"),
        ("↑/↓", "Tempo"), ("L", "Canciones"), ("W", "Alinear"),
        ("Y", "Acordes"), ("E", "Notas"), ("G", "Walking"),
        ("ESC", "Salir"), ("F1", "Ayuda"),
    ]
    x = 8
    row_y = BOTTOM_Y + 16
    for key, desc in hints:
        k = app.font_small.render(key, True, C_ACCENT)
        d = app.font_small.render(f" {desc}  ", True, C_GRAY)
        app.screen.blit(k, (x, row_y))
        x += k.get_width()
        app.screen.blit(d, (x, row_y))
        x += d.get_width()

    if app.mp3_path:
        engine = " [varispeed]" if app._use_vsp else " [fixed]"
        sfx    = " [MUTE]" if app.muted else ""
        col    = C_GREEN if not app.muted else C_GRAY
        mp3s   = os.path.basename(app.mp3_path)[:44] + sfx + engine
    else:
        col  = C_RED
        mp3s = "MP3 no encontrado"
    mp3_surf = app.font_small.render(mp3s, True, col)
    mp3_x    = W - mp3_surf.get_width() - 8
    app.screen.blit(mp3_surf, (mp3_x, BOTTOM_Y + 16))

    src_surf = app.font_tiny.render(
        f"MusicXML: {len(app.notes)} notas",
        True, C_GRAY if app.notes else C_RED)
    app.screen.blit(src_surf, (mp3_x - src_surf.get_width() - 14, BOTTOM_Y + 19))

    if getattr(app, '_config_msg_timer', 0) > 0:
        msg = app.font_med.render(app._config_msg, True, app._config_msg_col)
        app.screen.blit(msg, (W // 2 - msg.get_width() // 2, BOTTOM_Y + 14))
