"""Tests for the grand-staff notation path (core/notation.py's
build_score_from_doc / score_doc_to_json_model), which builds directly from
an imported ScoreDoc rather than the audio pipeline's flat single-part list.
"""

from music21 import layout

from sax2sheet.core.models import (
    KeySignatureChange,
    NoteEvent,
    PartInfo,
    ScoreDoc,
    TempoMark,
    TimeSignatureChange,
)
from sax2sheet.core.notation import build_score_from_doc, export_musicxml, score_doc_to_json_model
from sax2sheet.core.score_import import import_score_file


def _grand_staff_doc() -> ScoreDoc:
    return ScoreDoc(
        title="Round Trip Test",
        composer="Tester",
        parts=[PartInfo(part_id="part0", name="Piano", staves=2)],
        key_signatures=[KeySignatureChange(beat=0.0, sharps=2)],
        time_signatures=[TimeSignatureChange(beat=0.0, time_signature="3/4")],
        tempos=[TempoMark(beat=0.0, bpm=72.0)],
        measure_beats=[0.0, 3.0],
        notes=[
            NoteEvent(pitch_midi=72, onset_s=0.0, offset_s=0.5, beat=0.0, duration_beats=1.0,
                      part_id="part0", staff=1, hand="R", finger=1),
            # chord: two notes sharing a beat on the same staff
            NoteEvent(pitch_midi=48, onset_s=0.0, offset_s=2.5, beat=0.0, duration_beats=3.0,
                      part_id="part0", staff=2, hand="L"),
            NoteEvent(pitch_midi=55, onset_s=0.0, offset_s=2.5, beat=0.0, duration_beats=3.0,
                      part_id="part0", staff=2, hand="L"),
            NoteEvent(pitch_midi=74, onset_s=0.5, offset_s=1.5, beat=1.0, duration_beats=2.0,
                      part_id="part0", staff=1, hand="R"),
        ],
    )


def _single_staff_doc() -> ScoreDoc:
    return ScoreDoc(
        title="Sax Line",
        parts=[PartInfo(part_id="part0", name="Alto Sax", staves=1)],
        key_signatures=[KeySignatureChange(beat=0.0, sharps=0)],
        time_signatures=[TimeSignatureChange(beat=0.0, time_signature="4/4")],
        tempos=[TempoMark(beat=0.0, bpm=100.0)],
        notes=[
            NoteEvent(pitch_midi=69, onset_s=0.0, offset_s=1.0, beat=0.0, duration_beats=1.0,
                      part_id="part0", staff=1),
        ],
    )


def test_grand_staff_builds_two_parts_joined_by_staffgroup():
    doc = _grand_staff_doc()
    score = build_score_from_doc(doc)

    assert len(score.parts) == 2
    groups = list(score.getElementsByClass(layout.StaffGroup))
    assert len(groups) == 1
    assert len(list(groups[0].getSpannedElements())) == 2


def test_grand_staff_uses_treble_and_bass_clefs():
    doc = _grand_staff_doc()
    score = build_score_from_doc(doc)

    from music21 import clef
    treble_part, bass_part = score.parts[0], score.parts[1]
    assert isinstance(treble_part.flatten().getElementsByClass(clef.Clef).first(), clef.TrebleClef)
    assert isinstance(bass_part.flatten().getElementsByClass(clef.Clef).first(), clef.BassClef)


def test_single_staff_doc_builds_one_part_no_staffgroup():
    doc = _single_staff_doc()
    score = build_score_from_doc(doc)

    assert len(score.parts) == 1
    assert len(list(score.getElementsByClass(layout.StaffGroup))) == 0


def test_notes_sharing_a_beat_become_one_chord():
    doc = _grand_staff_doc()
    score = build_score_from_doc(doc)

    from music21 import chord
    bass_part = score.parts[1]
    chords = list(bass_part.flatten().getElementsByClass(chord.Chord))
    assert len(chords) == 1
    assert sorted(p.midi for p in chords[0].pitches) == [48, 55]


def test_full_round_trip_preserves_structure(tmp_path):
    """Build -> export MusicXML -> re-import (via score_import.py) ->
    everything that matters survives. This is the same round trip
    verification music21 was checked against during score_import.py's
    development, now exercised through notation.py's write side.
    """
    doc = _grand_staff_doc()
    score = build_score_from_doc(doc)

    out_path = tmp_path / "roundtrip.musicxml"
    export_musicxml(score, out_path)

    reimported = import_score_file(out_path)
    assert reimported.title == "Round Trip Test"
    assert reimported.parts[0].staves == 2

    treble = sorted((n.pitch_midi, n.beat, n.duration_beats) for n in reimported.notes if n.staff == 1)
    assert treble == [(72, 0.0, 1.0), (74, 1.0, 2.0)]

    bass = sorted((n.pitch_midi, n.beat, n.duration_beats) for n in reimported.notes if n.staff == 2)
    assert bass == [(48, 0.0, 3.0), (55, 0.0, 3.0)]

    fingered = next(n for n in reimported.notes if n.pitch_midi == 72)
    assert fingered.finger == 1
    assert all(n.finger is None for n in reimported.notes if n.pitch_midi != 72)


def test_score_doc_to_json_model_carries_staff_hand_finger():
    doc = _grand_staff_doc()
    model = score_doc_to_json_model(doc)

    assert model["title"] == "Round Trip Test"
    assert model["key_sharps"] == 2
    assert model["time_signature"] == "3/4"
    assert model["bpm"] == 72.0
    assert model["staves"] == 2

    fingered_note = next(n for n in model["notes"] if n["written_pitch_midi"] == 72)
    assert fingered_note["staff"] == 1
    assert fingered_note["hand"] == "R"
    assert fingered_note["finger"] == 1

    bass_notes = [n for n in model["notes"] if n["staff"] == 2]
    assert len(bass_notes) == 2
    assert all(n["hand"] == "L" for n in bass_notes)


def test_score_doc_to_json_model_single_staff():
    doc = _single_staff_doc()
    model = score_doc_to_json_model(doc)

    assert model["staves"] == 1
    assert all(n["staff"] == 1 for n in model["notes"])
    assert all(n["hand"] is None for n in model["notes"])


def test_deleted_notes_excluded_from_build_and_json_model():
    doc = _grand_staff_doc()
    doc.notes[0].deleted = True  # the fingered C5

    score = build_score_from_doc(doc)
    treble_part = score.parts[0]
    from music21 import note as m21note
    pitches = [n.pitch.midi for n in treble_part.flatten().notes if isinstance(n, m21note.Note)]
    assert 72 not in pitches

    model = score_doc_to_json_model(doc)
    assert 72 not in [n["written_pitch_midi"] for n in model["notes"]]


def test_empty_scoredoc_raises_for_build_but_not_json_model():
    empty = ScoreDoc()
    try:
        build_score_from_doc(empty)
        assert False, "expected ValueError"
    except ValueError:
        pass

    model = score_doc_to_json_model(empty)
    assert model["notes"] == []
