import verovio, os, re
import xml.etree.ElementTree as ET

data_dir = os.path.join(os.path.dirname(verovio.__file__), "data")

def strip_tab_staff(xml_str):
    xml_clean = re.sub(r'<!DOCTYPE[^[>]*(?:\[[^\]]*\])?[^>]*>', '', xml_str)
    root = ET.fromstring(xml_clean)
    for part in root.iter("part"):
        for measure in part.findall("measure"):
            for attrs in measure.findall("attributes"):
                s = attrs.find("staves")
                if s is not None:
                    s.text = "1"
                for clef in list(attrs.findall("clef")):
                    if clef.get("number") == "2":
                        attrs.remove(clef)
                for sd in list(attrs.findall("staff-details")):
                    if sd.get("number") == "2":
                        attrs.remove(sd)
            children = list(measure)
            remove_set, last_bi = set(), None
            for idx, child in enumerate(children):
                if child.tag == "backup":
                    last_bi = idx
                elif child.tag == "note":
                    se = child.find("staff")
                    if se is not None and se.text == "2":
                        remove_set.add(idx)
                        if last_bi is not None:
                            remove_set.add(last_bi)
                            last_bi = None
                    else:
                        last_bi = None
            for idx in sorted(remove_set, reverse=True):
                measure.remove(children[idx])
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

with open(r"C:\DEA\ALE\Ensayos\cancion\mitab.musicxml", encoding="utf-8") as f:
    raw = f.read()
clean = strip_tab_staff(raw)
vrv = verovio.toolkit()
vrv.setResourcePath(data_dir)
vrv.setOptions({"pageWidth": 100000, "breaks": "none", "scale": 50, "footer": "none", "header": "none"})
vrv.loadData(clean)
svg = vrv.renderToSVG(1)
print("SVG length:", len(svg))
print("Note count:", svg.count('class="note"'))
print("Log:", vrv.getLog()[:300] if vrv.getLog() else "(sin errores)")
