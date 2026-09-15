"""Imports a score (MusicXML/MXL/MIDI) into a ScoreDoc.

All three import sources in the plan (file upload, OMR output, library
download) converge here: whatever the file is, it becomes a music21 Score,
and this module is the only place that interprets score semantics --
notation.py and the tutorial consume ScoreDoc/NoteEvent, never music21
objects directly. OMR (core/omr.py) and the library providers
(core/score_library.py) both produce a MusicXML file and hand it to
import_score_upload() just like a direct upload.

Imported scores bypass quantize.py/transpose.py entirely: they're already
notated and already in the right rhythm, so re-quantizing would damage them.

Key behaviors, verified against real music21 parsing (not assumed):
  - A single MusicXML <part> with per-note <staff> tags (the common
    MuseScore/Finale/Sibelius export for piano) is auto-split by music21
    into PartStaff objects joined by a StaffGroup -- confirmed via a
    hand-built two-staff test file.
  - Tied notes are merged into one sounding NoteEvent via Stream.stripTies(),
    not manual tie-state tracking.
  - <notations><technical><fingering> lands on Note.articulations as an
    articulations.Fingering with .fingerNumber.
  - MIDI has no staff/StaffGroup concept: two-track MIDI is treated as a
    grand-staff pair by track order (RH convention first); single-track
    MIDI has no track info to split by, so hand is assigned by a pitch
    threshold instead (see `midi_hand_split_pitch`).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from music21 import articulations, chord, converter
from music21 import key as m21key
from music21 import layout
from music21 import meter as m21meter
from music21 import note as m21note
from music21 import tempo as m21tempo

from sax2sheet.core.models import (
    KeySignatureChange,
    NoteEvent,
    PartInfo,
    ScoreDoc,
    TempoMark,
    TimeSignatureChange,
)
from sax2sheet.core.storage import Project, get_or_create_project

DEFAULT_HAND_SPLIT_PITCH = 60  # middle C
DEFAULT_BPM = 120.0
MIDI_SUFFIXES = {".mid", ".midi"}
SUPPORTED_SCORE_SUFFIXES = {".musicxml", ".xml", ".mxl", ".mid", ".midi"}


def import_score_upload(
    upload_path: Path,
    source_label: str,
    midi_hand_split_pitch: int = DEFAULT_HAND_SPLIT_PITCH,
) -> Project:
    """Top-level entry point for score import (file upload today; OMR and
    library-download output both produce a MusicXML file that can go
    through this same function). Mirrors ingest.py's
    ingest_upload()/ingest_url() pattern: normalize -> get_or_create_project
    -> return the Project, with the parsed ScoreDoc persisted alongside it.

    Parses `upload_path` exactly once. Both the canonical `source.musicxml`
    and the returned ScoreDoc are derived from that single parse -- doing
    this as parse-then-write-then-*reparse* (an earlier version of this
    function did) loses MIDI's file-extension-based heuristics, since the
    written-back-out MusicXML no longer looks like MIDI to a second parse.
    """
    suffix = upload_path.suffix.lower()
    if suffix not in SUPPORTED_SCORE_SUFFIXES:
        raise ValueError(
            f"unsupported score file type: {suffix!r} "
            f"(supported: {', '.join(sorted(SUPPORTED_SCORE_SUFFIXES))})"
        )

    score = converter.parse(str(upload_path))
    is_midi = suffix in MIDI_SUFFIXES
    doc = _score_to_doc(score, is_midi=is_midi, midi_hand_split_pitch=midi_hand_split_pitch)

    fd, tmp_name = tempfile.mkstemp(suffix=".musicxml")
    os.close(fd)
    normalized_path = Path(tmp_name)
    score.write("musicxml", fp=str(normalized_path))

    project = get_or_create_project(normalized_path, source_label=source_label, source_kind="score")
    project.score_json.write_text(doc.to_json())
    return project


def import_score_file(path: Path, midi_hand_split_pitch: int = DEFAULT_HAND_SPLIT_PITCH) -> ScoreDoc:
    """Parse a MusicXML/MXL/MIDI file into a ScoreDoc.

    `midi_hand_split_pitch` only matters for single-track MIDI with no
    per-track or per-staff structure to split by: notes at or above this
    MIDI pitch are assigned staff 1/hand "R", below it staff 2/hand "L".
    Exposed as a parameter (not hardcoded) since the right split point
    depends on the piece.

    NOTE: if you already have a parsed music21 Score (e.g. you're about to
    write it back out too, as import_score_upload does), use
    `_score_to_doc()` directly on that object instead of calling this a
    second time on a re-derived file -- MIDI's is_midi-dependent heuristics
    (see module docstring) only fire correctly against the *original* file;
    a MusicXML file written back out from parsed MIDI looks like MusicXML,
    not MIDI, to a second parse.
    """
    score = converter.parse(str(path))
    is_midi = path.suffix.lower() in MIDI_SUFFIXES
    return _score_to_doc(score, is_midi=is_midi, midi_hand_split_pitch=midi_hand_split_pitch)


def _score_to_doc(score, is_midi: bool, midi_hand_split_pitch: int) -> ScoreDoc:
    doc = ScoreDoc(title=_meta(score, "title"), composer=_meta(score, "composer"))

    groups = _resolve_groups(score, is_midi=is_midi)
    for part_id, part_name, staff_members in groups:
        doc.parts.append(PartInfo(part_id=part_id, name=part_name, staves=len(staff_members)))
        for staff_num, hand, part_stream in staff_members:
            doc.notes.extend(_notes_from_part(part_stream, part_id, staff_num, hand))

    if is_midi and len(score.parts) <= 1:
        # No track/staff structure at all to derive hands from -- split by
        # pitch threshold purely for hand-assignment metadata. Notes stay
        # together as one logical part.
        for n in doc.notes:
            above = n.pitch_midi >= midi_hand_split_pitch
            n.staff = 1 if above else 2
            n.hand = "R" if above else "L"

    ref_stream = score.parts[0] if score.parts else score
    doc.key_signatures = _extract_key_signatures(ref_stream)
    doc.time_signatures = _extract_time_signatures(ref_stream)
    doc.tempos = _extract_tempos(ref_stream)
    doc.measure_beats = _extract_measure_beats(ref_stream)

    # Imported scores have no audio timeline; onset_s/offset_s are a
    # reasonable default rendering from the piece's own tempo map so the
    # existing audio-domain fields (duration_s, playback preview) aren't
    # nonsensically zero. The tutorial's real-time transport clock (a later
    # workstream) is the authoritative scheduler and can rescale live.
    for n in doc.notes:
        n.onset_s = _beats_to_seconds(n.beat or 0.0, doc.tempos)
        n.offset_s = _beats_to_seconds((n.beat or 0.0) + (n.duration_beats or 0.0), doc.tempos)

    doc.notes.sort(key=lambda n: (n.beat if n.beat is not None else 0.0, n.staff, n.pitch_midi))
    return doc


def _meta(score, field: str) -> str:
    md = score.metadata
    if md is None:
        return ""
    if field == "title":
        # music21's parser splits <work-title> into .movementName (not
        # .title) whenever a file also has a <movement-title> tag -- which
        # music21's own writer always emits alongside <work-title>. Verified
        # empirically: .title is None in that case even though a title is
        # clearly present. .bestTitle resolves correctly regardless of which
        # tag(s) the source file actually has.
        return md.bestTitle or ""
    return getattr(md, field, None) or ""


def _resolve_groups(score, is_midi: bool) -> list[tuple[str, str, list[tuple[int, str | None, object]]]]:
    """Returns one entry per logical instrument:
    (part_id, part_name, [(staff_num, hand, part_stream), ...]).

    A grand-staff piano is one entry with two staff members. A single-staff
    instrument (sax, guitar, a MIDI track with no pair) is one entry with
    one staff member and hand=None (not applicable outside a paired staff).
    """
    groups: list[tuple[str, str, list[tuple[int, str | None, object]]]] = []
    grouped_part_ids = set()

    for sg in score.getElementsByClass(layout.StaffGroup):
        members = list(sg.getSpannedElements())
        if len(members) < 2:
            continue
        part_id = f"part{len(groups)}"
        name = sg.name or getattr(members[0], "partName", None) or "Instrument"
        staff_members = [
            (i + 1, "R" if i == 0 else "L", member) for i, member in enumerate(members)
        ]
        groups.append((part_id, name, staff_members))
        grouped_part_ids.update(id(m) for m in members)

    remaining = [p for p in score.parts if id(p) not in grouped_part_ids]

    if is_midi and len(remaining) == 2:
        # No StaffGroup in MIDI, but exactly two ungrouped tracks -- treat
        # as a grand-staff pair by track order (RH track first is the
        # common convention for piano MIDI exports).
        part_id = f"part{len(groups)}"
        groups.append((part_id, "Piano", [(1, "R", remaining[0]), (2, "L", remaining[1])]))
        remaining = []

    for p in remaining:
        part_id = f"part{len(groups)}"
        name = getattr(p, "partName", None) or f"Part {len(groups) + 1}"
        groups.append((part_id, name, [(1, None, p)]))

    return groups


def _notes_from_part(part_stream, part_id: str, staff_num: int, hand: str | None) -> list[NoteEvent]:
    stripped = part_stream.stripTies(inPlace=False)
    flat = stripped.flatten()
    out: list[NoteEvent] = []

    for el in flat.notesAndRests:
        if isinstance(el, m21note.Rest):
            continue
        pitches = el.pitches if isinstance(el, chord.Chord) else [el.pitch]
        fingers = [a.fingerNumber for a in el.articulations if isinstance(a, articulations.Fingering)]
        finger = fingers[0] if fingers else None
        voice_ctx = el.getContextByClass("Voice")
        voice_num = int(voice_ctx.id) if voice_ctx is not None and str(voice_ctx.id).isdigit() else 1

        for pitch in pitches:
            out.append(NoteEvent(
                pitch_midi=pitch.midi,
                onset_s=0.0,   # filled in by _score_to_doc() from the tempo map
                offset_s=0.0,
                beat=float(el.offset),
                duration_beats=float(el.quarterLength),
                part_id=part_id,
                staff=staff_num,
                voice=voice_num,
                hand=hand,
                finger=finger,
            ))
    return out


def _extract_key_signatures(ref_stream) -> list[KeySignatureChange]:
    out = [
        KeySignatureChange(beat=float(ks.offset), sharps=int(ks.sharps))
        for ks in ref_stream.flatten().getElementsByClass(m21key.KeySignature)
    ]
    return sorted(out, key=lambda k: k.beat) or [KeySignatureChange(beat=0.0, sharps=0)]


def _extract_time_signatures(ref_stream) -> list[TimeSignatureChange]:
    out = [
        TimeSignatureChange(beat=float(ts.offset), time_signature=ts.ratioString)
        for ts in ref_stream.flatten().getElementsByClass(m21meter.TimeSignature)
    ]
    return sorted(out, key=lambda t: t.beat) or [TimeSignatureChange(beat=0.0, time_signature="4/4")]


def _extract_tempos(ref_stream) -> list[TempoMark]:
    out = [
        TempoMark(beat=float(mm.offset), bpm=float(mm.number))
        for mm in ref_stream.flatten().getElementsByClass(m21tempo.MetronomeMark)
        if mm.number is not None
    ]
    return sorted(out, key=lambda t: t.beat) or [TempoMark(beat=0.0, bpm=DEFAULT_BPM)]


def _extract_measure_beats(ref_stream) -> list[float]:
    measures = ref_stream.getElementsByClass("Measure")
    return [float(m.offset) for m in measures] or [0.0]


def _beats_to_seconds(beat: float, tempos: list[TempoMark]) -> float:
    """Converts a beat offset to seconds via a piecewise-constant tempo map
    (tempo marks sorted ascending by beat, each applying from its beat
    onward). A reasonable default rendering, not a real-time scheduler --
    see the module docstring.
    """
    if not tempos:
        return beat * 60.0 / DEFAULT_BPM

    seconds = 0.0
    prev_beat = 0.0
    prev_bpm = tempos[0].bpm
    for tm in tempos:
        if tm.beat >= beat:
            break
        seconds += (tm.beat - prev_beat) * 60.0 / prev_bpm
        prev_beat = tm.beat
        prev_bpm = tm.bpm
    seconds += (beat - prev_beat) * 60.0 / prev_bpm
    return seconds
