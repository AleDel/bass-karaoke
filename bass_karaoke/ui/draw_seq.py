"""
Paneles de secuencias paso a paso: técnica (X), arpegios (A), escalas (V).

Estilo Walking Lab: ocupan la zona del tab (mástil y piano visibles) con
el paso actual en letra, en el mástil (anillo blanco) y en pentagrama.
La lógica vive en technique.py, arpeggios.py y scales.py; aquí se pinta.
"""
import pygame

from .. import arpeggios as arp_logic
from .. import scales as scale_logic
from .. import technique as tech_logic
from ..config import (
    C_ACCENT,
    C_BLUE,
    C_DGRAY,
    C_GRAY,
    C_GREEN,
    C_RED,
    C_WHITE,
    NECK_Y,
    STRING_NAMES,
    TAB_Y,
    W,
)
from ..music import midi_name, midi_of
from .staff import draw_mini_staff

STAFF_W = 200


def _seq_panel(app, title: str, selector: str, current: str,
               step_txt: str, ok: int, total: int, loops: int,
               hold_frac: float, msg: str, hints: str,
               staff_midi) -> None:
    y0, h = TAB_Y, NECK_Y - TAB_Y

    pygame.draw.rect(app.screen, (13, 13, 24), (0, y0, W, h))
    pygame.draw.line(app.screen, C_ACCENT, (0, y0), (W, y0), 2)
    pygame.draw.line(app.screen, C_DGRAY, (0, y0 + h - 1), (W, y0 + h - 1), 1)

    t = app.font_med.render(title, True, C_ACCENT)
    app.screen.blit(t, (12, y0 + 8))
    sel = app.font_small.render(selector, True, C_GRAY)
    app.screen.blit(sel, (12, y0 + 38))

    big = app.font_big.render(current, True, C_WHITE)
    app.screen.blit(big, (12, y0 + 66))
    st = app.font_small.render(step_txt, True, C_GRAY)
    app.screen.blit(st, (14, y0 + 138))

    with app.pitch_lock:
        det_note = app.stable_note
        det_hz   = app.stable_hz
    oigo_col = C_BLUE if det_hz > 0 else C_GRAY
    oigo = app.font_med.render(f"Oigo: {det_note}", True, oigo_col)
    app.screen.blit(oigo, (12, y0 + 168))

    bw, bh = 300, 14
    bx, by = 12, y0 + 206
    pygame.draw.rect(app.screen, C_DGRAY, (bx, by, bw, bh), border_radius=5)
    if hold_frac > 0:
        pygame.draw.rect(app.screen, C_GREEN,
                         (bx, by, int(bw * min(1.0, hold_frac)), bh),
                         border_radius=5)

    if total > 0:
        pct = int(100 * ok / total)
        scol = C_GREEN if pct >= 70 else C_RED if pct < 40 else C_ACCENT
        sc = app.font_med.render(f"{ok}/{total}  ({pct}%) · vueltas {loops}",
                                 True, scol)
    else:
        sc = app.font_med.render("toca el paso para empezar", True, C_GRAY)
    app.screen.blit(sc, (12, y0 + 230))

    if msg:
        m = app.font_small.render(msg[:60], True, C_GRAY)
        app.screen.blit(m, (12, y0 + 262))

    hh = app.font_tiny.render(hints, True, C_GRAY)
    app.screen.blit(hh, (12, y0 + h - 22))

    draw_mini_staff(app, W - STAFF_W - 16, y0 + 30, STAFF_W, staff_midi)


def _seq_current(app, p: str):
    steps = getattr(app, f"{p}_steps")
    i = getattr(app, f"{p}_step", 0) % max(1, len(steps))
    hold = getattr(app, f"{p}_hold")
    return steps[i], f"{i + 1}/{len(steps)}", hold / max(0.01, app.tr_hold_need)


def draw_tech(app) -> None:
    st, prog, frac = _seq_current(app, "tx")
    pat = tech_logic.PATTERNS.get(app.tx_sel, tech_logic.PATTERNS[1])
    _seq_panel(
        app, title="TÉCNICA · DEDOS",
        selector=f"{pat['title']}  ·  inicio traste {app.tx_pos}  (1/2 patrón · ↑/↓ inicio)",
        current=f"{st['name']}  (tr.{st['fret']} {STRING_NAMES[st['string']]} · dedo {st['finger']})",
        step_txt=f"paso {prog}  ·  {st.get('label', '')}",
        ok=app.tx_ok, total=app.tx_total, loops=app.tx_loops,
        hold_frac=frac, msg=app.tx_msg, staff_midi=st["midi"],
        hints="N=repetir serie · 1/2 patrón · ↑/↓ inicio · X salir")


def draw_arp(app) -> None:
    st, prog, frac = _seq_current(app, "ar")
    q = arp_logic.QUALITIES.get(app.ar_sel, arp_logic.QUALITIES[2])
    root = midi_name(midi_of(arp_logic.ROOT_STRING, app.ar_pos))
    _seq_panel(
        app, title="ARPEGIOS · TÓNICA MÓVIL",
        selector=f"{q['title']} en {root}  ·  tónica traste {app.ar_pos}  (1/2/3 cualidad · ↑/↓ tónica)",
        current=f"{st['role']} → {st['name']}  (tr.{st['fret']} {STRING_NAMES[st['string']]} · dedo {st['finger']})",
        step_txt=f"paso {prog}",
        ok=app.ar_ok, total=app.ar_total, loops=app.ar_loops,
        hold_frac=frac, msg=app.ar_msg, staff_midi=st["midi"],
        hints="N=repetir · 1/2/3 cualidad · ↑/↓ tónica · A salir")


def draw_scale(app) -> None:
    st, prog, frac = _seq_current(app, "sc")
    sc = scale_logic.SCALES.get(app.sc_sel, scale_logic.SCALES[1])
    root = midi_name(midi_of(scale_logic.ROOT_STRING, app.sc_pos))
    _seq_panel(
        app, title="ESCALAS · CAJAS",
        selector=f"{sc['title']} en {root}  ·  tónica traste {app.sc_pos}  (1/2/3 escala · ↑/↓ tónica)",
        current=f"grado {st['degree']} → {st['name']}  (tr.{st['fret']} {STRING_NAMES[st['string']]} · dedo {st['finger']})",
        step_txt=f"paso {prog}",
        ok=app.sc_ok, total=app.sc_total, loops=app.sc_loops,
        hold_frac=frac, msg=app.sc_msg, staff_midi=st["midi"],
        hints="N=repetir · 1/2/3 escala · ↑/↓ tónica · V salir")
