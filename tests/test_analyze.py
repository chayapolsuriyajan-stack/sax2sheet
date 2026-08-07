import math
import wave
import struct

from sax2sheet.core.analyze import analyze_audio


def _write_click_track(path, bpm=120.0, seconds=4.0, sr=22050):
    """A short click track at a known tempo -- good enough to sanity-check
    that beat tracking returns something in the right neighborhood. Exact
    BPM detection on clicks alone is not guaranteed (octave errors are a
    known failure mode of beat trackers, which is exactly why quantize.py
    exposes a manual override), so the test only checks for a musically
    plausible range.
    """
    interval = 60.0 / bpm
    n = int(sr * seconds)
    frames = bytearray()
    next_click_sample = 0
    click_len = int(sr * 0.01)
    for i in range(n):
        t = i / sr
        if i >= next_click_sample and i < next_click_sample + click_len:
            val = int(20000 * math.sin(2 * math.pi * 2000 * (i - next_click_sample) / sr))
        else:
            val = 0
        frames += struct.pack("<h", val)
        if i >= next_click_sample + click_len and t >= (next_click_sample / sr) + interval - 0.005:
            next_click_sample = i + 1

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))


def test_analyze_returns_plausible_tempo_and_key(tmp_path):
    path = tmp_path / "click.wav"
    _write_click_track(path, bpm=120.0)

    result = analyze_audio(path)

    # Beat trackers commonly report a half/double-time octave error, which is
    # precisely why quantize.py's BPM is user-overridable -- assert the
    # plausible band rather than an exact value.
    assert 50 <= result.bpm <= 260
    assert result.key_mode in ("major", "minor")
    assert -7 <= result.key_sharps <= 7
