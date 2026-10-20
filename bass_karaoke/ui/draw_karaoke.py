"""
Tira karaoke estilo Chordify (J): timeline horizontal de acordes con
scroll sincronizado a la música, pero dividida por COMPASES reales.

- Cada compás es una celda (misma rejilla que la partitura: measure_starts
  + grid_phase16), así que el acorde se marca sobre compases, no sobre
  "bloques" de duración arbitraria. La celda muestra el acorde VIGENTE
  (el del último cambio en o antes del compás) para que se vea qué
  compases cubre cada acorde.
- Un cambio de acorde se marca con una línea gruesa y el nombre en color
  de acento. Si hay un cambio "fuera de compás" (evento a mitad de
  compás, típico del heurístico), se dibuja una marca naranja para que se
  pueda corregir con el editor de compás.
- La edición es por compás: clic = seleccionar, Enter = editar, Supr =
  quitar el cambio. Todo se guarda en <base>.chords.json con Ctrl+S.
"""

import math

import pygame

from ..chords import is_rest_chord, lyric_at, snap_events_to_grid
from ..config import (
    C_ACCENT,
    C_BG2,
    C_DGRAY,
    C_GRAY,
    C_GREEN,
    C_PANEL,
    C_RED,
    C_WHITE,
    KARAOKE_H,
    KARAOKE_Y,
    W,
)

CURSOR_X = W // 3
_BEAT16 = 4          # una negra = 4 dieciseisavos
_TEAL = (70, 180, 175)  # progreso dentro del compás vigente (como Chordify)
_OFFGRID = (235, 160, 60)  # cambio fuera de compás (a corregir)


def _bass_root(chord_name: str) -> str:
    """Tónica para el bajo (raíz del acorde, sin la 'm' de menor)."""
    n = (chord_name or "").strip()
    if n.endswith("m") and len(n) > 1:
        n = n[:-1]
    return n or "—"


def _is_rest(name: str) -> bool:
    return is_rest_chord(name)


def _vis16(app, raw16: float) -> float:
    """start16 de partitura → start16 visual (fase global de la rejilla)."""
    raw16 = float(raw16)
    return raw16 + (float(app.grid_phase16()) if raw16 > 1e-9 else 0.0)


def snapped_chord_events(app):
    """Eventos de acorde alineados a la rejilla de compases (base partitura).

    El .chords.json puede traer tiempos desfasados unas décimas (p. ej.
    guardados con el offset del MP3); alinearlos evita que un cambio de
    acorde se quede "invisible" en el compás donde suena.
    """
    evs = [(float(s), str(n)) for s, n in
           (getattr(app, "chord_events", []) or [])]
    ms = list(getattr(app, "measure_starts", []) or [])
    if not evs or not ms:
        return [list(e) for e in evs]
    try:
        grid = [float(app._song_seconds(float(s16))) for _num, s16 in ms]
    except Exception:
        return evs
    return snap_events_to_grid(evs, grid)


def chord_measure_cells(app, evs=None):
    """Celdas por compás.

    Devuelve [(i, num, raw0, v0, v1, sec0, sec1, name, is_change)] donde
    name = acorde vigente al inicio del compás, is_change = hay un evento
    de acorde exactamente en el inicio del compás.
    """
    ms = list(getattr(app, "measure_starts", []) or [])
    bar16 = max(4, int(getattr(app, "beats_per_bar", 4) or 4) * 4)
    if not ms:
        total = float(getattr(app.view, "_score_total16", 0) or 0)
        if total <= 0:
            return []
        n = int(math.ceil(total / bar16))
        ms = [[i + 1, i * bar16] for i in range(n)]
    evs = list(evs) if evs is not None else snapped_chord_events(app)

    def eff(sec):
        name = ""
        for s, n in evs:
            if float(s) <= sec + 1e-6:
                name = str(n)
            else:
                break
        return name

    def has_change(sec):
        return any(abs(float(s) - sec) <= 0.05 for s, _n in evs)

    raws = [float(s16) for _num, s16 in ms]
    cells = []
    for i, (num, s16) in enumerate(ms):
        raw0 = float(s16)
        nxt = raws[i + 1] if i + 1 < len(raws) else raw0 + bar16
        v0 = _vis16(app, raw0)
        v1 = _vis16(app, nxt)
        try:
            sec0 = float(app._song_seconds(raw0))
            sec1 = float(app._song_seconds(nxt))
        except Exception:
            sec0 = sec1 = 0.0
        cells.append((i, int(num), raw0, v0, v1, sec0, sec1,
                      eff(sec0), has_change(sec0)))
    return cells


def chord_timeline_rect():
    """(yt0, th) de la zona de acordes de la tira (coords de pantalla)."""
    info_h = 20
    yt0 = KARAOKE_Y + 2
    th = max(20, KARAOKE_H - info_h - 4)
    return yt0, th


def chord_measure_hit_test(app, pos):
    """Compás bajo el ratón en la tira.

    Devuelve (cell_idx, cell) o None si el clic cae fuera de la tira.
    """
    x, y = int(pos[0]), int(pos[1])
    yt0, th = chord_timeline_rect()
    if not (0 <= x <= W and yt0 <= y <= yt0 + th):
        return None
    vx = float(getattr(app.view, "viewport_x", 0.0))
    cells = chord_measure_cells(app)
    for i, cell in enumerate(cells):
        v0, v1 = cell[3], cell[4]
        x0 = int(app.px_of(v0) - vx + CURSOR_X)
        x1 = int(app.px_of(v1) - vx + CURSOR_X)
        if x0 <= x < x1:
            return i, cell
    return None


def draw_chord_editor_popup(app) -> None:
    """Desplegable de acordes mientras se teclea uno en la barra.

    Se dibuja aparte (después de las tiras) porque abre justo debajo de la
    barra, encima del waveform; los rects vienen de la app para poder
    clicar en ellos.
    """
    if not bool(getattr(app, "chord_bar_typing", False)):
        return
    layout = app.chord_bar_sugg_layout()
    if not layout:
        return
    sel = int(getattr(app, "chord_bar_sugg_idx", -1))
    for i, (name, rect) in enumerate(layout):
        is_sel = (i == sel)
        pygame.draw.rect(app.screen, (26, 26, 44) if is_sel else (14, 14, 26),
                         rect, border_radius=4)
        pygame.draw.rect(app.screen, C_ACCENT if is_sel else C_DGRAY,
                         rect, 1, border_radius=4)
        txt = app.font_small.render(name, True, C_ACCENT if is_sel else C_GRAY)
        app.screen.blit(txt, (rect.x + 8,
                              rect.y + rect.h // 2 - txt.get_height() // 2))


def draw_karaoke_strip(app) -> None:
    y0, h = KARAOKE_Y, KARAOKE_H
    pygame.draw.rect(app.screen, C_BG2, (0, y0, W, h))
    pygame.draw.line(app.screen, C_DGRAY, (0, y0 + h - 1), (W, y0 + h - 1), 1)

    try:
        sec = float(app._song_seconds(app.beat_time))
    except Exception:
        sec = 0.0

    evs   = snapped_chord_events(app)
    cells = chord_measure_cells(app, evs)
    vx = float(getattr(app.view, "viewport_x", 0.0))

    info_h = 20
    yt0, th = chord_timeline_rect()

    def _x_of(s16):
        return int(app.px_of(s16) - vx + CURSOR_X)

    pygame.draw.rect(app.screen, (13, 13, 24), (0, yt0, W, th))
    clip = pygame.Rect(0, yt0, W, th)
    app.screen.set_clip(clip)

    sel     = getattr(app, "chord_bar_sel_measure", None)
    typing  = bool(getattr(app, "chord_bar_typing", False))
    buf     = str(getattr(app, "chord_bar_buf", "") or "")

    try:
        s16_now = _vis16(app, float(app._song_seconds_inverse(sec)))
    except Exception:
        s16_now = 0.0
    cur = -1
    for i, cell in enumerate(cells):
        if cell[3] <= s16_now < cell[4]:
            cur = i
            break
    else:
        if cells and s16_now >= cells[-1][4]:
            cur = len(cells) - 1

    if cells:
        for cell in cells:
            (i, num, raw0, v0, v1, sec0, sec1, name, is_change) = cell
            x0 = _x_of(v0)
            x1 = _x_of(v1)
            if x1 < 0 or x0 > W:
                continue
            x0c = max(0, x0)
            x1c = min(W, x1)
            is_cur = (i == cur)
            is_past = (i < cur)
            is_sel = (i == sel and sel is not None)
            rest = _is_rest(name)

            if is_sel:
                fill = (46, 40, 78)
            elif is_cur:
                fill = (62, 46, 10)
            elif is_past:
                fill = (14, 14, 26)
            else:
                fill = C_PANEL
            if x1c > x0c:
                pygame.draw.rect(app.screen, fill, (x0c, yt0, x1c - x0c, th))

            # Línea de compás (acento si hay cambio de acorde; el hueco va liso)
            if 0 <= x0 <= W:
                if is_change and not rest:
                    pygame.draw.line(app.screen, C_ACCENT,
                                     (x0, yt0), (x0, yt0 + th), 2)
                else:
                    pygame.draw.line(app.screen, (70, 70, 95),
                                     (x0, yt0 + 2), (x0, yt0 + th - 2), 1)

            # Número de compás (esquina superior izquierda)
            if x0c + 24 <= x1c:
                nt = app.font_tiny.render(
                    str(num), True,
                    C_ACCENT if (is_change and not rest) else C_DGRAY)
                app.screen.blit(nt, (x0c + 3, yt0 + 1))

            # Cambios fuera de compás (eventos a mitad de este compás)
            for s_ev, _n in evs:
                s_ev = float(s_ev)
                if sec0 + 0.05 < s_ev < sec1 - 0.05:
                    try:
                        raw_ev = float(app._song_seconds_inverse(s_ev))
                    except Exception:
                        continue
                    xo = _x_of(_vis16(app, raw_ev))
                    if x0c <= xo <= x1c:
                        pygame.draw.line(app.screen, _OFFGRID,
                                         (xo, yt0 + th // 3),
                                         (xo, yt0 + th - 2), 2)

            # Etiqueta: el acorde vigente (o el buffer si se está editando)
            if is_sel and typing:
                label = buf + "|"
                font = app.font_med
                col = C_ACCENT
            else:
                label = "—" if rest else (name or "—")
                font = app.font_med if (is_cur and not rest) else app.font_small
                col = (C_GRAY if rest else
                       C_ACCENT if is_change or is_cur else
                       (110, 110, 135) if is_past else C_WHITE)
            txt = font.render(label, True, col)
            if (is_sel or is_cur or txt.get_width() + 12 <= (x1 - x0)):
                if x0 + 6 < W and x0 + 6 + txt.get_width() > 0:
                    app.screen.blit(txt, (x0 + 6,
                                          yt0 + th // 2 - txt.get_height() // 2))

            # Selección / edición
            if is_sel:
                pygame.draw.rect(app.screen, C_ACCENT if typing else (150, 140, 220),
                                 (x0c, yt0, x1c - x0c, th), 2 if typing else 1)

        # Progreso dentro del compás vigente (barra teal inferior)
        if 0 <= cur < len(cells):
            _i, _n, _r, v0, v1, _s0, _s1, _nm, _ch = cells[cur]
            x0 = _x_of(v0)
            x1 = _x_of(v1)
            if x1 > x0 and x1 > 0 and x0 < W:
                frac = 0.0
                if v1 > v0:
                    frac = min(1.0, max(0.0, (s16_now - v0) / (v1 - v0)))
                fx = max(x0, min(x1, int(x0 + (x1 - x0) * frac)))
                pygame.draw.line(app.screen, _TEAL,
                                 (max(0, x0), yt0 + th - 2),
                                 (min(W, fx), yt0 + th - 2), 3)
    else:
        txt = app.font_small.render(
            "Sin compases/acordes: genera el .chords.json (I)", True, C_GRAY)
        app.screen.blit(txt, (12, yt0 + th // 2 - txt.get_height() // 2))

    # Playhead fijo (alineado con la tablatura)
    pygame.draw.line(app.screen, C_ACCENT,
                     (CURSOR_X, yt0), (CURSOR_X, yt0 + th), 2)
    pygame.draw.polygon(app.screen, C_ACCENT, [
        (CURSOR_X - 5, yt0), (CURSOR_X + 5, yt0), (CURSOR_X, yt0 + 8)])

    app.screen.set_clip(None)

    # ── Fila inferior: bajo + siguiente + letra ─────────────────────
    yi = y0 + h - info_h
    cur_name = cells[cur][7] if 0 <= cur < len(cells) else ""
    nxt = None
    if 0 <= cur < len(cells):
        for cell in cells[cur + 1:]:
            if not _is_rest(cell[7]):
                nxt = cell[7]
                break

    root = _bass_root(cur_name)
    badge = f"Bajo: {root}"
    bt = app.font_small.render(badge, True, C_GREEN)
    bx = 12
    pygame.draw.rect(app.screen, (10, 30, 18),
                     (bx - 6, yi + 1, bt.get_width() + 12, 18),
                     border_radius=6)
    pygame.draw.rect(app.screen, C_GREEN,
                     (bx - 6, yi + 1, bt.get_width() + 12, 18), 1,
                     border_radius=6)
    app.screen.blit(bt, (bx, yi + 2))

    # Compás seleccionado (o el vigente) como referencia
    ref = sel if (sel is not None and 0 <= sel < len(cells)) else cur
    if 0 <= ref < len(cells):
        cell = cells[ref]
        badge2 = f"Compás {cell[1]}"
        b2 = app.font_small.render(badge2, True, C_ACCENT if sel is not None
                                   else C_GRAY)
        app.screen.blit(b2, (bx + bt.get_width() + 14, yi + 2))
        if nxt and not _is_rest(nxt):
            nx = app.font_small.render(f"→ {nxt}", True, C_GRAY)
            app.screen.blit(nx, (bx + bt.get_width() + 14 +
                                 b2.get_width() + 12, yi + 2))

    line = lyric_at(app.lyric_events, sec)
    if line:
        lt = app.font_small.render(line[:90], True, C_WHITE)
        lx = max(300, W // 2 - lt.get_width() // 2)
        app.screen.blit(lt, (lx, yi + 2))

    # ── Feedback de edición en la barra ─────────────────────────────
    msg = getattr(app, "chord_bar_msg", "")
    if msg:
        mt = app.font_small.render(msg, True, C_ACCENT)
        app.screen.blit(mt, (W - mt.get_width() - 10, yi + 2))
    elif typing:
        ht = app.font_tiny.render("Tab/↑↓ sugerencias · Enter aplicar · "
                                  "Esc cancelar", True, C_GRAY)
        app.screen.blit(ht, (W - ht.get_width() - 10, yi + 4))
    elif sel is not None:
        ht = app.font_tiny.render(
            "Enter editar · Supr sin acorde · F9 deducir · Esc salir",
            True, C_GRAY)
        app.screen.blit(ht, (W - ht.get_width() - 10, yi + 4))
    elif getattr(app, "chord_edit_dirty", False):
        ht = app.font_tiny.render("● acordes sin guardar · Ctrl+S",
                                  True, C_RED)
        app.screen.blit(ht, (W - ht.get_width() - 10, yi + 4))
