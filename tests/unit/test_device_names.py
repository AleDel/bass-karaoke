"""Nombres de dispositivos de audio: reparación de mojibake y avisos."""
from bass_karaoke.audio.pitch_engine import clean_device_name, device_name_warning

# PyAudio (Windows) devuelve el nombre UTF-8 mal decodificado como latin-1.
MOJIBAKE_MIC = "Micrófono".encode().decode("latin-1")


def test_repara_mojibake_utf8():
    assert clean_device_name(MOJIBAKE_MIC) == "Micrófono"
    assert clean_device_name("Línea (4- Steinberg UR22)".encode()
                             .decode("latin-1")) == "Línea (4- Steinberg UR22)"


def test_deja_intacto_texto_ya_correcto():
    assert clean_device_name("Microphone (RTX-Audio Point)") == "Microphone (RTX-Audio Point)"
    assert clean_device_name("Asignador de sonido Microsoft - Input") == \
        "Asignador de sonido Microsoft - Input"


def test_no_rompe_texto_latin1_legitimo():
    # 'Café' en latin-1 no es UTF-8 válido → se conserva tal cual.
    assert clean_device_name("Caf\xe9") == "Caf\xe9"


def test_acepta_bytes_y_otros_tipos():
    assert clean_device_name(b"Micr\xc3\xb3fono") == "Micrófono"
    assert clean_device_name(7) == "7"


def test_avisa_de_salidas_y_loopback():
    assert device_name_warning("CABLE Output (VB-Audio Virtual Cable)")
    assert device_name_warning("VoiceMeeter Output")
    assert device_name_warning("Stereo Mix")
    assert device_name_warning("Línea (4- Steinberg UR22)") is None
