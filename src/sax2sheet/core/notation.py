"""Builds a music21 Score from quantized, transposed notes and exports
MusicXML/MIDI. Also emits a simplified JSON score model that the browser's
VexFlow renderer consumes directly, so the frontend never parses MusicXML --
music21 handles the hard notation problems (splitting arbitrary durations
into tied/dotted notation, measure layout) once, on export.
"""

from __future__ import annotations

from pathlib import Path

from music21 import clef, key, meter, note, stream, tempo

from sax2sheet.core.models import NoteEvent

MIN_QUARTER_LENGTH = 0.0625  # a 64th note; matches quantize.MIN_DURATION_BEATS


def build_score(
    notes: list[NoteEvent],
    written_key_sharps: int,
    bpm: float,
    time_signature: str = "4/4",
    instrument_name: str = "Alto Saxophone",
) -> stream.Score:
    """Build a single-part Score from written, quantized notes.

    Notes must already carry `written_pitch_midi`, `beat` (quarter-note
    offset from the start), and `duration_beats` (quarterLength) -- i.e. the
    output of transpose_notes(quantize_notes(...)). Deleted notes are
    skipped.
    """
    part = stream.Part()
    part.partName = instrument_name
    part.append(clef.TrebleClef())
    part.append(key.KeySignature(written_key_sharps))
    part.append(meter.TimeSignature(time_signature))
    part.append(tempo.MetronomeMark(number=bpm))

    playable = [n for n in notes if not n.deleted and n.written_pitch_midi is not None
                and n.beat is not None and n.duration_beats is not None]
    for n in sorted(playable, key=lambda n: n.beat):
        m21_note = note.Note(n.written_pitch_midi)
        m21_note.duration.quarterLength = max(MIN_QUARTER_LENGTH, n.duration_beats)
        part.insert(n.beat, m21_note)

    # makeNotation (run implicitly on write) splits arbitrary durations into
    # properly tied/dotted notation and lays out measures according to the
    # time signature -- this is what lets quantize.py hand out raw
    # quarterLengths without worrying about notation legality.
    score = stream.Score()
    score.append(part)
    return score


def export_musicxml(score: stream.Score, path: Path) -> None:
    score.write("musicxml", fp=str(path))


def export_midi(score: stream.Score, path: Path) -> None:
    score.write("midi", fp=str(path))


def score_to_json_model(notes: list[NoteEvent], key_sharps: int, bpm: float, time_signature: str) -> dict:
    """Simplified representation for the browser's VexFlow renderer: a flat
    list of played notes plus the key/time signature and tempo. VexFlow does
    its own layout (including measure splitting and duration rounding) from
    this; see web/js/staff.js.
    """
    playable = [n for n in notes if not n.deleted and n.written_pitch_midi is not None
                and n.beat is not None and n.duration_beats is not None]
    notes_out = [
        {
            "beat": n.beat,
            "duration_beats": n.duration_beats,
            "written_pitch_midi": n.written_pitch_midi,
            "folded": n.folded,
        }
        for n in sorted(playable, key=lambda n: n.beat)
    ]
    return {
        "key_sharps": key_sharps,
        "time_signature": time_signature,
        "bpm": bpm,
        "notes": notes_out,
    }
