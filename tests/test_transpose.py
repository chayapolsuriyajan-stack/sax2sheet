from sax2sheet.core.models import Instrument, NoteEvent
from sax2sheet.core.transpose import transpose_key_signature, transpose_notes


def _note(pitch_midi, onset=0.0, offset=1.0):
    return NoteEvent(id="n0", pitch_midi=pitch_midi, onset_s=onset, offset_s=offset)


def test_concert_c4_to_alto_written_a4():
    # Concert C4 (60) -> alto (+9) -> written A4 (69)
    out = transpose_notes([_note(60)], Instrument.ALTO)
    assert out[0].written_pitch_midi == 69
    assert out[0].folded is False


def test_concert_c4_to_tenor_written_d5():
    # Concert C4 (60) -> tenor (+14) -> written D5 (74)
    out = transpose_notes([_note(60)], Instrument.TENOR)
    assert out[0].written_pitch_midi == 74
    assert out[0].folded is False


def test_bass_line_below_range_folds_up_and_flags():
    # Concert E2 (40) -> alto (+9) = 49, below written low (Bb3 = 58) -> folds
    out = transpose_notes([_note(40)], Instrument.ALTO)
    assert out[0].folded is True
    assert out[0].folded_octaves > 0
    assert 58 <= out[0].written_pitch_midi <= 90


def test_high_note_above_range_folds_down_and_flags():
    # Concert C7 (96) -> alto (+9) = 105, above written high (F#6 = 90) -> folds
    out = transpose_notes([_note(96)], Instrument.ALTO)
    assert out[0].folded is True
    assert out[0].folded_octaves < 0
    assert 58 <= out[0].written_pitch_midi <= 90


def test_global_octave_shift_applies_before_folding():
    out_no_shift = transpose_notes([_note(60)], Instrument.ALTO, global_octave_shift=0)
    out_shifted = transpose_notes([_note(60)], Instrument.ALTO, global_octave_shift=1)
    assert out_shifted[0].written_pitch_midi == out_no_shift[0].written_pitch_midi + 12


def test_transpose_never_mutates_input():
    notes = [_note(60)]
    transpose_notes(notes, Instrument.ALTO)
    assert notes[0].written_pitch_midi is None


def test_key_signature_concert_c_major_to_alto_a_major():
    # Alto sax written key for concert C major is A major (3 sharps)
    assert transpose_key_signature(0, Instrument.ALTO) == 3


def test_key_signature_concert_c_major_to_tenor_d_major():
    # Tenor sax written key for concert C major is D major (2 sharps)
    assert transpose_key_signature(0, Instrument.TENOR) == 2


def test_key_signature_concert_c_major_to_soprano_d_major():
    assert transpose_key_signature(0, Instrument.SOPRANO) == 2


def test_key_signature_concert_c_major_to_baritone_a_major():
    assert transpose_key_signature(0, Instrument.BARITONE) == 3
