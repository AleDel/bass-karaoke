"""Launcher para PyInstaller: ejecuta el paquete bass_karaoke."""
import io
import os
import sys


def _verify():
    """Autochequeo del build (uso: BK_VERIFY=1 BassKaraoke.exe).
    Verifica en el entorno congelado: pyaudio, soundfile, verovio y cairosvg.
    Escribe los resultados en _verify_out.txt junto al .exe y sale."""
    out = os.path.join(os.path.dirname(sys.executable), "_verify_out.txt")

    def log(*a):
        msg = " ".join(str(x) for x in a)
        with io.open(out, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    log("=== verify start ===")
    try:
        import bass_karaoke.features
        bass_karaoke.features.ensure_on_path()

        from bass_karaoke.audio import INPUT_AVAILABLE, PA_OK, SOUNDFILE_OK, load_mp3_samples
        log("audio:", "PA_OK=%s INPUT_AVAILABLE=%s SOUNDFILE_OK=%s"
            % (PA_OK, INPUT_AVAILABLE, SOUNDFILE_OK))

        from bass_karaoke.score import VEROVIO_OK, CAIROSVG_OK, init_score_surface
        log("score:", "VEROVIO_OK=%s CAIROSVG_OK=%s" % (VEROVIO_OK, CAIROSVG_OK))

        songs = os.path.join(os.path.dirname(sys.executable), "songs",
                             "feet_dont_fail_me_now")
        mp3 = os.path.join(songs, "feet_dont_fail_me_now.mp3")
        xml = os.path.join(songs, "feet_dont_fail_me_now.musicxml")

        y, sr = load_mp3_samples(mp3)
        log("waveform:", "decoded=%s sr=%s len=%s"
            % (y is not None, sr, 0 if y is None else len(y)))

        if CAIROSVG_OK:
            import cairosvg
            png = cairosvg.svg2png(
                bytestring=b'<svg xmlns="http://www.w3.org/2000/svg" width="20" '
                           b'height="20"><rect width="20" height="20" fill="#000"/></svg>')
            log("cairosvg svg2png:", "ok bytes=%d" % len(png))
        else:
            log("cairosvg: NO")

        if VEROVIO_OK:
            import verovio
            from bass_karaoke.score.verovio_renderer import strip_tab_staff
            log("verovio __file__:", verovio.__file__)
            log("verovio data:", os.path.join(os.path.dirname(verovio.__file__), "data"),
                "existe=%s" % os.path.isdir(
                    os.path.join(os.path.dirname(verovio.__file__), "data")))
            with io.open(xml, "r", encoding="utf-8") as f:
                raw_xml = f.read()
            clean_xml = strip_tab_staff(raw_xml)
            vk = verovio.toolkit()
            vk.setResourcePath(os.path.join(os.path.dirname(verovio.__file__), "data"))
            vk.setOptions({"pageWidth": 100000, "pageHeight": 2000,
                           "adjustPageHeight": True, "breaks": "none", "scale": 50,
                           "spacingLinear": 0.20, "footer": "none", "header": "none"})
            ok = vk.loadData(clean_xml)
            svg_str = vk.renderToSVG(1)
            log("verovio loadData+renderToSVG:", "ok=%s svg_len=%d"
                % (ok, len(svg_str)))
        else:
            log("verovio: NO")

        try:
            import pygame
            pygame.init()
            pygame.display.set_mode((64, 64))
            surf, note_xs = init_score_surface([], xml)
            log("init_score_surface:", "surface=%s note_xs=%d"
                % (surf is not None, len(note_xs)))
        except Exception as e:
            log("init_score_surface ERROR:", repr(e))
    except Exception as e:
        import traceback
        log("FATAL:", repr(e))
        log(traceback.format_exc())
    log("=== verify done ===")


from bass_karaoke.main import main

if __name__ == "__main__":
    if os.environ.get("BK_VERIFY") == "1":
        _verify()
    else:
        main()