"""Quantization: maps raw onset/offset times (seconds) onto a metrical grid,
given BPM, grid resolution, and an optional swing ratio.

Pure function over NoteEvent lists -- never touches notes.raw.json. This is
what lets tempo/grid/swing be tuned live in the UI without re-running
transcription: callers always pass in onset/offset seconds (straight from the
raw transcription, or from edits.apply_edits) and get back the same notes
with `beat`/`duration_beats` populated.
"""

from __future__ import annotations

from dataclasses import asdict

from sax2sheet.core.models import NoteEvent, QuantizeSettings

# Subdivisions per beat for each supported grid.
_GRID_DIVISIONS = {
    "8th": 2,
    "16th": 4,
    "8th_triplet": 3,
    "16th_triplet": 6,
}

# Floor so a note quantized to nothing (onset == offset after snapping)
# doesn't collapse to zero duration and vanish from notation.
MIN_DURATION_BEATS = 0.0625  # a 64th note at a 4-beat measure


def _snap_to_grid(beat: float, divisions: int) -> float:
    unit = 1.0 / divisions
    return round(beat / unit) * unit


def _apply_swing(beat: float, divisions: int, swing: float) -> float:
    """Delay the off-beat ('and') subdivision toward `swing` (a fraction of
    the beat, e.g. 0.667 for a triplet feel). Only meaningful on the 8th-note
    grid; other grids pass through unchanged.
    """
    if swing <= 0 or divisions != 2:
        return beat
    beat_index = int(beat)
    frac = beat - beat_index
    if abs(frac - 0.5) < 1e-6:
        return beat_index + swing
    return beat


def quantize_notes(notes: list[NoteEvent], settings: QuantizeSettings) -> list[NoteEvent]:
    beats_per_second = settings.bpm / 60.0
    divisions = _GRID_DIVISIONS[settings.grid]

    out: list[NoteEvent] = []
    for n in notes:
        new = NoteEvent(**asdict(n))
        onset_beat = _apply_swing(_snap_to_grid(n.onset_s * beats_per_second, divisions), divisions, settings.swing)
        offset_beat = _apply_swing(_snap_to_grid(n.offset_s * beats_per_second, divisions), divisions, settings.swing)

        duration = offset_beat - onset_beat
        if duration < MIN_DURATION_BEATS:
            duration = MIN_DURATION_BEATS
            offset_beat = onset_beat + duration

        new.beat = onset_beat
        new.duration_beats = duration
        out.append(new)
    return out
