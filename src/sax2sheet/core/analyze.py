"""librosa-based supporting analysis: tempo and a rough key estimate.

These feed sensible *defaults* into QuantizeSettings and the notation key
signature -- both stay user-overridable (see the manual BPM/grid/swing
controls this powers), because automatic tempo and key detection are
frequently wrong on real material: half/double-time ambiguity, modal or
minor material, rubato.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

# Krumhansl-Schmuckler key profiles, used for a coarse major/minor guess.
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Sharps count (negative = flats) for each major-key tonic pitch class.
_MAJOR_SHARPS = {
    "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
    "F": -1, "A#": -2, "D#": -3, "G#": -4,
}


@dataclass(slots=True)
class AnalysisResult:
    bpm: float
    key_tonic: str
    key_mode: str  # "major" | "minor"
    key_sharps: int  # signature sharps (negative = flats), for notation


def analyze_audio(audio_path: Path) -> AnalysisResult:
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if np.ndim(tempo) == 0 else float(tempo[0])

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)

    best_score, best_tonic, best_mode = -np.inf, "C", "major"
    for shift in range(12):
        major_corr = np.corrcoef(np.roll(_MAJOR_PROFILE, shift), chroma_mean)[0, 1]
        minor_corr = np.corrcoef(np.roll(_MINOR_PROFILE, shift), chroma_mean)[0, 1]
        if major_corr > best_score:
            best_score, best_tonic, best_mode = major_corr, _PITCH_CLASSES[shift], "major"
        if minor_corr > best_score:
            best_score, best_tonic, best_mode = minor_corr, _PITCH_CLASSES[shift], "minor"

    # A minor key shares its signature with the major key a minor third up.
    sharps_tonic = best_tonic
    if best_mode == "minor":
        idx = (_PITCH_CLASSES.index(best_tonic) + 3) % 12
        sharps_tonic = _PITCH_CLASSES[idx]
    sharps = _MAJOR_SHARPS.get(sharps_tonic, 0)

    return AnalysisResult(bpm=round(bpm, 1), key_tonic=best_tonic, key_mode=best_mode, key_sharps=sharps)
