"""Builds a music21 Score from quantized, transposed notes and exports
MusicXML/MIDI. Also emits a simplified JSON score model that the browser's
VexFlow renderer consumes directly, so the frontend never parses MusicXML --
music21 handles the hard notation problems (splitting arbitrary durations
into tied/dotted notation, measure layout) once, on export.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from music21 import articulations, chord, clef, key, layout, meter, metadata, note, stream, tempo

from sax2sheet.core.models import NoteEvent, ScoreDoc

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


def build_score_from_doc(doc: ScoreDoc, part_id: str | None = None) -> stream.Score:
    """Builds a music21 Score directly from an imported ScoreDoc (see
    score_import.py), preserving its staff/hand/chord/fingering structure --
    unlike build_score() above (the audio pipeline's flat single-part
    builder), a grand-staff piano part here becomes two music21 Parts
    joined by a StaffGroup, matching the shape score_import.py parses FROM.

    `part_id` selects which instrument to render when a ScoreDoc has more
    than one (not yet produced by score_import.py, but the field exists on
    PartInfo/NoteEvent for when it is); defaults to the first part.
    """
    if not doc.parts:
        raise ValueError("ScoreDoc has no parts to render")
    target = next((p for p in doc.parts if p.part_id == part_id), doc.parts[0]) if part_id else doc.parts[0]

    time_sig = doc.time_signatures[0].time_signature if doc.time_signatures else "4/4"
    key_sharps = doc.key_signatures[0].sharps if doc.key_signatures else 0
    bpm = doc.tempos[0].bpm if doc.tempos else 120.0
    notes_for_part = [n for n in doc.notes if n.part_id == target.part_id and not n.deleted]

    score = stream.Score()
    if doc.title or doc.composer:
        score.metadata = metadata.Metadata()
        if doc.title:
            score.metadata.title = doc.title
        if doc.composer:
            score.metadata.composer = doc.composer

    if target.staves >= 2:
        staff_parts = []
        for staff_num in range(1, target.staves + 1):
            part = stream.Part()
            part.partName = target.name
            part.append(clef.TrebleClef() if staff_num == 1 else clef.BassClef())
            part.append(key.KeySignature(key_sharps))
            part.append(meter.TimeSignature(time_sig))
            if staff_num == 1:
                part.append(tempo.MetronomeMark(number=bpm))
            _insert_notes(part, [n for n in notes_for_part if n.staff == staff_num])
            score.insert(0, part)
            staff_parts.append(part)
        score.insert(0, layout.StaffGroup(staff_parts, name=target.name, symbol="brace"))
    else:
        part = stream.Part()
        part.partName = target.name
        part.append(clef.TrebleClef())
        part.append(key.KeySignature(key_sharps))
        part.append(meter.TimeSignature(time_sig))
        part.append(tempo.MetronomeMark(number=bpm))
        _insert_notes(part, notes_for_part)
        score.insert(0, part)

    return score


def _insert_notes(part: stream.Part, notes: list[NoteEvent]) -> None:
    """Groups notes sharing a beat into one chord (or a single note),
    attaching a fingering articulation when present.
    """
    by_beat: dict[float, list[NoteEvent]] = defaultdict(list)
    for n in notes:
        by_beat[n.beat or 0.0].append(n)

    for beat, group in sorted(by_beat.items()):
        duration_ql = max(MIN_QUARTER_LENGTH, group[0].duration_beats or MIN_QUARTER_LENGTH)
        if len(group) == 1:
            n = group[0]
            m21_el = note.Note(n.pitch_midi)
            if n.finger:
                m21_el.articulations.append(articulations.Fingering(n.finger))
        else:
            m21_el = chord.Chord([g.pitch_midi for g in group])
        m21_el.duration.quarterLength = duration_ql
        part.insert(beat, m21_el)


def score_doc_to_json_model(doc: ScoreDoc, part_id: str | None = None) -> dict:
    """Simplified representation of an imported score for the browser's
    grand-staff VexFlow renderer -- the ScoreDoc equivalent of
    score_to_json_model() above, carrying staff/hand/finger per note so the
    renderer knows which stave and hand each note belongs to.
    """
    if not doc.parts:
        return {"title": doc.title, "key_sharps": 0, "time_signature": "4/4", "bpm": 120.0, "staves": 1, "notes": []}
    target = next((p for p in doc.parts if p.part_id == part_id), doc.parts[0]) if part_id else doc.parts[0]

    notes_for_part = [n for n in doc.notes if n.part_id == target.part_id and not n.deleted]
    notes_out = [
        {
            "beat": n.beat,
            "duration_beats": n.duration_beats,
            "written_pitch_midi": n.pitch_midi,  # imported scores are already "written" -- no transposition step
            "staff": n.staff,
            "hand": n.hand,
            "finger": n.finger,
            "folded": False,
        }
        for n in sorted(notes_for_part, key=lambda n: (n.beat or 0.0, n.staff))
    ]
    return {
        "title": doc.title,
        "key_sharps": doc.key_signatures[0].sharps if doc.key_signatures else 0,
        "time_signature": doc.time_signatures[0].time_signature if doc.time_signatures else "4/4",
        "bpm": doc.tempos[0].bpm if doc.tempos else 120.0,
        "staves": target.staves,
        "notes": notes_out,
    }


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
