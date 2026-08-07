"""Concert-pitch -> written-pitch transposition for Bb/Eb saxophones, plus
playable-range enforcement.

Out-of-range notes are octave-folded until they fit the written range, and
flagged (`folded`) rather than silently altered -- this matters most for the
"arrange another instrument's melody for sax" use case, where source material
(vocal lines, bass lines) routinely falls outside a horn's range. See
core/models.py for the instrument table.
"""

from __future__ import annotations

from dataclasses import asdict

from sax2sheet.core.models import INSTRUMENTS, Instrument, NoteEvent


def transpose_notes(
    notes: list[NoteEvent],
    instrument: Instrument,
    global_octave_shift: int = 0,
) -> list[NoteEvent]:
    """Compute written pitches for `instrument` from concert-pitch notes.

    Pure function: never mutates `notes`. Returns new NoteEvent objects with
    `written_pitch_midi`, `folded`, and `folded_octaves` populated.
    """
    spec = INSTRUMENTS[instrument]
    out: list[NoteEvent] = []
    for n in notes:
        new = NoteEvent(**asdict(n))
        pitch = new.pitch_midi + spec.transposition_semitones + 12 * global_octave_shift
        folded_octaves = 0
        while pitch < spec.written_low:
            pitch += 12
            folded_octaves += 1
        while pitch > spec.written_high:
            pitch -= 12
            folded_octaves -= 1
        new.written_pitch_midi = pitch
        new.folded = folded_octaves != 0
        new.folded_octaves = folded_octaves
        out.append(new)
    return out


def transpose_key_signature(concert_sharps: int, instrument: Instrument) -> int:
    """Transpose a major-key signature (sharps count; negative = flats) to
    the given instrument's written key. Delegates the circle-of-fifths math
    and enharmonic spelling to music21, which is also used for notation
    export (core/notation.py) so both stay consistent.
    """
    from music21 import interval, key

    spec = INSTRUMENTS[instrument]
    concert_key = key.KeySignature(concert_sharps).asKey("major")
    written_key = concert_key.transpose(interval.Interval(spec.transposition_semitones))
    return written_key.sharps
