import os
from pathlib import Path

import verovio

from bass_karaoke.score.verovio_renderer import strip_tab_staff

data_dir = os.path.join(os.path.dirname(verovio.__file__), "data")

with open(Path(__file__).parent.parent / "songs" / "mitab" / "mitab.musicxml", encoding="utf-8") as f:
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
