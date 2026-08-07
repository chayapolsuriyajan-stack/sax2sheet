"""Optional Demucs-based stem separation (drums/bass/vocals/other).

Kept as an opt-in stage: `demucs`+`torch` are a multi-GB install and CPU
inference is slow (minutes for a few-minute track), so this is invoked
explicitly by the user, not automatically on ingest. Results are cached to
project.stem_wav(name) -- separating the same project twice is a no-op unless
`force=True`.

Demucs is not instrument-aware: saxophone lands in the "other" stem, mixed
with any other melodic/harmonic instruments the model doesn't have a
dedicated stem for. This is a real accuracy improvement on dense mixes, not
clean isolation -- the pitch-range gate in transcribe.py still matters even
with separation on.

Implementation note: we call Demucs's model directly and write stems with
`soundfile` rather than shelling out to `python -m demucs` and letting it
save via torchaudio. Recent torchaudio releases dropped their built-in audio
backends in favor of an optional `torchcodec` dependency that Demucs itself
doesn't declare -- and on Windows, torchcodec's prebuilt wheels fail to load
their native library (no matching FFmpeg build). Loading/saving audio
ourselves via `soundfile` (already a dependency for the rest of the app)
sidesteps that whole broken chain.
"""

from __future__ import annotations

import numpy as np

from sax2sheet.core.storage import Project

STEM_NAMES = ("vocals", "drums", "bass", "other")
DEMUCS_MODEL = "htdemucs"


def is_available() -> bool:
    try:
        import demucs  # noqa: F401
        return True
    except ImportError:
        return False


def separate_project(project: Project, force: bool = False) -> list[str]:
    """Run Demucs on project.source_wav, populating project.stem_wav(name)
    for each stem in STEM_NAMES. Returns the list of stem names now
    available. Raises RuntimeError if the `separate` extra isn't installed.
    """
    if not is_available():
        raise RuntimeError(
            "Demucs is not installed. Install the optional 'separate' extra "
            "(`uv sync --extra separate`) to enable stem separation."
        )

    if not force and all(project.stem_wav(s).exists() for s in STEM_NAMES):
        return list(STEM_NAMES)

    import soundfile as sf
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = get_model(DEMUCS_MODEL)
    model.eval()

    wav, sr = sf.read(str(project.source_wav), dtype="float32", always_2d=True)
    wav = wav.T  # (channels, samples)
    if wav.shape[0] == 1:
        wav = np.repeat(wav, model.audio_channels, axis=0)

    if sr != model.samplerate:
        import librosa
        wav = librosa.resample(wav, orig_sr=sr, target_sr=model.samplerate, axis=1)
        sr = model.samplerate

    tensor = torch.from_numpy(wav).unsqueeze(0)  # (batch=1, channels, samples)
    with torch.no_grad():
        sources = apply_model(model, tensor, progress=False)[0]  # (n_stems, channels, samples)

    produced = {}
    for name, source in zip(model.sources, sources):
        produced[name] = source.numpy().T  # (samples, channels)

    for stem in STEM_NAMES:
        if stem not in produced:
            raise RuntimeError(f"demucs model did not produce expected stem: {stem}")
        sf.write(str(project.stem_wav(stem)), produced[stem], sr)

    manifest = project.load_manifest()
    manifest.stages["separated"] = True
    project.save_manifest(manifest)

    return list(STEM_NAMES)


def available_stems(project: Project) -> list[str]:
    return [s for s in STEM_NAMES if project.stem_wav(s).exists()]
