"""
Mini-mástil horizontal (tarjeta inferior izquierda).

Muestra el mapa de la canción sobre las cuatro cuerdas, la nota que toca
ahora y la que detecta el micrófono. Sigue siendo clicable para oír notas
y para el modo mapa (H).
"""
import math

import pygame

from ..config import MIN_HZ, STRING_NAMES
from . import theme as T
from .theme import ACCENT, TEXT, TEXT_DIM, TEXT_MUTED
from .draw_shell import _next_note, string_color

FRETS = 13


def fret_x(L, fret: int) -> int:
    area = L.neck_area
    x0 = area.x + int(6 * L.s)
    x1 = area.right - int(6 * L.s)
    return int(x0 + (x1 - x0) * (fret / FRETS))


def _pitch_state(app):
    """(texto, color, cents) del detector de pitch."""
    with app.pitch_lock:
        hz = app.stable_hz
        note = app.stable_note
    cur = app.current_note()
    if hz <= MIN_HZ:
        return "", (110, 116, 126), None
    cents = None
    if cur and cur.get("hz", 0) > 0:
        try:
            cents = 1200.0 * math.log2(hz / cur["hz"])
            while cents > 600:
                cents -= 1200
            while cents < -600:
                cents += 1200
        except Exception:
            cents = None
    if app.note_match is True:
        col = T.GREEN
    elif app.note_match is False:
        col = T.RED
    else:
        col = ACCENT
    txt = f"{note}  {hz:.1f} Hz"
    if cents is not None:
        txt += f"  {cents:+.0f}¢"
    return txt, col, cents


def draw_neck(app) -> None:
    L = app.layout
    card = L.neck

    # Estado de pitch arriba a la derecha (la tarjeta la dibuja el armazón)
    txt, col, cents = _pitch_state(app)
    if txt:
        f_val = T.font(L.fs(10), bold=True)
        right = card.right - int(10 * L.s)
        T.text(app.screen, f_val, txt, col, (right, card.y + int(9 * L.s)),
               "topright")
        if cents is not None:
            bar_w = int(68 * L.s)
            bar = pygame.Rect(right - bar_w, card.y + int(22 * L.s), bar_w,
                              max(2, int(3 * L.s)))
            pygame.draw.rect(app.screen, (48, 50, 53)[:3], bar,
                             border_radius=bar.h // 2)
            cx = bar.centerx + int(max(-1.0, min(1.0, cents / 50.0)) * bar.w / 2)
            pygame.draw.circle(app.screen, col, (cx, bar.centery),
                               max(2, int(2.5 * L.s)))

    area = L.neck_area
    T.inset(app.screen, area, radius=max(6, int(9 * L.s)))

    # Trastes (0 a FRETS)
    f_num = T.font(L.fs(8))
    f_num_active = T.font(L.fs(8), bold=True)
    cur = app.current_note() or _next_note(app)
    cur_fret = cur.get("fret") if cur else None

    # Celda del traste actual: apenas un velo, sin columna luminosa
    if cur_fret is not None and 0 <= cur_fret <= FRETS:
        xc = fret_x(L, cur_fret)
        step = (area.w - int(12 * L.s)) / FRETS
        half = max(8, int(step * 0.46))
        band = pygame.Surface((half * 2, max(4, area.h - int(24 * L.s))),
                              pygame.SRCALPHA)
        pygame.draw.rect(band, (*string_color(cur.get("string")), 12),
                         band.get_rect(), border_radius=max(4, int(6 * L.s)))
        app.screen.blit(band, (xc - half, area.y + 6))

    for fret in range(0, FRETS + 1):
        x = fret_x(L, fret)
        if fret > 0:
            pygame.draw.line(app.screen, (52, 58, 68),
                             (x, area.y + 6), (x, area.bottom - int(12 * L.s)), 1)
        is_cur_fret = (fret == cur_fret)
        f_col = (232, 190, 74) if is_cur_fret else (108, 116, 128)
        f_use = f_num_active if is_cur_fret else f_num
        T.text(app.screen, f_use, str(fret), f_col,
               (x, area.bottom - int(3 * L.s)), "midbottom")

    # Cuerdas
    f_str = T.font(L.fs(11), bold=True)
    for s, y in L.neck_strings.items():
        pygame.draw.line(app.screen, string_color(s),
                         (area.x + int(5 * L.s), y),
                         (area.right - int(4 * L.s), y),
                         {4: 2, 3: 2, 2: 1, 1: 1}[s])
        # Punto de cuerda al aire junto a la cejilla
        pygame.draw.circle(app.screen, string_color(s),
                           (area.x + int(5 * L.s), y), max(2, int(2.4 * L.s)))
        # Ceja (traste 0) marcada con una barra clara
        if s == 1:
            pygame.draw.line(app.screen, (206, 212, 222),
                             (area.x + int(3 * L.s), L.neck_strings[1] - 3),
                             (area.x + int(3 * L.s), L.neck_strings[4] + 3), 2)
        T.text(app.screen, f_str, STRING_NAMES[s], string_color(s),
               (card.x + int(11 * L.s), y), "midleft")

    cur = app.current_note() or _next_note(app)

    # Mapa de la canción: puntos tenues de todas las posiciones usadas
    if getattr(app.view, "neck_map", False) and app.notes:
        from collections import Counter
        freq = Counter((n["fret"], n["string"]) for n in app.notes)
        mx = max(freq.values()) if freq else 1
        for (fret, string), cnt in freq.items():
            if not (0 <= fret <= FRETS) or string not in L.neck_strings:
                continue
            x = fret_x(L, fret)
            y = L.neck_strings[string]
            r = max(2, (3 + 3 * cnt / mx) * L.s)
            T.dot(app.screen, (x, y), r, (78, 84, 96))
            T.dot(app.screen, (x, y), max(1, r - 1.4 * L.s),
                  string_color(string))
    else:
        # Posiciones usadas por la canción: marcas mínimas, casi invisibles,
        # para no ensuciar el mástil (la referencia va limpia).
        if app.notes:
            bar16 = max(4, int(getattr(app, "beats_per_bar", 4) or 4) * 4)
            lo = app.beat_time - bar16
            hi = app.beat_time + bar16 * 2
            for n in app.notes:
                fret = n["fret"]
                if not (0 <= fret <= FRETS) or n["string"] not in L.neck_strings:
                    continue
                x = fret_x(L, fret)
                y = L.neck_strings[n["string"]]
                near = (lo <= n["start16"] <= hi)
                T.dot(app.screen, (x, y), max(1.1, (2.0 if near else 1.4) * L.s),
                      (128, 136, 150) if near else (44, 50, 60))

    # Nota actual: orbe con el color de su cuerda y núcleo blanco
    active_cur = cur if cur else {"fret": 0, "string": 3}
    if active_cur and 0 <= active_cur.get("fret", 0) <= FRETS:
        afret = active_cur.get("fret", 0)
        astring = active_cur.get("string", 3)
        x = fret_x(L, afret)
        y = L.neck_strings.get(astring, area.centery)
        colc = string_color(astring)
        # Capa de halo luminoso (bloom)
        rr = max(16, int(24 * L.s))
        surf_bloom = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
        for k, a in ((rr, 26), (int(rr * 0.62), 66), (int(rr * 0.36), 120)):
            pygame.draw.circle(surf_bloom, (*colc, a), (rr, rr), k)
        app.screen.blit(surf_bloom, (x - rr, y - rr))
        pygame.draw.circle(app.screen, colc, (x, y), max(5, int(6.5 * L.s)))
        pygame.draw.circle(app.screen, (255, 253, 238), (x, y),
                           max(2, int(2.2 * L.s)))

    # Nota detectada por el micrófono
    with app.pitch_lock:
        det_hz = app.stable_hz
    if det_hz > MIN_HZ:
        best = app._hz_to_fret_string(det_hz)
        if best and best[1] in L.neck_strings and 0 <= best[0] <= FRETS:
            x = fret_x(L, best[0])
            y = L.neck_strings[best[1]]
            pygame.draw.circle(app.screen, ACCENT, (x, y),
                               max(4, int(5 * L.s)), max(1, int(2 * L.s)))

    # Nota pulsada con el ratón
    prev = getattr(app.view, "preview_fret_str", None)
    if prev and getattr(app.view, "preview_timer", 0) > 0:
        pf, ps = prev
        if ps in L.neck_strings and 0 <= pf <= FRETS:
            x = fret_x(L, pf)
            y = L.neck_strings[ps]
            pygame.draw.circle(app.screen, ACCENT, (x, y),
                               max(4, int(7 * L.s)), max(1, int(2 * L.s)))

    # Pista de modo secuencia / entrenamiento
    sp = getattr(app, "seq_pos", None)
    if sp and sp[1] in L.neck_strings and 0 <= sp[0] <= FRETS:
        x = fret_x(L, sp[0])
        y = L.neck_strings[sp[1]]
        pygame.draw.circle(app.screen, TEXT, (x, y),
                           max(5, int(7 * L.s)), max(1, int(2 * L.s)))
        lbl = getattr(app, "seq_label", "")
        if lbl:
            T.text(app.screen, T.font(L.fs(9), bold=True), lbl, TEXT,
                   (x, y - int(12 * L.s)), "center")


