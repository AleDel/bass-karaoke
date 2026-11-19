"""
Dibuja la tarjeta de partitura: cabecera de estado, pentagrama y cursor.

La imagen de Verovio (o el pentagrama manual) se pinta sobre un pozo oscuro,
con los nombres de nota en una tira superior y una banda cian marcando el
instante actual.
"""
import math

import pygame

from ..config import STRING_COLORS
from . import theme as T
from .theme import ACCENT, TEXT, TEXT_DIM, TEXT_MUTED


def score_img_x(app, b16):
    """Posición x (en píxeles de la imagen de Verovio) de un start16.

    Usa las posiciones reales de las notas (_score_note_xs) e interpola
    entre ellas; si no hay datos, cae a un reparto lineal de la imagen.
    Es la única base válida para el scroll: mover la partitura en unidades
    lineales (px_of) la deja descolocada respecto a la música.
    """
    surf = app.view._score_surf
    xs   = app.view._score_note_xs
    if surf is None:
        return float(b16)
    if not xs:
        total  = getattr(app.view, "_score_total16", None) or 1
        margin = surf.get_width() * 0.04
        return margin + max(0, b16) / total * (surf.get_width() - margin)
    if b16 <= xs[0][0]:
        if len(xs) > 1 and xs[1][0] > xs[0][0]:
            slope = (xs[1][1] - xs[0][1]) / (xs[1][0] - xs[0][0])
            return xs[0][1] - (xs[0][0] - b16) * slope
        return xs[0][1]
    if b16 >= xs[-1][0]:
        return xs[-1][1]
    for i in range(len(xs) - 1):
        b0, x0 = xs[i]
        b1, x1 = xs[i + 1]
        if b0 <= b16 <= b1:
            t = (b16 - b0) / (b1 - b0) if b1 > b0 else 0.0
            return x0 + t * (x1 - x0)
    return xs[-1][1]


def _device_label(app) -> str:
    try:
        from ..audio import INPUT_AVAILABLE
        if not INPUT_AVAILABLE or not app.audio_devices:
            return "sin entrada de audio"
        devs = app.audio_devices
        dev = devs[app.device_idx] if 0 <= app.device_idx < len(devs) else devs[0]
        return f"ENTRADA [{app.device_idx}]: {dev[1]}"
    except Exception:
        return "sin entrada de audio"


def draw_score(app) -> None:
    L = app.layout
    card = L.score
    T.card(app.screen, card, L.radius)

    # ── Cabecera de la tarjeta ────────────────────────────────────────────
    f_head = T.font(L.fs(11))
    head = L.score_head
    dev = _device_label(app)
    T.text(app.screen, f_head, T.fit(f_head, dev, head.w * 0.62),
           TEXT_MUTED, (head.x, head.centery), "midleft")

    if app.notes:
        src = f"MusicXML: {len(app.notes)} notas"
    else:
        src = "MusicXML: sin notas"
    if app.mp3_path:
        src += "  ·  MP3 encontrado"
        src_col = T.GREEN
    else:
        src += "  ·  MP3 no encontrado"
        src_col = T.RED
    T.text(app.screen, f_head, src, src_col,
           (head.right, head.centery), "midright")

    # Separador horizontal fino bajo la cabecera
    pygame.draw.line(app.screen, (48, 50, 53),
                     (card.x + L.pad, head.bottom + int(4 * L.s)),
                     (card.right - L.pad, head.bottom + int(4 * L.s)), 1)

    # ── Pentagrama ────────────────────────────────────────────────────────
    staff = L.staff
    T.inset(app.screen, staff, radius=max(6, int(8 * L.s)),
            color=(17, 19, 23))
    NAME_H = max(10, int(12 * L.s))
    CURSOR_X = L.cursor_x

    if app.view._score_surf is not None:
        app.view._score_scroll_x = score_img_x(app, app.beat_time)
        blit_x = CURSOR_X - int(app.view._score_scroll_x)

        clip = pygame.Rect(staff.x, staff.y, staff.w, staff.h)
        prev_clip = app.screen.get_clip()
        app.screen.set_clip(clip)
        app.screen.blit(app.view._score_surf,
                        (blit_x, staff.y + NAME_H + 2))

        # Nombres de nota sobre el pentagrama
        last_nx = -999
        MIN_GAP = max(22, int(26 * L.s))
        LABEL_X0 = staff.x + int(8 * L.s)
        f_note = T.font(L.fs(10))
        for note in app.notes:
            img_x = score_img_x(app, note["start16"])
            nx = blit_x + int(img_x)
            if nx < LABEL_X0 or nx > staff.right - 2:
                continue
            if nx - last_nx < MIN_GAP:
                continue
            last_nx = nx
            is_past = note["start16"] < app.beat_time - 1
            is_cur = abs(note["start16"] - app.beat_time) <= 2
            if is_cur:
                col = ACCENT
            elif is_past:
                col = (86, 92, 102)
            else:
                col = TEXT_DIM
            T.text(app.screen, f_note, note.get("note_name", "?"), col,
                   (nx, staff.y + NAME_H // 2 + 1), "center")
        app.screen.set_clip(prev_clip)

        # Banda del cursor
        band_w = max(14, int(26 * L.s))
        band = pygame.Surface((band_w, staff.h - NAME_H - 6), pygame.SRCALPHA)
        pygame.draw.rect(band, (*ACCENT, 30), band.get_rect(),
                         border_radius=max(3, int(6 * L.s)))
        app.screen.blit(band, (CURSOR_X - band_w // 2,
                               staff.y + NAME_H + 2))
        pygame.draw.line(app.screen, ACCENT,
                         (CURSOR_X, staff.y + NAME_H + 2),
                         (CURSOR_X, staff.bottom - 5),
                         max(1, int(2 * L.s)))
        # Triángulo inferior
        tw = max(3, int(5 * L.s))
        pygame.draw.polygon(app.screen, ACCENT, [
            (CURSOR_X - tw, staff.bottom - 5),
            (CURSOR_X + tw, staff.bottom - 5),
            (CURSOR_X, staff.bottom - 5 - tw * 2)])
    else:
        _draw_score_manual(app, staff, CURSOR_X)

    pygame.draw.rect(app.screen, (44, 46, 49), staff, 1,
                     border_radius=max(6, int(8 * L.s)))


def _draw_score_manual(app, rect, CURSOR_X):
    """Pentagrama de reserva (sin Verovio/music21) – estilo referencia."""
    L = app.layout
    LINE_SEP = max(7, int(rect.h * 0.078))
    LINES = 5
    staff_h = (LINES - 1) * LINE_SEP
    # Centrar el pentagrama en el rect (el bajo tiene notas que caen debajo,
    # por lo que subimos un poco para dejar espacio de líneas ledger)
    staff_y0 = rect.y + max(10, int((rect.h - staff_h) * 0.35))
    CLEF_X = rect.x + 10

    prev_clip = app.screen.get_clip()
    app.screen.set_clip(rect)

    # Clave de Fa 𝄢
    clef_font = T.font(max(22, int(LINE_SEP * 4.6)))
    clef_surf = clef_font.render("𝄢", True, (180, 186, 198))
    app.screen.blit(clef_surf, (CLEF_X, staff_y0 - LINE_SEP))

    # Indicador de compás 4/4
    f_time = T.font(max(12, int(LINE_SEP * 1.75)), bold=True)
    time_x = CLEF_X + clef_surf.get_width() + max(2, int(4 * L.s))
    t4_top = f_time.render("4", True, (190, 196, 208))
    t4_bot = f_time.render("4", True, (190, 196, 208))
    app.screen.blit(t4_top, (time_x, staff_y0 + int(LINE_SEP * 0.05)))
    app.screen.blit(t4_bot, (time_x, staff_y0 + int(LINE_SEP * 1.95)))

    # Líneas del pentagrama
    for li in range(LINES):
        pygame.draw.line(app.screen, (110, 116, 128),
                         (rect.x + 2, staff_y0 + li * LINE_SEP),
                         (rect.right - 2, staff_y0 + li * LINE_SEP), 1)

    # Para el bajo: La referencia de altura es B2 en la 4ª línea (Clave de Fa)
    # B2 = octava 2, diatónico 2*7+6 = 20 → lo ponemos en staff_y0 + LINE_SEP (4ª línea)
    STEP_IDX = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
    REF_DIATONIC = 2 * 7 + 6   # B2
    REF_LINE_Y = staff_y0 + LINE_SEP  # 4ª línea del pentagrama de Fa

    def note_y(step, octave):
        d = octave * 7 + STEP_IDX.get(step, 0)
        raw = REF_LINE_Y - (d - REF_DIATONIC) * (LINE_SEP / 2)
        # Permitir hasta 3 líneas ledger extra abajo y arriba
        return max(rect.y + 2, min(rect.bottom - 4, raw))

    vx = int(app.view.viewport_x)

    # Barras de compás
    prev_meas = -1
    for note in app.notes:
        if note["measure_num"] != prev_meas:
            prev_meas = note["measure_num"]
            mx2 = app.px_of(note["start16"]) - vx + CURSOR_X
            if rect.x + 20 < mx2 < rect.right - 2:
                pygame.draw.line(app.screen, (70, 76, 88),
                                 (mx2 - 2, staff_y0),
                                 (mx2 - 2, staff_y0 + staff_h), 1)

    # Notas
    for i, note in enumerate(app.notes):
        nx2 = app.px_of(note["start16"]) - vx + CURSOR_X
        if nx2 < rect.x - 24 or nx2 > rect.right + 24:
            continue
        is_cur = (i == app.note_idx and app.beat_time >= note["start16"])
        is_past = (i < app.note_idx)
        ny_pos = note_y(note.get("step", "C"), note.get("octave", 3))
        dur_type = note.get("dur_type", "quarter")

        if is_cur:
            col = (T.GREEN if app.note_match is True else
                   T.RED if app.note_match is False else ACCENT)
        else:
            col = (80, 86, 98) if is_past else (220, 226, 236)

        hw = max(5, int(LINE_SEP * 0.75))
        hh = max(4, int(LINE_SEP * 0.60))
        head_r = pygame.Rect(nx2 - hw // 2, int(ny_pos) - hh // 2, hw, hh)

        # Líneas ledger si la nota está fuera del pentagrama
        for li in range(LINES):
            ly = staff_y0 + li * LINE_SEP
        # Arriba: por encima del pentagrama
        y_above_staff = staff_y0
        y_below_staff = staff_y0 + staff_h
        if ny_pos < y_above_staff - hh // 2:
            for ly in range(int(y_above_staff - LINE_SEP), int(ny_pos) - hh // 2, -LINE_SEP):
                pygame.draw.line(app.screen, (100, 106, 118),
                                 (nx2 - hw - 2, ly), (nx2 + hw + 2, ly), 1)
        elif ny_pos > y_below_staff + hh // 2:
            for ly in range(int(y_below_staff + LINE_SEP), int(ny_pos) + hh // 2 + LINE_SEP, LINE_SEP):
                pygame.draw.line(app.screen, (100, 106, 118),
                                 (nx2 - hw - 2, ly), (nx2 + hw + 2, ly), 1)

        if dur_type in ("half", "whole"):
            pygame.draw.ellipse(app.screen, col, head_r, 2)
        else:
            pygame.draw.ellipse(app.screen, col, head_r)

        # Plica: sube si la nota está en la mitad baja del pentagrama, baja si está arriba
        staff_mid = staff_y0 + staff_h / 2
        if dur_type != "whole":
            sl = LINE_SEP * 3
            if ny_pos >= staff_mid:  # nota baja → plica hacia arriba
                pygame.draw.line(app.screen, col,
                                 (nx2 + hw // 2 - 1, int(ny_pos) - hh // 2),
                                 (nx2 + hw // 2 - 1, int(ny_pos) - hh // 2 - sl), 1)
            else:  # nota alta → plica hacia abajo
                pygame.draw.line(app.screen, col,
                                 (nx2 - hw // 2 + 1, int(ny_pos) + hh // 2),
                                 (nx2 - hw // 2 + 1, int(ny_pos) + hh // 2 + sl), 1)

    # Cursor cian vertical
    pygame.draw.line(app.screen, ACCENT, (CURSOR_X, rect.y + 2), (CURSOR_X, rect.bottom - 2), 1)
    # Halo semitransparente en el cursor
    band_w = max(10, int(20 * L.s))
    band = pygame.Surface((band_w, rect.h - 4), pygame.SRCALPHA)
    pygame.draw.rect(band, (*ACCENT, 22), band.get_rect(), border_radius=3)
    app.screen.blit(band, (CURSOR_X - band_w // 2, rect.y + 2))

    app.screen.set_clip(prev_clip)
