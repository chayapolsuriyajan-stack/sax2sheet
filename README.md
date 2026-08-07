# sax2sheet

Local tool that turns audio (YouTube link, media URL, or uploaded file) into
saxophone-readable sheet music: transcribe, verify in a piano roll, transpose
for alto/tenor/soprano/baritone, and export PDF / MIDI / MusicXML.

See [`docs/` / plan] for the full architecture. This README covers day-to-day
setup and running.

## Setup

Requires Python 3.10 and [`uv`](https://github.com/astral-sh/uv) (Basic
Pitch's ONNX backend, which avoids a TensorFlow install, only activates on
Windows for Python <3.11). ffmpeg must be on PATH (used for audio
normalization and YouTube post-processing).

```bash
uv sync
```

To enable Demucs-based stem separation (optional, heavy — pulls in torch):

```bash
uv sync --extra separate
```

If a CUDA GPU is available, the "Use GPU" checkbox next to the Separate
button (auto-detected via `torch.cuda.is_available()`) runs separation on it
instead of CPU — a multi-minute CPU separation drops to seconds. No extra
setup beyond a CUDA-enabled torch install; the checkbox is disabled
automatically when no GPU is visible.

## Run

```bash
uv run uvicorn sax2sheet.api.main:app --reload
```

Then open http://127.0.0.1:8000.

## Test

```bash
uv run pytest
```

## Project data

Everything derived from an input (normalized audio, separated stems, raw
transcription, edits, exports) lives under `data/projects/<id>/`, gitignored.
The id is a content hash of the normalized source audio, so re-loading the
same song reuses its cached folder instead of reprocessing.

## Status

All five build phases are implemented and verified end-to-end:

1. **Ingest & transcription** -- YouTube/URL/upload -> normalized audio ->
   content-hashed project -> Basic Pitch (ONNX) note events.
2. **Piano-roll editing & playback** -- select/delete/move/resize notes,
   box-select, confidence filter, undo; alto/tenor/soprano/baritone sampled
   playback (Soundfont-player, FluidR3_GM).
3. **Analysis, quantization & transposition** -- librosa tempo/key estimate;
   grid/swing quantization; Bb/Eb transposition with octave-fold + flag for
   out-of-range notes; unit-tested (`tests/test_quantize.py`,
   `tests/test_transpose.py`).
4. **Notation & export** -- music21-built score; MusicXML/MIDI export;
   VexFlow staff preview; client-side SVG -> PDF (jsPDF + svg2pdf.js), so the
   exported PDF is exactly the SVG shown on screen.
5. **Stem separation** -- optional Demucs stage (`--extra separate`), stem
   caching, in-browser stem audition and re-transcription without
   re-separating, with an optional GPU device for the separation pass.

Sax sample playback (sections 3-4) uses vendored local sample files
(`web/vendor/soundfonts/`) rather than a CDN, so it works without live
internet access -- consistent with this being a local tool. Rendering the
staff preview (section 5) is instant and purely client-side; MusicXML/MIDI
generation via music21 (the slow step) only runs when you actually click a
download link, not on every staff render.

### Known limitations

- Demucs is not instrument-aware -- sax lands in the "other" stem alongside
  any other melodic instruments the model doesn't have a dedicated stem for.
- The transcription frequency gate (config.py `minimum_frequency_hz`,
  default 80Hz) will filter out very low source material (e.g. a bass line
  below ~E2) even with separation on -- lower it if you're deliberately
  transcribing a bass part to arrange upward.
- The VexFlow staff preview rounds arbitrary durations to the nearest
  standard note value and doesn't tie notes across barlines or render
  triplet-grid quantization exactly; the exported MusicXML/MIDI are built
  independently by music21 and are not subject to this approximation.
- On Windows, recent `torchaudio` releases require an optional `torchcodec`
  dependency for `torchaudio.save()` that Demucs itself doesn't declare --
  and torchcodec's prebuilt wheels fail to load their native library on this
  platform. `core/separate.py` avoids the whole chain by calling Demucs's
  model directly and writing stems with `soundfile` instead.
