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
    C_ACCENT,
    C_BLUE,
    C_DGRAY,
    C_ERR,
    C_GRAY,
    C_GREEN,
    C_OK,
    C_OVERLAY,
    C_PANEL,
    C_RED,
    C_WAIT,
    C_WHITE,
    MIN_HZ,
    PITCH_METHODS,
    STRING_COLORS,
    H,
    W,
)


def _fit_text(font, text, max_w):
    """Recorta un texto a max_w px añadiendo elipsis."""
    if font.size(text)[0] <= max_w:
        return text
    while text and font.size(text + "…")[0] > max_w:
        text = text[:-1]
    return text + "…"


def draw_tuner(app) -> None:
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill((5, 5, 18, 235))
    app.screen.blit(ov, (0, 0))

    t = app.font_med.render("AFINADOR  —  T para cerrar", True, C_GRAY)
    app.screen.blit(t, (W // 2 - t.get_width() // 2, 30))

    with app.pitch_lock:
        det_hz = app.detected_hz

    cents    = 0.0
    ref_note = "—"
    in_tune  = False
    if det_hz > MIN_HZ:
        midi_f   = 12 * math.log2(det_hz / 440.0) + 69
        midi_r   = round(midi_f)
        cents    = (midi_f - midi_r) * 100
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
        start    = max(0, app.view.device_menu_sel - max_rows + 1)
        from ..audio import device_name_warning
        for i, (_, name) in enumerate(app.audio_devices):
            if i < start: continue
            if i - start >= max_rows: break
            ry     = my + 50 + (i - start) * row_h
            is_sel = (i == app.view.device_menu_sel)
            is_cur = (i == app.device_idx)
            if is_sel:
                pygame.draw.rect(app.screen, C_DGRAY,
                                 (mx + 6, ry - 2, mw - 12, row_h - 2),
                                 border_radius=4)
            col = C_GREEN if is_cur else C_WHITE if is_sel else C_GRAY
            lbl = app.font_small.render(
                f"{'●' if is_cur else ' '} [{i}] {name[:48]}", True, col)
            app.screen.blit(lbl, (mx + 12, ry))
            if device_name_warning(name):
                tag = app.font_tiny.render(" ¿salida?", True, C_WAIT)
                app.screen.blit(tag, (mx + 14 + lbl.get_width(), ry + 4))

    hint = app.font_tiny.render(
        "Up/Dn navegar    ENTER confirmar    ESC / D  cerrar",
        True, C_GRAY)
    app.screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 22))


def draw_pitch_menu(app) -> None:
    LABELS = {
        "mpm":          "MPM McLeod   (CPU, afinador — ideal graves)",
        "aubio":        "aubio YIN    (CPU, sin GPU)",
        "crepe-tiny":   "CREPE tiny     (GPU recomendado)",
        "crepe-full":   "CREPE full     (GPU — más preciso)",
        "pesto":        "PESTO streaming  (PyTorch, GPU)",
        "pesto-onnx":   "PESTO ONNX     (CPU, sin PyTorch)",
        "basic-pitch":  "Basic Pitch    (Spotify, ONNX en Windows)",
    }
    mw = 540
    mh = 50 + len(PITCH_METHODS) * 32 + 34
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
        is_sel = (i == app.view.pitch_menu_sel)
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


def draw_feature_menu(app) -> None:
    from .. import features

    mw, mh = 1040, 560
    mx, my = W // 2 - mw // 2, H // 2 - mh // 2

    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill(C_OVERLAY)
    app.screen.blit(ov, (0, 0))

    pygame.draw.rect(app.screen, C_PANEL,  (mx, my, mw, mh), border_radius=12)
    pygame.draw.rect(app.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

    hdr = app.font_med.render("FUNCIONALIDADES OPCIONALES", True, C_ACCENT)
    app.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))
    pygame.draw.line(app.screen, C_DGRAY,
                     (mx + 10, my + 42), (mx + mw - 10, my + 42), 1)

    feats    = features.FEATURES
    st       = features.status()
    row_h    = 34
    top_y    = my + 50
    max_rows = (mh - 215) // row_h
    start    = max(0, app.view.feature_menu_sel - max_rows + 1)

    for i in range(start, start + max_rows):
        if i >= len(feats):
            break
        f  = feats[i]
        ry = top_y + (i - start) * row_h
        is_sel = (i == app.view.feature_menu_sel)
        if is_sel:
            pygame.draw.rect(app.screen, C_DGRAY,
                             (mx + 6, ry - 2, mw - 12, row_h - 2),
                             border_radius=4)

        inst = st.get(f["id"], False)
        if f["id"] in app.feature_busy:
            badge, bcol = ("quitando…" if inst else "instalando…", C_WAIT)
        elif inst:
            sflag = features.session_flag(f["id"])
            if sflag is False:
                badge, bcol = ("instalado · reinicia", C_WAIT)
            else:
                badge, bcol = ("OK", C_OK)
        else:
            badge, bcol = ("no instalado", C_GRAY)

        name_col = C_WHITE if is_sel else C_GRAY
        lbl = app.font_small.render(
            _fit_text(app.font_small, f["name"], 400), True, name_col)
        app.screen.blit(lbl, (mx + 12, ry + 4))

        size = app.font_tiny.render(
            _fit_text(app.font_tiny, f["size"], 188), True, C_GRAY)
        app.screen.blit(size, (mx + 420, ry + 5))

        needs = app.font_tiny.render(
            _fit_text(app.font_tiny, f["needs"], 230), True, C_GRAY)
        app.screen.blit(needs, (mx + 614, ry + 5))

        b = app.font_small.render(badge, True, bcol)
        app.screen.blit(b, (mx + mw - b.get_width() - 12, ry + 4))

    # ── Detalle de la funcionalidad seleccionada ─────────────────────
    sel    = feats[app.view.feature_menu_sel]
    dy     = top_y + max_rows * row_h + 12
    title  = app.font_small.render(f"> {sel['name']}", True, C_ACCENT)
    app.screen.blit(title, (mx + 12, dy))
    dy += 20

    words = sel["desc"].split()
    line, yy = [], dy
    for w in words:
        line.append(w)
        if app.font_tiny.size(" ".join(line))[0] > mw - 32:
            line.pop()
            app.screen.blit(app.font_tiny.render(" ".join(line), True, C_WHITE),
                            (mx + 14, yy))
            line, yy = [w], yy + 16
    if line:
        app.screen.blit(app.font_tiny.render(" ".join(line), True, C_WHITE),
                        (mx + 14, yy))
    yy += 20

    if sel["requires"]:
        reqs = [b["name"].split(" —")[0] for b in feats
                if b["id"] in sel["requires"]]
        req = app.font_tiny.render("Requiere: " + ", ".join(reqs), True, C_WAIT)
        app.screen.blit(req, (mx + 12, yy))
        yy += 18

    if sel["id"] in app.feature_msg:
        ok, msg = app.feature_msg[sel["id"]]
        mcol = C_OK if ok else C_ERR
        ms = app.font_tiny.render(msg[:90], True, mcol)
        app.screen.blit(ms, (mx + 12, yy))
        yy += 18

    if app.feature_log:
        for j, line in enumerate(app.feature_log):
            app.screen.blit(app.font_tiny.render(line[:110], True, C_GRAY),
                            (mx + 12, yy + j * 14))

    hint = app.font_tiny.render(
        "Up/Dn navegar    ENTER = instalar / quitar    I / ESC = cerrar",
        True, C_GRAY)
    app.screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 22))


def draw_song_menu(app) -> None:
    mw, mh = 640, 420
    mx, my = W // 2 - mw // 2, H // 2 - mh // 2

    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill(C_OVERLAY)
    app.screen.blit(ov, (0, 0))

    pygame.draw.rect(app.screen, C_PANEL,  (mx, my, mw, mh), border_radius=12)
    pygame.draw.rect(app.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

    hdr = app.font_med.render("SELECCIONA CANCIÓN", True, C_ACCENT)
    app.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))
    pygame.draw.line(app.screen, C_DGRAY,
                     (mx + 10, my + 42), (mx + mw - 10, my + 42), 1)

    if not app.songs:
        app.screen.blit(
            app.font_med.render(
                "No se encontraron canciones en songs/ (se necesita .musicxml o audio)",
                True, C_RED),
            (mx + 20, my + 80))
    else:
        row_h    = 30
        max_rows = (mh - 78) // row_h
        start    = max(0, app.view.song_menu_sel - max_rows + 1)
        for i, s in enumerate(app.songs):
            if i < start: continue
            if i - start >= max_rows: break
            ry     = my + 50 + (i - start) * row_h
            is_sel = (i == app.view.song_menu_sel)
            is_cur = (i == app.song_idx)
            if is_sel:
                pygame.draw.rect(app.screen, C_DGRAY,
                                 (mx + 6, ry - 2, mw - 12, row_h - 2),
                                 border_radius=4)
            col  = C_GREEN if is_cur else C_WHITE if is_sel else C_GRAY
            has  = "●" if s.get("audio") else "○"
            txt  = f"{has} {s['name']}"
            if s.get("audio_only"):
                txt += "   (sin partitura · F7)"
            elif not s.get("audio"):
                txt += "   (sin audio)"
            lbl = app.font_small.render(txt, True, col)
            app.screen.blit(lbl, (mx + 12, ry + 4))

    hint = app.font_tiny.render(
        "Up/Dn navegar    ENTER cargar    ESC / L  cerrar",
        True, C_GRAY)
    app.screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 22))


def draw_help(app) -> None:
    """Overlay con todos los atajos, agrupados. F1 o ESC para cerrar."""
    groups = [
        ("Transporte", [
            ("SPACE", "Play / pausa (con countdown)"),
            ("R", "Reiniciar canción"),
            ("← / →", "Compás anterior / siguiente"),
            ("Arrastrar", "Seek en el tab"),
        ]),
        ("Tempo y offset", [
            ("↑ / ↓", "Tempo ±5 BPM (estira el MP3 con varispeed)"),
            ("  , / .", "Offset MP3 ±0.05 s  (Shift ±0.5 s, Ctrl ±5 s)"),
            ("  [ / ]", "Inicio de canción ±0.05 s (compás 1)"),
            ("W", "Editor de alineación (waveform)"),
            ("F5 / F6", "Guardar / cargar config  (Ctrl+S = acordes u offset)"),
        ]),
        ("Sonido", [
            ("M", "Silenciar MP3"),
            ("N", "Metrónomo on/off"),
            ("D", "Dispositivo de entrada"),
            ("P", "Método de pitch"),
            ("T", "Afinador"),
        ]),
        ("Vista", [
            ("L", "Selector de canciones"),
            ("F7", "Generar partitura desde el audio (si falta)"),
            ("S", "Partitura Verovio ↔ Music21"),
            ("B", "Tempo en BPM ↔ figura"),
            ("H", "Mapa del mástil"),
            ("C", "Countdown on/off"),
            ("J", "Acordes + letra (karaoke)"),
            ("Y", "Editor de acordes (por compás)"),
            ("Clic barra", "Seleccionar compás (tira J)"),
            ("Enter / Supr", "Editar / quitar el acorde del compás"),
            ("Clic mástil/piano", "Oír y ver la nota (aprender notas)"),
        ]),
        ("Entrenamiento", [
            ("E", "Encuentra la nota (oído + mástil)"),
            ("G", "Walking Lab (moldes Mayor/menor)"),
            ("K", "Corridos tumbados (bajeo 3/4)"),
            ("O", "Oído: escucha y repite"),
            ("X", "Técnica y dedos"),
            ("A", "Arpegios con tónica móvil"),
            ("V", "Escalas por cajas"),
        ]),
        ("Sistema", [
            ("I", "Funcionalidades opcionales"),
            ("F1 / ESC", "Cerrar esta ayuda"),
        ]),
    ]

    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill(C_OVERLAY)
    app.screen.blit(ov, (0, 0))

    max_kw = 0
    max_dw = 0
    for _t, items in groups:
        for k, d in items:
            max_kw = max(max_kw, app.font_small.size(k)[0])
            max_dw = max(max_dw, app.font_small.size(d)[0])

    row_h   = 22
    n_rows  = sum(1 + len(g[1]) for g in groups)
    max_h   = H - 20
    if 90 + n_rows * row_h > max_h:
        row_h = max(14, (max_h - 90) // max(1, n_rows))
    mw      = max(620, 36 + max_kw + 14 + max_dw + 16)
    mh      = 90 + n_rows * row_h
    mx, my  = W // 2 - mw // 2, H // 2 - mh // 2

    pygame.draw.rect(app.screen, C_PANEL,  (mx, my, mw, mh), border_radius=12)
    pygame.draw.rect(app.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

    hdr = app.font_med.render("ATAJOS  —  F1 / ESC para cerrar", True, C_ACCENT)
    app.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))
    pygame.draw.line(app.screen, C_DGRAY,
                     (mx + 10, my + 44), (mx + mw - 10, my + 44), 1)

    y = my + 54
    max_kw = 0
    for _t, items in groups:
        for k, _d in items:
            max_kw = max(max_kw, app.font_small.size(k)[0])
    desc_x = mx + 36 + max_kw + 14
    for title, items in groups:
        app.screen.blit(app.font_small.render(title, True, C_BLUE),
                        (mx + 16, y))
        y += row_h
        for key, desc in items:
            app.screen.blit(app.font_small.render(key, True, C_ACCENT),
                            (mx + 36, y))
            app.screen.blit(app.font_small.render(desc, True, C_WHITE),
                            (desc_x, y))
            y += row_h
