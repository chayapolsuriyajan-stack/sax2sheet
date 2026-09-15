"""Tests for core/score_import.py.

These lock in real, verified music21 parsing behavior (not assumptions):
grand-staff auto-splitting for single-part-with-staff-tags MusicXML,
StaffGroup-based hand assignment, tie merging via stripTies, fingering
extraction, and MIDI's track-based / pitch-threshold hand splitting.
"""

from music21 import chord, clef, key, meter, metadata, note, stream, tempo

from sax2sheet.core.models import ScoreDoc
from sax2sheet.core.score_import import import_score_file, import_score_upload

# -- fixtures --------------------------------------------------------------


def _write_grand_staff_musicxml(path):
    """A single MusicXML <part> with per-note <staff> tags -- the common
    MuseScore/Finale/Sibelius export style for piano, which music21 auto-
    splits into PartStaff objects joined by a StaffGroup on parse.
    """
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <work><work-title>Test Grand Staff</work-title></work>
  <identification><creator type="composer">Test Composer</creator></identification>
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <staves>2</staves>
        <clef number="1"><sign>G</sign><line>2</line></clef>
        <clef number="2"><sign>F</sign><line>4</line></clef>
      </attributes>
      <note>
        <pitch><step>C</step><octave>5</octave></pitch>
        <duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff>
        <notations><technical><fingering>1</fingering></technical></notations>
      </note>
      <note>
        <pitch><step>D</step><octave>5</octave></pitch>
        <duration>1</duration><voice>1</voice><type>quarter</type>
        <tie type="start"/><staff>1</staff>
        <notations><tied type="start"/></notations>
      </note>
      <note>
        <pitch><step>D</step><octave>5</octave></pitch>
        <duration>1</duration><voice>1</voice><type>quarter</type>
        <tie type="stop"/><staff>1</staff>
        <notations><tied type="stop"/></notations>
      </note>
      <note>
        <pitch><step>E</step><octave>5</octave></pitch>
        <duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff>
      </note>
      <backup><duration>4</duration></backup>
      <note>
        <pitch><step>C</step><octave>3</octave></pitch>
        <duration>4</duration><voice>2</voice><type>whole</type><staff>2</staff>
      </note>
    </measure>
  </part>
</score-partwise>
"""
    path.write_text(xml)
    return path


def _write_sax_musicxml(path):
    sc = stream.Score()
    sc.metadata = metadata.Metadata()
    p = stream.Part(id="P1")
    p.partName = "Alto Sax"
    p.append(clef.TrebleClef())
    p.append(key.KeySignature(0))
    p.append(meter.TimeSignature("4/4"))
    p.append(note.Note("A4", quarterLength=1.0))
    p.append(chord.Chord(["C4", "E4", "G4"], quarterLength=1.0))
    sc.insert(0, p)
    sc.write("musicxml", fp=str(path))
    return path


def _write_two_track_midi(path):
    sc = stream.Score()
    rh = stream.Part()
    rh.append(meter.TimeSignature("4/4"))
    rh.append(tempo.MetronomeMark(number=90))
    rh.append(note.Note("C5", quarterLength=1.0))
    rh.append(note.Note("D5", quarterLength=1.0))
    lh = stream.Part()
    lh.append(note.Note("C3", quarterLength=2.0))
    sc.insert(0, rh)
    sc.insert(0, lh)
    sc.write("midi", fp=str(path))
    return path


def _write_single_track_midi(path):
    p = stream.Part()
    p.append(meter.TimeSignature("4/4"))
    p.append(tempo.MetronomeMark(number=90))
    p.append(note.Note("C5", quarterLength=1.0))  # 72, above default threshold
    p.append(note.Note("C3", quarterLength=1.0))  # 48, below default threshold
    p.write("midi", fp=str(path))
    return path


# -- tests -------------------------------------------------------------


def test_grand_staff_musicxml_splits_into_two_staves(tmp_path):
    path = _write_grand_staff_musicxml(tmp_path / "piano.musicxml")
    doc = import_score_file(path)

    assert doc.title == "Test Grand Staff"
    assert doc.composer == "Test Composer"
    assert len(doc.parts) == 1
    assert doc.parts[0].staves == 2

    staff1_notes = [n for n in doc.notes if n.staff == 1]
    staff2_notes = [n for n in doc.notes if n.staff == 2]
    assert all(n.hand == "R" for n in staff1_notes)
    assert all(n.hand == "L" for n in staff2_notes)


def test_tied_notes_merge_into_one_sounding_note(tmp_path):
    path = _write_grand_staff_musicxml(tmp_path / "piano.musicxml")
    doc = import_score_file(path)

    # The tied D5-D5 pair (two quarter notes) should merge into a single
    # NoteEvent with combined duration, not appear as two separate notes.
    d5_notes = [n for n in doc.notes if n.pitch_midi == 74]
    assert len(d5_notes) == 1
    assert d5_notes[0].duration_beats == 2.0


def test_fingering_extracted_from_musicxml(tmp_path):
    path = _write_grand_staff_musicxml(tmp_path / "piano.musicxml")
    doc = import_score_file(path)

    c5_note = next(n for n in doc.notes if n.pitch_midi == 72)
    assert c5_note.finger == 1
    # Notes without a <fingering> stay None, not some other falsy sentinel.
    other_notes = [n for n in doc.notes if n.pitch_midi != 72]
    assert all(n.finger is None for n in other_notes)


def test_single_staff_instrument_has_no_hand_assignment(tmp_path):
    path = _write_sax_musicxml(tmp_path / "sax.musicxml")
    doc = import_score_file(path)

    assert len(doc.parts) == 1
    assert doc.parts[0].staves == 1
    assert all(n.staff == 1 for n in doc.notes)
    assert all(n.hand is None for n in doc.notes)


def test_chord_produces_one_note_event_per_pitch(tmp_path):
    path = _write_sax_musicxml(tmp_path / "sax.musicxml")
    doc = import_score_file(path)

    chord_notes = [n for n in doc.notes if n.beat == 1.0]
    assert sorted(n.pitch_midi for n in chord_notes) == [60, 64, 67]
    assert all(n.duration_beats == 1.0 for n in chord_notes)


def test_two_track_midi_splits_into_grand_staff_by_track_order(tmp_path):
    path = _write_two_track_midi(tmp_path / "piano.mid")
    doc = import_score_file(path)

    assert len(doc.parts) == 1
    assert doc.parts[0].staves == 2
    rh_pitches = sorted(n.pitch_midi for n in doc.notes if n.staff == 1)
    lh_pitches = sorted(n.pitch_midi for n in doc.notes if n.staff == 2)
    assert rh_pitches == [72, 74]
    assert lh_pitches == [48]
    assert all(n.hand == "R" for n in doc.notes if n.staff == 1)
    assert all(n.hand == "L" for n in doc.notes if n.staff == 2)


def test_single_track_midi_splits_by_pitch_threshold(tmp_path):
    path = _write_single_track_midi(tmp_path / "solo.mid")
    doc = import_score_file(path, midi_hand_split_pitch=60)

    above = next(n for n in doc.notes if n.pitch_midi == 72)
    below = next(n for n in doc.notes if n.pitch_midi == 48)
    assert above.staff == 1 and above.hand == "R"
    assert below.staff == 2 and below.hand == "L"


def test_single_track_midi_custom_threshold(tmp_path):
    path = _write_single_track_midi(tmp_path / "solo.mid")
    # Threshold above both notes' pitches -> everything is "L".
    doc = import_score_file(path, midi_hand_split_pitch=100)
    assert all(n.hand == "L" for n in doc.notes)


def test_tempo_mark_is_read_from_midi(tmp_path):
    path = _write_two_track_midi(tmp_path / "piano.mid")
    doc = import_score_file(path)
    assert doc.tempos[0].bpm == 90.0


def test_missing_tempo_defaults_to_120bpm(tmp_path):
    path = _write_sax_musicxml(tmp_path / "sax.musicxml")
    doc = import_score_file(path)
    assert doc.tempos[0].bpm == 120.0


def test_onset_seconds_computed_from_tempo(tmp_path):
    # 90 BPM -> 60/90 = 0.6667s per quarter note.
    path = _write_two_track_midi(tmp_path / "piano.mid")
    doc = import_score_file(path)
    second_rh_note = next(n for n in doc.notes if n.pitch_midi == 74)
    assert second_rh_note.beat == 1.0
    assert abs(second_rh_note.onset_s - (60.0 / 90.0)) < 1e-6


def test_key_signature_sharps_extracted(tmp_path):
    path = _write_grand_staff_musicxml(tmp_path / "piano.musicxml")
    doc = import_score_file(path)
    assert doc.key_signatures[0].sharps == 0


def test_time_signature_extracted(tmp_path):
    path = _write_grand_staff_musicxml(tmp_path / "piano.musicxml")
    doc = import_score_file(path)
    assert doc.time_signatures[0].time_signature == "4/4"


def test_upload_pipeline_preserves_midi_grand_staff_heuristic(tmp_path, monkeypatch):
    """Regression test: an earlier version of import_score_upload derived
    the ScoreDoc by re-parsing the *written-back-out* MusicXML rather than
    the original MIDI, which silently lost the "two ungrouped MIDI tracks =
    grand staff" heuristic (the written file has a .musicxml extension, so
    is_midi was false on the second parse). This must go through the full
    upload -> Project -> score.json pipeline, not just import_score_file(),
    to catch that class of bug.
    """
    from sax2sheet.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")

    midi_path = _write_two_track_midi(tmp_path / "piano.mid")
    project = import_score_upload(midi_path, source_label="piano.mid")

    manifest = project.load_manifest()
    assert manifest.source_kind == "score"
    assert manifest.stages["imported"] is True
    assert project.source_musicxml.exists()
    assert project.score_json.exists()

    doc = ScoreDoc.from_json(project.score_json.read_text())
    assert len(doc.parts) == 1
    assert doc.parts[0].staves == 2  # not 2 separate single-staff parts
    assert sorted(n.pitch_midi for n in doc.notes if n.staff == 1) == [72, 74]
    assert sorted(n.pitch_midi for n in doc.notes if n.staff == 2) == [48]


def test_scoredoc_json_round_trip(tmp_path):
    path = _write_grand_staff_musicxml(tmp_path / "piano.musicxml")
    doc = import_score_file(path)

    restored = ScoreDoc.from_json(doc.to_json())

    assert restored.title == doc.title
    assert restored.composer == doc.composer
    assert restored.parts == doc.parts
    assert restored.key_signatures == doc.key_signatures
    assert restored.time_signatures == doc.time_signatures
    assert restored.tempos == doc.tempos
    assert restored.measure_beats == doc.measure_beats
    assert restored.notes == doc.notes


def test_unsupported_file_type_rejected(tmp_path, monkeypatch):
    from sax2sheet.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")

    bogus = tmp_path / "score.pdf"
    bogus.write_bytes(b"not a score")

    try:
        import_score_upload(bogus, source_label="score.pdf")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "unsupported" in str(e)


def test_mxl_compressed_musicxml_imports(tmp_path):
    import zipfile

    inner = tmp_path / "inner.musicxml"
    _write_grand_staff_musicxml(inner)
    mxl_path = tmp_path / "piece.mxl"
    with zipfile.ZipFile(mxl_path, "w") as z:
        z.write(inner, arcname="score.musicxml")
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container><rootfiles>'
            '<rootfile full-path="score.musicxml"/></rootfiles></container>',
        )

    doc = import_score_file(mxl_path)
    assert doc.title == "Test Grand Staff"
    assert len(doc.notes) == 4
