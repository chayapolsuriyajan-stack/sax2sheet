from sax2sheet.core.models import NoteEvent, QuantizeSettings
from sax2sheet.core.quantize import MIN_DURATION_BEATS, quantize_notes


def _note(onset, offset):
    return NoteEvent(id="n0", pitch_midi=60, onset_s=onset, offset_s=offset)


def test_120bpm_16th_grid_maps_onset_to_exact_beat():
    # 120 BPM = 2 beats/sec. A note starting exactly on beat 2 (1.0s) lands
    # on beat 2.0 with no rounding drift.
    settings = QuantizeSettings(bpm=120.0, grid="16th")
    out = quantize_notes([_note(1.0, 1.5)], settings)
    assert out[0].beat == 2.0


def test_short_note_does_not_collapse_to_zero_duration():
    settings = QuantizeSettings(bpm=120.0, grid="16th")
    # onset and offset both snap to the same grid point.
    out = quantize_notes([_note(0.0, 0.01)], settings)
    assert out[0].duration_beats == MIN_DURATION_BEATS
    assert out[0].duration_beats > 0


def test_snaps_to_nearest_grid_point():
    # 120 BPM, 8th-note grid (0.5 beat units = 0.25s units). An onset of
    # 0.26s (0.52 beats) should snap to the nearest 0.5-beat grid point (0.5).
    settings = QuantizeSettings(bpm=120.0, grid="8th")
    out = quantize_notes([_note(0.26, 0.76)], settings)
    assert out[0].beat == 0.5


def test_swing_delays_offbeat_eighth_notes():
    # Straight grid: onset at 0.25s -> beat 0.5 (the "and" of beat 1).
    # With swing=0.667, that off-beat should move to beat 0.667.
    straight = QuantizeSettings(bpm=120.0, grid="8th", swing=0.0)
    swung = QuantizeSettings(bpm=120.0, grid="8th", swing=0.667)

    out_straight = quantize_notes([_note(0.25, 0.5)], straight)
    out_swung = quantize_notes([_note(0.25, 0.5)], swung)

    assert out_straight[0].beat == 0.5
    assert out_swung[0].beat == 0.667


def test_quantize_never_mutates_input():
    notes = [_note(1.0, 1.5)]
    quantize_notes(notes, QuantizeSettings(bpm=120.0, grid="16th"))
    assert notes[0].beat is None
