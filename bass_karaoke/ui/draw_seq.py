"""
Overlays de secuencias paso a paso: técnica (X), arpegios (A), escalas (V).

Los tres comparten estructura: selector, objetivo actual grande, progreso,
lo que oye el micro, marcador y vueltas. La lógica vive en technique.py,
arpeggios.py y scales.py; aquí solo se pinta.
"""
import pygame

from ..config import (
    W, H, C_ACCENT, C_DGRAY, C_GRAY, C_WHITE,
    C_PANEL, C_BLUE, C_GREEN, C_RED, C_OVERLAY, MIN_HZ,
    STRING_NAMES,
)
from .. import technique as tech_logic
from .. import arpeggios as arp_logic
from .. import scales as scale_logic


def _seq_panel(app, title: str, selector: str, current: str,
               step_txt: str, ok: int, total: int, loops: int,
               hold_frac: float, msg: str, hints: str) -> None:
    mw, mh = 620, 400
    mx, my = W // 2 - mw // 2, H // 2 - mh // 2

    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill(C_OVERLAY)
    app.screen.blit(ov, (0, 0))

    pygame.draw.rect(app.screen, C_PANEL,  (mx, my, mw, mh), border_radius=12)
    pygame.draw.rect(app.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

    hdr = app.font_med.render(title, True, C_ACCENT)
    app.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))
    pygame.draw.line(app.screen, C_DGRAY,
                     (mx + 10, my + 44), (mx + mw - 10, my + 44), 1)

    sel = app.font_small.render(selector, True, C_GRAY)
    app.screen.blit(sel, (mx + mw // 2 - sel.get_width() // 2, my + 52))

    big = app.font_big.render(current, True, C_WHITE)
    app.screen.blit(big, (mx + mw // 2 - big.get_width() // 2, my + 82))

    st = app.font_small.render(step_txt, True, C_GRAY)
    app.screen.blit(st, (mx + mw // 2 - st.get_width() // 2, my + 146))

    with app.pitch_lock:
        det_note = app.stable_note
        det_hz   = app.stable_hz
    oigo_col = C_BLUE if det_hz > MIN_HZ else C_GRAY
    oigo = app.font_med.render(f"Oigo: {det_note}", True, oigo_col)
    app.screen.blit(oigo, (mx + mw // 2 - oigo.get_width() // 2, my + 174))

    bw, bh = 340, 14
    bx = mx + mw // 2 - bw // 2
    by = my + 210
    pygame.draw.rect(app.screen, C_DGRAY, (bx, by, bw, bh), border_radius=5)
    if hold_frac > 0:
        pygame.draw.rect(app.screen, C_GREEN,
                         (bx, by, int(bw * min(1.0, hold_frac)), bh),
                         border_radius=5)

    if total > 0:
        pct = int(100 * ok / total)
        scol = C_GREEN if pct >= 70 else C_RED if pct < 40 else C_ACCENT
        sc = app.font_med.render(f"{ok}/{total}  ({pct}%)", True, scol)
    else:
        sc = app.font_med.render("toca el paso para empezar", True, C_GRAY)
    app.screen.blit(sc, (mx + mw // 2 - sc.get_width() // 2, my + 234))

    loops_t = app.font_tiny.render(f"vueltas: {loops}", True, C_GRAY)
    app.screen.blit(loops_t, (mx + mw // 2 - loops_t.get_width() // 2, my + 264))

    if msg:
        m = app.font_small.render(msg[:60], True, C_GRAY)
        app.screen.blit(m, (mx + mw // 2 - m.get_width() // 2, my + 284))

    h = app.font_tiny.render(hints, True, C_GRAY)
    app.screen.blit(h, (mx + mw // 2 - h.get_width() // 2, my + mh - 24))


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
        hold_frac=frac, msg=app.tx_msg,
        hints="N=repetir serie · 1/2 patrón · ↑/↓ inicio · X salir")


def draw_arp(app) -> None:
    st, prog, frac = _seq_current(app, "ar")
    q = arp_logic.QUALITIES.get(app.ar_sel, arp_logic.QUALITIES[2])
    from ..music import midi_of, midi_name
    root = midi_name(midi_of(arp_logic.ROOT_STRING, app.ar_pos))
    _seq_panel(
        app, title="ARPEGIOS · TÓNICA MÓVIL",
        selector=f"{q['title']} en {root}  ·  tónica traste {app.ar_pos}  (1/2/3 cualidad · ↑/↓ tónica)",
        current=f"{st['role']} → {st['name']}  (tr.{st['fret']} {STRING_NAMES[st['string']]} · dedo {st['finger']})",
        step_txt=f"paso {prog}",
        ok=app.ar_ok, total=app.ar_total, loops=app.ar_loops,
        hold_frac=frac, msg=app.ar_msg,
        hints="N=repetir · 1/2/3 cualidad · ↑/↓ tónica · A salir")


def draw_scale(app) -> None:
    st, prog, frac = _seq_current(app, "sc")
    sc = scale_logic.SCALES.get(app.sc_sel, scale_logic.SCALES[1])
    from ..music import midi_of, midi_name
    root = midi_name(midi_of(scale_logic.ROOT_STRING, app.sc_pos))
    _seq_panel(
        app, title="ESCALAS · CAJAS",
        selector=f"{sc['title']} en {root}  ·  tónica traste {app.sc_pos}  (1/2/3 escala · ↑/↓ tónica)",
        current=f"grado {st['degree']} → {st['name']}  (tr.{st['fret']} {STRING_NAMES[st['string']]} · dedo {st['finger']})",
        step_txt=f"paso {prog}",
        ok=app.sc_ok, total=app.sc_total, loops=app.sc_loops,
        hold_frac=frac, msg=app.sc_msg,
        hints="N=repetir · 1/2/3 escala · ↑/↓ tónica · V salir")
