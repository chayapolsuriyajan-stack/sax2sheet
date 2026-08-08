"""Core data model shared across pipeline stages.

`NoteEvent` is the one type that flows through the whole pipeline. Every stage
(transcribe -> quantize -> transpose -> notation) consumes and produces lists
of `NoteEvent`, adding fields as it goes but never mutating a prior stage's
output in place — callers always produce a new list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(slots=True)
class NoteEvent:
    """A single transcribed (or derived) note.

    Time fields are in seconds until quantization assigns `beat`/`duration_beats`.
    Pitch is always concert-pitch MIDI (60 = middle C) until transpose.py
    produces written pitches for a specific instrument.
    """

    pitch_midi: int
    onset_s: float
    offset_s: float
    confidence: float = 1.0

    # Populated by quantize.py
    beat: float | None = None
    duration_beats: float | None = None

    # Populated by transpose.py
    written_pitch_midi: int | None = None
    folded: bool = False
    folded_octaves: int = 0

    # Populated / mutated by manual edits (piano roll)
    id: str | None = None
    deleted: bool = False

    @property
    def duration_s(self) -> float:
        return self.offset_s - self.onset_s


class Instrument(str, Enum):
    ALTO = "alto"
    TENOR = "tenor"
    SOPRANO = "soprano"
    BARITONE = "baritone"
    GUITAR = "guitar"
    PIANO = "piano"


@dataclass(slots=True)
class InstrumentSpec:
    name: str
    # Semitones to add to a concert pitch to get the written pitch.
    transposition_semitones: int
    # Written range, inclusive, as MIDI numbers. Roughly Bb3-F#6 for all
    # modern saxophones (written range is the same across the family; only
    # the sounding pitch differs).
    written_low: int = 58   # Bb3
    written_high: int = 90  # F#6
    # General MIDI program number for SoundFont playback (0-indexed).
    gm_program: int = 65  # Alto Sax


INSTRUMENTS: dict[Instrument, InstrumentSpec] = {
    Instrument.SOPRANO: InstrumentSpec("Soprano Saxophone", +2, gm_program=64),
    Instrument.ALTO: InstrumentSpec("Alto Saxophone", +9, gm_program=65),
    Instrument.TENOR: InstrumentSpec("Tenor Saxophone", +14, gm_program=66),
    Instrument.BARITONE: InstrumentSpec("Baritone Saxophone", +21, gm_program=67),
    # Guitar is conventionally notated an octave above its sounding pitch
    # (for treble-clef readability), hence +12 rather than a "real"
    # transposition -- the key signature is unaffected by a full-octave
    # shift (see transpose_key_signature). Range is an approximation of
    # standard notation range (low open E to roughly the 19th-20th fret on
    # the high E string); very high lead lines will still fold.
    Instrument.GUITAR: InstrumentSpec("Guitar", +12, written_low=40, written_high=91, gm_program=24),
    # Piano is concert pitch (no transposition) with the full 88-key range,
    # so folding essentially never triggers for a monophonic melody line.
    Instrument.PIANO: InstrumentSpec("Piano", 0, written_low=21, written_high=108, gm_program=0),
}


@dataclass(slots=True)
class QuantizeSettings:
    bpm: float = 120.0
    grid: str = "16th"  # one of: "8th", "16th", "8th_triplet", "16th_triplet"
    swing: float = 0.0  # 0.0 = straight, 0.66 = heavy swing ratio applied to grid
    time_signature: str = "4/4"


@dataclass(slots=True)
class ScoreSettings:
    instrument: Instrument = Instrument.ALTO
    global_octave_shift: int = 0
    quantize: QuantizeSettings = field(default_factory=QuantizeSettings)
