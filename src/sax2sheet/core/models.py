"""Core data model shared across pipeline stages.

`NoteEvent` is the one type that flows through the whole pipeline. Every stage
(transcribe -> quantize -> transpose -> notation) consumes and produces lists
of `NoteEvent`, adding fields as it goes but never mutating a prior stage's
output in place — callers always produce a new list.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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

    # Populated by score_import.py. Audio transcription leaves these at their
    # defaults (one part, one staff), so every existing pipeline stage is
    # unaffected -- only imported scores carry real notation structure.
    part_id: str | None = None
    staff: int = 1              # 1 = upper/treble, 2 = lower/bass
    voice: int = 1              # polyphony within a single staff
    hand: str | None = None     # "L" | "R" -- derived from staff, user-overridable
    finger: int | None = None   # 1-5, from MusicXML <fingering> when present

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


# -- Imported scores -----------------------------------------------------
#
# A ScoreDoc is what score_import.py produces from a MusicXML/MIDI file (see
# core/score_import.py). It carries the things a real score has that a flat
# NoteEvent list alone doesn't: title/composer for display, signature and
# tempo changes over time, and measure boundaries (needed for "loop bars
# 9-16" in the tutorial). Imported scores bypass quantize.py/transpose.py
# entirely -- they're already notated and already in the right rhythm.


@dataclass(slots=True)
class TempoMark:
    beat: float
    bpm: float


@dataclass(slots=True)
class TimeSignatureChange:
    beat: float
    time_signature: str  # e.g. "4/4"


@dataclass(slots=True)
class KeySignatureChange:
    beat: float
    sharps: int  # negative = flats, matches transpose.py's convention


@dataclass(slots=True)
class PartInfo:
    part_id: str
    name: str
    staves: int = 1  # 1 = single staff (sax/guitar/vocal), 2 = grand staff (piano)


@dataclass(slots=True)
class ScoreDoc:
    title: str = ""
    composer: str = ""
    parts: list[PartInfo] = field(default_factory=list)
    key_signatures: list[KeySignatureChange] = field(default_factory=list)
    time_signatures: list[TimeSignatureChange] = field(default_factory=list)
    tempos: list[TempoMark] = field(default_factory=list)
    # Beat offset where each measure starts, in order; measure_beats[0] is
    # measure 1's start. A loop over "bars 9-16" is
    # [measure_beats[8], measure_beats[16] or end-of-piece).
    measure_beats: list[float] = field(default_factory=list)
    notes: list[NoteEvent] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "ScoreDoc":
        data = json.loads(text)
        return cls(
            title=data.get("title", ""),
            composer=data.get("composer", ""),
            parts=[PartInfo(**p) for p in data.get("parts", [])],
            key_signatures=[KeySignatureChange(**k) for k in data.get("key_signatures", [])],
            time_signatures=[TimeSignatureChange(**t) for t in data.get("time_signatures", [])],
            tempos=[TempoMark(**t) for t in data.get("tempos", [])],
            measure_beats=data.get("measure_beats", []),
            notes=[NoteEvent(**n) for n in data.get("notes", [])],
        )
