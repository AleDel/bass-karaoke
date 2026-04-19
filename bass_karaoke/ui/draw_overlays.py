"""
Overlays de pantalla completa:
  - Afinador (draw_tuner)
  - Cuenta atrás (draw_countdown)
  - Menú de dispositivos (draw_device_menu)
  - Menú de método de pitch (draw_pitch_menu)
"""
import math
import pygame

from ..config import (
    W, H, STRING_COLORS, C_ACCENT, C_DGRAY, C_GRAY, C_WHITE,
    C_PANEL, C_BG, C_BLUE, C_OVERLAY,
    C_OK, C_ERR, C_GREEN, C_RED,
    PITCH_METHODS, MIN_HZ,
)


def draw_tuner(app) -> None:
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill((5, 5, 18, 235))
    app.screen.blit(ov, (0, 0))

    t = app.font_med.render("AFINADOR  —  T para cerrar", True, C_GRAY)
    app.screen.blit(t, (W // 2 - t.get_width() // 2, 30))

    with app.pitch_lock:
        det_hz   = app.detected_hz
        det_note = app.detected_note

    cents    = 0.0
    ref_note = "—"
    ref_hz   = 0.0
    in_tune  = False
    if det_hz > MIN_HZ:
        midi_f   = 12 * math.log2(det_hz / 440.0) + 69
        midi_r   = round(midi_f)
        cents    = (midi_f - midi_r) * 100
        ref_hz   = 440.0 * (2 ** ((midi_r - 69) / 12))
        names    = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
        ref_note = f"{names[midi_r % 12]}{midi_r // 12 - 1}"
        in_tune  = abs(cents) < 15

    col_note = C_GREEN if in_tune else C_ACCENT if det_hz > MIN_HZ else C_DGRAY
    big = pygame.font.SysFont("consolas", 130, bold=True).render(
        ref_note if det_hz > MIN_HZ else "—", True, col_note)
    app.screen.blit(big, (W // 2 - big.get_width() // 2, H // 2 - 130))

    if det_hz > MIN_HZ:
        hz_s = app.font_small.render(f"{det_hz:.2f} Hz", True, C_GRAY)
        app.screen.blit(hz_s, (W // 2 - hz_s.get_width() // 2, H // 2 + 20))

    bw, bh  = 600, 22
    bx      = W // 2 - bw // 2
    by      = H // 2 + 60
    pygame.draw.rect(app.screen, C_DGRAY, (bx, by, bw, bh), border_radius=5)
    green_half = int(bw / 2 * 15 / 100)
    pygame.draw.rect(app.screen, (20, 80, 30),
                     (bx + bw // 2 - green_half, by, green_half * 2, bh),
                     border_radius=3)
    pygame.draw.line(app.screen, C_WHITE,
                     (bx + bw // 2, by), (bx + bw // 2, by + bh), 2)

    if det_hz > MIN_HZ:
        c_clip   = max(-50, min(50, cents))
        needle_x = bx + bw // 2 + int(c_clip / 50 * (bw // 2))
        n_col    = C_GREEN if in_tune else C_ERR
        pygame.draw.rect(app.screen, n_col,
                         (needle_x - 4, by - 4, 8, bh + 8), border_radius=3)
        cents_s = app.font_med.render(f"{cents:+.1f} cents", True, n_col)
        app.screen.blit(cents_s, (W // 2 - cents_s.get_width() // 2, by + bh + 8))

    for label, rx in [("-50", bx + 4), ("0", bx + bw // 2 - 8), ("+50", bx + bw - 26)]:
        app.screen.blit(app.font_tiny.render(label, True, C_GRAY), (rx, by + bh + 2))

    ref_y = by + bh + 40
    app.screen.blit(
        app.font_small.render("Referencia cuerdas al aire:", True, C_GRAY),
        (W // 2 - 140, ref_y))
    open_notes = [(4, "E1", 41.20), (3, "A1", 55.00), (2, "D2", 73.42), (1, "G2", 98.00)]
    spacing    = 130
    start_x    = W // 2 - spacing * 3 // 2 - 30
    for i, (s, name, hz) in enumerate(open_notes):
        sx  = start_x + i * spacing
        sy  = ref_y + 22
        col = STRING_COLORS[s]
        pygame.draw.rect(app.screen, C_PANEL, (sx - 2, sy - 2, 100, 46), border_radius=6)
        pygame.draw.rect(app.screen, col,     (sx - 2, sy - 2, 100, 46), 2, border_radius=6)
        n_lbl = app.font_big.render(name, True, col)
        app.screen.blit(n_lbl, (sx + 50 - n_lbl.get_width() // 2, sy + 2))
        h_lbl = app.font_tiny.render(f"{hz:.2f} Hz", True, C_GRAY)
        app.screen.blit(h_lbl, (sx + 50 - h_lbl.get_width() // 2, sy + 32))


def draw_countdown(app) -> None:
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 140))
    app.screen.blit(ov, (0, 0))
    num = app.font_huge.render(str(app.countdown_beat), True, C_ACCENT)
    app.screen.blit(num, (W // 2 - num.get_width() // 2,
                           H // 2 - num.get_height() // 2 - 20))
    sub = app.font_med.render("preparado...", True, C_GRAY)
    app.screen.blit(sub, (W // 2 - sub.get_width() // 2,
                           H // 2 + num.get_height() // 2 - 10))


def draw_device_menu(app) -> None:
    mw, mh = 680, 360
    mx, my = W // 2 - mw // 2, H // 2 - mh // 2

    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill(C_OVERLAY)
    app.screen.blit(ov, (0, 0))

    pygame.draw.rect(app.screen, C_PANEL,  (mx, my, mw, mh), border_radius=12)
    pygame.draw.rect(app.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

    hdr = app.font_med.render("SELECCIONA DISPOSITIVO DE ENTRADA", True, C_ACCENT)
    app.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))
    pygame.draw.line(app.screen, C_DGRAY,
                     (mx + 10, my + 42), (mx + mw - 10, my + 42), 1)

    if not app.audio_devices:
        app.screen.blit(
            app.font_med.render("No se encontraron dispositivos", True, C_RED),
            (mx + 20, my + 80))
    else:
        row_h    = 28
        max_rows = (mh - 78) // row_h
        start    = max(0, app.device_menu_sel - max_rows + 1)
        for i, (_, name) in enumerate(app.audio_devices):
            if i < start: continue
            if i - start >= max_rows: break
            ry     = my + 50 + (i - start) * row_h
            is_sel = (i == app.device_menu_sel)
            is_cur = (i == app.device_idx)
            if is_sel:
                pygame.draw.rect(app.screen, C_DGRAY,
                                 (mx + 6, ry - 2, mw - 12, row_h - 2),
                                 border_radius=4)
            col = C_GREEN if is_cur else C_WHITE if is_sel else C_GRAY
            lbl = app.font_small.render(
                f"{'●' if is_cur else ' '} [{i}] {name[:56]}", True, col)
            app.screen.blit(lbl, (mx + 12, ry))

    hint = app.font_tiny.render(
        "Up/Dn navegar    ENTER confirmar    ESC / D  cerrar",
        True, C_GRAY)
    app.screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 22))


def draw_pitch_menu(app) -> None:
    LABELS = {
        "aubio":        "aubio YINfast  (CPU, sin GPU)",
        "crepe-tiny":   "CREPE tiny     (GPU recomendado)",
        "crepe-full":   "CREPE full     (GPU — más preciso)",
        "pesto":        "PESTO streaming  (PyTorch, GPU)",
        "pesto-onnx":   "PESTO ONNX     (CPU, sin PyTorch)",
        "basic-pitch":  "Basic Pitch    (Spotify, ONNX en Windows)",
    }
    mw, mh = 540, 260
    mx, my = W // 2 - mw // 2, H // 2 - mh // 2

    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill(C_OVERLAY)
    app.screen.blit(ov, (0, 0))

    pygame.draw.rect(app.screen, C_PANEL,  (mx, my, mw, mh), border_radius=12)
    pygame.draw.rect(app.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

    hdr = app.font_med.render("MÉTODO DE DETECCIÓN DE PITCH", True, C_ACCENT)
    app.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))
    pygame.draw.line(app.screen, C_DGRAY,
                     (mx + 10, my + 42), (mx + mw - 10, my + 42), 1)

    row_h = 32
    for i, m in enumerate(PITCH_METHODS):
        ry     = my + 50 + i * row_h
        is_sel = (i == app.pitch_menu_sel)
        is_cur = (m == app.pitch_method)
        if is_sel:
            pygame.draw.rect(app.screen, C_DGRAY,
                             (mx + 6, ry - 2, mw - 12, row_h - 2), border_radius=4)
        col = C_GREEN if is_cur else C_WHITE if is_sel else C_GRAY
        pre = "● " if is_cur else "  "
        lbl = app.font_small.render(f"{pre}{LABELS.get(m, m)}", True, col)
        app.screen.blit(lbl, (mx + 12, ry + 4))

    hint = app.font_tiny.render(
        "Up/Dn navegar    ENTER aplicar    ESC / P  cerrar",
        True, C_GRAY)
    app.screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 22))
