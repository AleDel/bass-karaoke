"""
Paneles inferiores: tarjeta de aciertos por sección.

Las antiguas piezas (nota siguiente, metrónomo, pitch, barra inferior) se
integraron en la rueda, la barra de transporte y la cabecera del mástil;
se mantienen los nombres como envoltorios para no romper importaciones.
"""
import pygame

from . import theme as T
from .theme import ACCENT, TEXT, TEXT_MUTED

# Color fijo por sección, como la referencia (A verde, B cian, C ámbar…)
_SECTION_COLORS = (
    T.GREEN, ACCENT, T.ORANGE, T.PURPLE, T.YELLOW, T.RED,
)


def _sections(app):
    """[(sección, ok, total)] en orden musical estable."""
    rows = [(s, int(d.get("ok", 0)), int(d.get("total", 0)))
            for s, d in app.section_stats.items()
            if d.get("total", 0) > 0]
    rows.sort(key=lambda r: (str(r[0])))
    return rows


def _section_color(index: int):
    return _SECTION_COLORS[index % len(_SECTION_COLORS)]


def draw_stats_panel(app) -> None:
    """Aciertos por sección: tres anillos + resumen con leyenda de color."""
    L = app.layout
    card = L.stats
    T.card(app.screen, card, L.radius)

    f_lbl = T.font(L.fs(9), bold=True)
    T.text(app.screen, f_lbl, "ACIERTOS POR SECCIÓN", TEXT_MUTED,
           (card.centerx, card.y + int(10 * L.s)), "midtop")

    rows = _sections(app)
    if not rows:
        T.text(app.screen, T.font(L.fs(11)), "aún sin datos de práctica",
               TEXT_MUTED, (card.centerx, card.centery), "center")
        return

    top = rows[:3]

    # ── Fila superior: 3 anillos grandes ────────────────────────────────
    n = len(top)
    radius = int(min(card.w / (n * 2.75), card.h * 0.19))
    thick = max(6, int(radius * 0.29))
    cy = card.y + int(card.h * 0.38)
    slot = card.w / max(1, n)
    f_pct = T.font(max(10, int(radius * 0.40)), bold=True)

    for i, (sec, ok, total) in enumerate(top):
        pct = ok / max(1, total)
        cx = int(card.x + slot * (i + 0.5))
        T.ring(app.screen, (cx, cy), radius, pct, _section_color(i), thick,
               track=(46, 52, 62))
        T.text(app.screen, f_pct, f"{int(round(pct * 100))}%", TEXT,
               (cx, cy), "center")
        T.text(app.screen, f_lbl, str(sec)[:8],
               TEXT_MUTED, (cx, cy + radius + int(7 * L.s)), "midtop")

    # ── Fila inferior: media + leyenda de colores ───────────────────────
    total_ok = sum(ok for _s, ok, _t in rows)
    total_all = max(1, sum(t for _s, _ok, t in rows))
    avg = total_ok / total_all

    ly = card.bottom - int(card.h * 0.20)
    r_small = max(10, int(card.h * 0.065))
    ax = card.x + int(14 * L.s) + r_small
    T.ring(app.screen, (ax, ly), r_small, avg,
           _section_color(0) if avg >= 0.5 else T.RED,
           max(4, int(r_small * 0.28)), track=(46, 52, 62))
    T.text(app.screen, T.font(max(8, int(r_small * 0.58)), bold=True),
           f"{int(round(avg * 100))}%", TEXT, (ax, ly), "center")
    T.text(app.screen, f_lbl, "MEDIA", TEXT_MUTED,
           (ax, ly + r_small + int(3 * L.s)), "midtop")

    # Pastillas de color con el nombre de cada sección
    lx = ax + r_small + int(20 * L.s)
    avail = card.right - int(14 * L.s) - lx
    items = rows[:3]
    if items:
        gap = int(9 * L.s)
        pw = min(int(64 * L.s),
                 (avail - gap * (len(items) - 1)) // len(items))
        ph = max(12, int(15 * L.s))
        for i, (sec, ok, tot) in enumerate(items):
            pill = pygame.Rect(lx + i * (pw + gap), ly - ph // 2, pw, ph)
            pygame.draw.rect(app.screen, _section_color(i), pill,
                             border_radius=max(3, int(4 * L.s)))
            T.text(app.screen, T.font(L.fs(8), bold=True), str(sec)[:8],
                   TEXT_MUTED, (pill.centerx, pill.bottom + int(9 * L.s)),
                   "midtop")


# ── Compatibilidad: estas piezas viven ahora en otras tarjetas ──────────────
def draw_note_panel(app) -> None:
    """Sustituido por la rueda (ui.draw_shell.draw_gauge_card)."""


def draw_metronome(app) -> None:
    """Integrado en la barra de transporte (ui.draw_shell.draw_transport)."""


def draw_pitch_panel(app) -> None:
    """Integrado en la cabecera del mástil (ui.draw_neck)."""


def draw_bottom_bar(app) -> None:
    """Sustituido por las pistas inferiores (ui.draw_shell.draw_hints)."""
