import wave
from pathlib import Path

from sax2sheet.core.storage import get_or_create_project, hash_file


def _write_silence_wav(path: Path, seconds: float = 0.1) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00" * int(44100 * seconds))


def test_same_audio_resolves_to_same_project(tmp_path, monkeypatch):
    from sax2sheet.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")

    wav_a = tmp_path / "a.wav"
    wav_b = tmp_path / "b.wav"
    _write_silence_wav(wav_a)
    _write_silence_wav(wav_b)

    assert hash_file(wav_a) == hash_file(wav_b)

    project1 = get_or_create_project(wav_a, source_label="a.wav")
    project2 = get_or_create_project(wav_b, source_label="b.wav")

    assert project1.id == project2.id
    manifest = project1.load_manifest()
    assert manifest.stages["ingested"] is True
    # source_label from the first ingest wins; re-ingest is a cache hit, not
    # an overwrite.
    assert manifest.source_label == "a.wav"


def test_different_audio_gets_different_projects(tmp_path, monkeypatch):
    from sax2sheet.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")

    wav_a = tmp_path / "a.wav"
    wav_b = tmp_path / "b.wav"
    _write_silence_wav(wav_a, seconds=0.1)
    _write_silence_wav(wav_b, seconds=0.2)

    project1 = get_or_create_project(wav_a, source_label="a.wav")
    project2 = get_or_create_project(wav_b, source_label="b.wav")

    assert project1.id != project2.id
