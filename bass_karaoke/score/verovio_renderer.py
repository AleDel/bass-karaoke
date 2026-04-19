"""
Renderizador de partitura usando Verovio + cairosvg → pygame.Surface.
"""
import os
import xml.etree.ElementTree as ET

from ..config import MUSICXML_PATH, SCORE_H

VEROVIO_OK  = False
CAIROSVG_OK = False

try:
    import verovio as _verovio_mod
    VEROVIO_OK = True
    import shutil as _shutil
    _vrv_data  = os.path.join(os.path.dirname(_verovio_mod.__file__), "data")
    _tgn_dst   = os.path.join(_vrv_data, "tuning-glyphnames.json")
    _tgn_src   = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "..", "tuning-glyphnames.json")
    if not os.path.exists(_tgn_dst) and os.path.exists(_tgn_src):
        _shutil.copy2(_tgn_src, _tgn_dst)
        print("[Verovio] tuning-glyphnames.json instalado en", _vrv_data)
except ImportError:
    print("[WARN] verovio no encontrado — pip install verovio")

try:
    import cairosvg as _cairosvg_mod
    CAIROSVG_OK = True
except ImportError:
    print("[WARN] cairosvg no encontrado — pip install cairosvg")


def strip_tab_staff(xml_str: str) -> str:
    """Elimina el staff de tablatura (staff 2) del MusicXML para que
    Verovio sólo renderice la notación estándar (staff 1)."""
    import re as _re
    xml_clean = _re.sub(r'<!DOCTYPE[^[>]*(?:\[[^\]]*\])?[^>]*>', '', xml_str)
    try:
        root = ET.fromstring(xml_clean)
    except ET.ParseError:
        return xml_str

    for part in root.iter('part'):
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

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')


def init_score_surface(notes: list):
    """
    Pre-renderiza el MusicXML con Verovio → cairosvg → pygame.Surface.

    Devuelve (surface, note_xs) donde note_xs es una lista de
    (start16, pixel_x) para scroll exacto.
    """
    import re
    from io import BytesIO
    import pygame
    import verovio
    import cairosvg

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

        with open(MUSICXML_PATH, "r", encoding="utf-8") as f:
            raw_xml = f.read()
        clean_xml = strip_tab_staff(raw_xml)
        vrv.loadData(clean_xml)
        svg_str = vrv.renderToSVG(1)

        # Extraer posición X de cada nota desde el SVG
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

        def get_tx(el):
            m = re.search(r"translate\(\s*([-\d.eE+]+)", el.get("transform", ""))
            return float(m.group(1)) if m else 0.0

        note_xs_staff1, note_xs_all = [], []

        def walk(el, cx, staff_num=None):
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag == "defs":
                return
            cx2     = cx + get_tx(el)
            cls     = (el.get("class") or "").split()
            el_id   = el.get("id", "")
            cur_stf = staff_num
            if "staff" in cls:
                m = re.search(r"-(\d+)$", el_id)
                if m:
                    cur_stf = int(m.group(1))
            if "note" in cls:
                note_x = cx2
                for child in el:
                    if "notehead" in (child.get("class") or "").split():
                        for gc in child:
                            tx = re.search(r"translate\(\s*([-\d.eE+]+)",
                                           gc.get("transform", ""))
                            if tx:
                                note_x = cx + float(tx.group(1))
                                break
                        break
                note_xs_all.append(note_x)
                if cur_stf == 1:
                    note_xs_staff1.append(note_x)
                return
            for ch in el:
                walk(ch, cx2, cur_stf)

        walk(root_svg, 0.0)

        note_xs_svg = (note_xs_staff1
                       if len(note_xs_staff1) == len(notes)
                       else note_xs_all)

        # Renderizar SVG → PNG (eliminar <text> para evitar problemas de fuentes)
        svg_str = re.sub(r'<text\b[^>]*>.*?</text>', '', svg_str, flags=re.DOTALL)
        target_h  = SCORE_H - 4
        png_bytes = cairosvg.svg2png(
            bytestring=svg_str.encode(),
            output_height=target_h,
        )
        surf = pygame.image.load(BytesIO(png_bytes)).convert_alpha()
        scale_x = surf.get_width() / vb_w

        # Colorizar para tema oscuro
        arr   = pygame.surfarray.pixels3d(surf)
        alpha = pygame.surfarray.pixels_alpha(surf)
        ink   = alpha > 20
        arr[ink]   = [188, 188, 210]
        arr[~ink]  = [0, 0, 0]
        alpha[ink] = 220
        del arr, alpha

        n = min(len(notes), len(note_xs_svg))
        note_xs = [
            (notes[i]["start16"], note_xs_svg[i] * scale_x)
            for i in range(n)
        ]
        print(f"[Verovio] {surf.get_width()}×{surf.get_height()}px  "
              f"notas mapeadas={n}/{len(notes)}")
        return surf, note_xs

    except Exception as _e:
        print(f"[Verovio ERROR] {_e}")
        import traceback; traceback.print_exc()
        return None, []
