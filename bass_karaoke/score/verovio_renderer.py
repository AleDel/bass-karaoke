"""
Renderizador de partitura usando Verovio + cairosvg → pygame.Surface.
"""

import logging
import os
import xml.etree.ElementTree as ET

from ..config import MUSICXML_PATH, SCORE_H

log = logging.getLogger(__name__)

VEROVIO_OK  = False
CAIROSVG_OK = False

try:
    import verovio as _verovio_mod
    VEROVIO_OK = True
    import shutil as _shutil
    _vrv_data  = os.path.join(os.path.dirname(_verovio_mod.__file__), "data")
    _proj_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    # El glyph de tuning vive en assets/ (antes en la raíz)
    for _cand in (os.path.join(_proj_root, "assets", "tuning-glyphnames.json"),
                  os.path.join(_proj_root, "tuning-glyphnames.json")):
        if os.path.exists(_cand):
            for _name in ("tuning-glyphnames.json", "glyphnames.json"):
                _dst = os.path.join(_vrv_data, _name)
                if not os.path.exists(_dst):
                    _shutil.copy2(_cand, _dst)
            break
    log.info(f"[Verovio] tuning-glyphnames.json instalado en {_vrv_data}")
except ImportError:
    log.warning("[WARN] verovio no encontrado — pip install verovio")

try:
    import cairosvg as _cairosvg_mod  # noqa: F401
    CAIROSVG_OK = True
except ImportError:
    log.warning("[WARN] cairosvg no encontrado — pip install cairosvg")


def _strip_doctype(xml_str: str) -> str:
    """Quita la declaración ``<!DOCTYPE ...>``, con o sin subconjunto interno.

    Recorrido lineal contando corchetes en lugar de una regex con retroceso
    superlineal (Sonar python:S8786). Devuelve el texto intacto si no hay
    DOCTYPE o si no se cierra.
    """
    start = xml_str.find('<!DOCTYPE')
    if start < 0:
        return xml_str
    depth = 0
    for i in range(start, len(xml_str)):
        ch = xml_str[i]
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
        elif ch == '>' and depth <= 0:
            return xml_str[:start] + xml_str[i + 1:]
    return xml_str


def strip_tab_staff(xml_str: str) -> str:
    """Deja el MusicXML en notación estándar para Verovio.

    Caso normal (staff 1 + staff 2): elimina el staff de tablatura (2).
    Caso tab-only (todas las notas en staff 2, p. ej. exportado desde el
    MIDI de basic_pitch): NO hay nada que dejar, así que en vez de borrar
    todo se reetiqueta el staff 2 → 1 y se quita la tablatura; así la
    partitura se ve en notación estándar.

    Sin este fallback un archivo tab-only quedaba vacío (0 notas)."""
    xml_clean = _strip_doctype(xml_str)
    try:
        root = ET.fromstring(xml_clean)
    except ET.ParseError:
        return xml_str

    def _staff_of(note):
        el = note.find('staff')
        return el.text if el is not None else '1'

    for part in root.iter('part'):
        # ¿Hay alguna nota real (no silencio) fuera del staff 2?
        has_staff1 = any(
            _staff_of(n) != '2'
            for n in part.iter('note')
            if n.find('rest') is None
        )

        for measure in part.findall('measure'):
            for attrs in measure.findall('attributes'):
                staves_el = attrs.find('staves')
                if staves_el is not None:
                    staves_el.text = '1'
                for clef in list(attrs.findall('clef')):
                    if clef.get('number') == '2':
                        attrs.remove(clef)
                for sd in list(attrs.findall('staff-details')):
                    if sd.get('number') == '2':
                        attrs.remove(sd)

            if not has_staff1:
                # Modo tab-only: promueve el staff 2 a notación estándar.
                for note in measure.findall('note'):
                    st = note.find('staff')
                    if st is not None and st.text == '2':
                        st.text = '1'
                    notations = note.find('notations')
                    if notations is not None:
                        for tech in list(notations.findall('technical')):
                            notations.remove(tech)
                        if len(notations) == 0:
                            note.remove(notations)
                continue

            children = list(measure)
            remove_set = set()
            last_backup_idx = None
            for idx, child in enumerate(children):
                if child.tag == 'backup':
                    last_backup_idx = idx
                elif child.tag == 'note':
                    staff_el = child.find('staff')
                    if staff_el is not None and staff_el.text == '2':
                        remove_set.add(idx)
                        if last_backup_idx is not None:
                            remove_set.add(last_backup_idx)
                            last_backup_idx = None
                    else:
                        last_backup_idx = None
            for idx in sorted(remove_set, reverse=True):
                measure.remove(children[idx])

    # Eliminar glissandos (generan warnings de Verovio al no poder cerrarse)
    for part in root.iter('part'):
        # ── Arreglar glissandos huérfanos (bug de TuxGuitar: start sin stop) ──
        from collections import defaultdict as _dd
        gliss_has = _dd(lambda: {'start': False, 'stop': False})
        for note in part.iter('note'):
            for notations in note.findall('notations'):
                for gl in notations.findall('glissando'):
                    num = gl.get('number', '1')
                    typ = gl.get('type', '')
                    if typ in ('start', 'stop'):
                        gliss_has[num][typ] = True
        orphaned = {num for num, d in gliss_has.items()
                    if not (d['start'] and d['stop'])}
        if orphaned:
            for note in part.iter('note'):
                for notations in note.findall('notations'):
                    for gl in list(notations.findall('glissando')):
                        if gl.get('number', '1') in orphaned:
                            notations.remove(gl)
                    for sl in list(notations.findall('slide')):
                        if sl.get('number', '1') in orphaned:
                            notations.remove(sl)

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')


def init_score_surface(notes: list, musicxml_path: str = MUSICXML_PATH):
    """
    Pre-renderiza el MusicXML con Verovio → cairosvg → pygame.Surface.

    Devuelve (surface, note_xs) donde note_xs es una lista de
    (start16, pixel_x) para scroll exacto.
    """
    import re
    from io import BytesIO

    import cairosvg
    import pygame
    import verovio

    try:
        vrv = verovio.toolkit()
        _vrv_data = os.path.join(os.path.dirname(verovio.__file__), "data")
        vrv.setResourcePath(_vrv_data)
        vrv.setOptions({
            "pageWidth":        100000,
            "pageHeight":       2000,
            "adjustPageHeight": True,
            "breaks":           "none",
            "scale":            50,
            "spacingLinear":    0.20,
            "footer":           "none",
            "header":           "none",
        })

        with open(musicxml_path, encoding="utf-8") as f:
            raw_xml = f.read()
        clean_xml = strip_tab_staff(raw_xml)
        vrv.loadData(clean_xml)
        svg_str = vrv.renderToSVG(1)

        # ── Obtener tiempos exactos por ID usando el timemap de Verovio ──────
        timemap = vrv.renderToTimemap()
        id_to_qstamp = {}
        for entry in timemap:
            if isinstance(entry, dict) and "on" in entry:
                qs = entry.get("qstamp", 0)
                for nid in entry["on"]:
                    id_to_qstamp[nid] = qs

        # ── Extraer posición X en el viewBox por ID de cada nota en el SVG ───
        root_svg = ET.fromstring(svg_str)

        def _find_inner_svg(el):
            for ch in el:
                tag = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
                if tag == "svg" and "definition-scale" in (ch.get("class") or ""):
                    return ch
                result = _find_inner_svg(ch)
                if result is not None:
                    return result
            return None

        inner_svg = _find_inner_svg(root_svg) or root_svg
        vb = inner_svg.get("viewBox", "0 0 10000 1000")
        vb_parts = [float(v) for v in vb.split()]
        vb_w = vb_parts[2]

        note_x_by_id = {}   # {svg_id → pos_x en coordenadas viewBox}

        def _collect_note_pos(el, cx=0.0):
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag == "defs":
                return
            tx_m = re.search(r"translate\(\s*([-\d.eE+]+)", el.get("transform", ""))
            cx2 = cx + (float(tx_m.group(1)) if tx_m else 0.0)
            cls = (el.get("class") or "").split()
            if "note" in cls:
                el_id = el.get("id", "")
                note_x = cx2  # posición del contenedor de nota
                # La posición real está en el translate del <use> dentro del notehead
                for ch in el:
                    if "notehead" in (ch.get("class") or "").split():
                        for gc in ch:
                            gc_tx = gc.get("transform", "")
                            gc_m = re.search(r"translate\(\s*([-\d.eE+]+)", gc_tx)
                            if gc_m:
                                note_x = cx + float(gc_m.group(1))
                                break
                        break
                if el_id:
                    note_x_by_id[el_id] = note_x
                return
            for ch in el:
                _collect_note_pos(ch, cx2)

        _collect_note_pos(root_svg)

        # Renderizar SVG → PNG
        # Eliminar <text> (problemas de fuentes en cairosvg)
        svg_clean = re.sub(r'<text\b[^>]*>.*?</text>', '', svg_str, flags=re.DOTALL)
        # Eliminar <rect> sin relleno (contornos de rehearsal marks / direction boxes
        # que Verovio dibuja como rect vacío y que aparecen como rectángulos blancos)
        def _remove_empty_rects(m):
            tag = m.group(0)
            # Si tiene fill explícito distinto de none → conservar…
            fill_m = re.search(r'\bfill=["\']([^"\']+)["\']', tag)
            if fill_m and fill_m.group(1).lower() not in ('none', ''):
                # …salvo fondo de página blanco: con el estilo papel se
                # pintaría de negro (toda la tira quedaría negra).
                if fill_m.group(1).lower() in (
                        '#fff', '#ffffff', 'white', 'rgb(255,255,255)'):
                    return ''
                return tag
            # Sin fill o fill=none → eliminar
            return ''
        svg_clean = re.sub(r'<rect\b[^/]*/>', _remove_empty_rects, svg_clean)
        import numpy as _np
        # Altura útil de la tira en la app (ver draw_score: NAME_H=14, blit en
        # SY+NAME_H+1 con clip hasta SY+SCORE_H).
        target_h = SCORE_H - 15
        # Supersample x2 para trazos nítidos al reducir.
        png_bytes = cairosvg.svg2png(
            bytestring=svg_clean.encode(),
            output_height=target_h * 2,
        )
        big = pygame.image.load(BytesIO(png_bytes)).convert_alpha()

        # Recortar el aire vertical de la página: sin esto el pentagrama ocupa
        # ~1/3 de la tira y se ve minúsculo. Solo recorte vertical → las X no
        # cambian y el mapeo de notas sigue válido. El recorte se centra en el
        # pentagrama (no en la tinta total) para no dejar margen abajo.
        _alp = pygame.surfarray.pixels_alpha(big)
        _any = (_alp > 20).max(axis=0)
        _rows = _np.nonzero(_any)[0]
        _frac = (_alp > 20).mean(axis=0)
        _staff = _np.nonzero(_frac > 0.25)[0]   # líneas del pentagrama: densas
        del _alp
        if len(_rows):
            pad = 10
            y0 = int(_rows.min()) - pad
            y1 = int(_rows.max()) + pad
            if len(_staff):
                staff_c = float(_np.median(_staff))
                hh = max(staff_c - y0, y1 - staff_c)
                y0, y1 = int(staff_c - hh), int(staff_c + hh)
            y0 = max(0, y0)
            y1 = min(big.get_height(), y1)
            big = big.subsurface(pygame.Rect(0, y0, big.get_width(),
                                             max(1, y1 - y0))).copy()
        if big.get_height() != target_h:
            ratio = target_h / big.get_height()
            big = pygame.transform.smoothscale(
                big, (max(1, int(big.get_width() * ratio)), target_h))
        surf = big
        scale_x = surf.get_width() / vb_w

        # Estilo papel mezclando por alfa (conserva el antialiasing; el umbral
        # duro anterior dejaba bordes dentados).
        arr   = pygame.surfarray.pixels3d(surf)
        alpha = pygame.surfarray.pixels_alpha(surf)
        _a = (alpha[..., None].astype(_np.float32)) / 255.0
        _ink   = _np.array([20, 20, 28], dtype=_np.float32)
        _paper = _np.array([250, 250, 246], dtype=_np.float32)
        arr[:, :, :] = (_ink * _a + _paper * (1.0 - _a)).astype(_np.uint8)
        alpha[:, :] = 255
        del arr, alpha, _a

        # ── Mapear notas por start16 usando el timemap (robusto ante notas extra) ──
        # Construir {start16 → pos_x_imagen} desde el timemap + posiciones SVG
        start16_to_x = {}
        for nid, qs in id_to_qstamp.items():
            s16 = round(qs * 4)
            if nid in note_x_by_id and s16 not in start16_to_x:
                start16_to_x[s16] = note_x_by_id[nid] * scale_x

        # Para cada nota de app.notes, buscar su posición por start16
        note_xs = []
        missing = []
        for note in notes:
            s16 = note["start16"]
            if s16 in start16_to_x:
                note_xs.append((s16, start16_to_x[s16]))
            else:
                missing.append(s16)

        # Fallback: interpolar posiciones para notas sin mapeo directo
        if missing and note_xs:
            xs_sorted = sorted(note_xs, key=lambda t: t[0])
            for s16 in missing:
                # Interpolación lineal entre los vecinos conocidos
                if s16 <= xs_sorted[0][0]:
                    note_xs.append((s16, xs_sorted[0][1]))
                elif s16 >= xs_sorted[-1][0]:
                    note_xs.append((s16, xs_sorted[-1][1]))
                else:
                    for k in range(len(xs_sorted) - 1):
                        b0, x0 = xs_sorted[k]; b1, x1 = xs_sorted[k + 1]
                        if b0 <= s16 <= b1:
                            t = (s16 - b0) / (b1 - b0) if b1 > b0 else 0.0
                            note_xs.append((s16, x0 + t * (x1 - x0)))
                            break
        note_xs.sort(key=lambda t: t[0])

        mapped = len([n for n in notes if n["start16"] in start16_to_x])
        log.info(f"[Verovio] {surf.get_width()}×{surf.get_height()}px  "
              f"notas mapeadas={mapped}/{len(notes)}  "
              f"timemap={len(id_to_qstamp)}  svg_notas={len(note_x_by_id)}")
        return surf, note_xs

    except Exception as _e:
        log.error(f"[Verovio ERROR] {_e}")
        import traceback

        traceback.print_exc()
        return None, []
