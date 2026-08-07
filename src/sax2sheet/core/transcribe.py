"""Wraps Spotify's Basic Pitch to turn an audio file into raw NoteEvents.

Output here is never mutated afterward -- see storage.Project.notes_raw_json.
Downstream layers (quantize, transpose, manual edits) are all additive passes
over this list.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from sax2sheet.config import settings
from sax2sheet.core.models import NoteEvent

# Basic Pitch's ONNX model path is resolved lazily so importing this module
# doesn't force a model load (useful for tests that only exercise other code
# paths).
_model = None


def _get_model():
    global _model
    if _model is None:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import Model
        _model = Model(ICASSP_2022_MODEL_PATH)
    return _model


def transcribe_audio(
    audio_path: Path,
    onset_threshold: float | None = None,
    frame_threshold: float | None = None,
    minimum_note_length_ms: float | None = None,
    minimum_frequency_hz: float | None = None,
    maximum_frequency_hz: float | None = None,
) -> list[NoteEvent]:
    from basic_pitch.inference import predict

    model_output, midi_data, note_events = predict(
        str(audio_path),
        model_or_model_path=_get_model(),
        onset_threshold=onset_threshold if onset_threshold is not None else settings.onset_threshold,
        frame_threshold=frame_threshold if frame_threshold is not None else settings.frame_threshold,
        minimum_note_length=(
            minimum_note_length_ms if minimum_note_length_ms is not None
            else settings.minimum_note_length_ms
        ),
        minimum_frequency=(
            minimum_frequency_hz if minimum_frequency_hz is not None
            else settings.minimum_frequency_hz
        ),
        maximum_frequency=(
            maximum_frequency_hz if maximum_frequency_hz is not None
            else settings.maximum_frequency_hz
        ),
        melodia_trick=True,
    )

    # note_events entries: (start_s, end_s, pitch_midi, amplitude, pitch_bend)
    notes: list[NoteEvent] = []
    for i, ev in enumerate(note_events):
        start_s, end_s, pitch_midi, amplitude = ev[0], ev[1], ev[2], ev[3]
        notes.append(
            NoteEvent(
                id=f"n{i}",
                pitch_midi=int(pitch_midi),
                onset_s=float(start_s),
                offset_s=float(end_s),
                confidence=float(amplitude),
            )
        )
    return sorted(notes, key=lambda n: n.onset_s)


def save_notes(notes: list[NoteEvent], path: Path) -> None:
    path.write_text(json.dumps([asdict(n) for n in notes], indent=2))


def load_notes(path: Path) -> list[NoteEvent]:
    data = json.loads(path.read_text())
    return [NoteEvent(**n) for n in data]
