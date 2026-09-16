# sax2sheet

Local tool that turns audio (YouTube link, media URL, or uploaded file) into
readable sheet music: transcribe, verify in a piano roll, arrange for
alto/tenor/soprano/baritone sax, guitar, or piano, and export PDF / MIDI /
MusicXML.

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

If you have a CUDA GPU, install the `separate-gpu` extra instead of
`separate` — PyPI's default `torch` wheel is CPU-only on Windows, so the
plain `separate` extra will not use your GPU even if one is present:

```bash
uv sync --extra separate-gpu
```

This resolves `torch` from PyTorch's CUDA wheel index (`cu130`, for
CUDA 13.0-class drivers e.g. RTX 50-series/Blackwell) instead of PyPI's
CPU-only default — see `[tool.uv.sources]` / `[[tool.uv.index]]` in
`pyproject.toml`. If your driver needs a different CUDA version, change the
index there (available indices: https://download.pytorch.org/whl/torch/).
The "Use GPU" checkbox next to the Separate button is auto-disabled unless
`torch.cuda.is_available()` reports a usable GPU — a multi-minute CPU
separation drops to seconds on GPU.

## Run

```bash
uv run uvicorn sax2sheet.api.main:app --reload
```

Then open http://127.0.0.1:8000.

**Or just double-click `run.bat`** (or the `sax2sheet.lnk` shortcut, which
points at it) — it starts the server in its own window and opens the app in
your default browser automatically.

## Access from iPad/phone

The regular `run.bat` only binds to `127.0.0.1`, so nothing but this PC can
reach it. `run-lan.bat` starts a second, separate server bound to your whole
LAN over HTTPS (iOS Safari blocks microphone access on plain HTTP for
anything that isn't `localhost`, so HTTPS is required for the mic-based
tutorial input to work from an iPad/phone).

One-time setup:

1. Generate a self-signed cert (already done for this machine; re-run if
   `certs/` is missing or your PC's LAN IP changes — check with `ipconfig`):
   ```bash
   mkdir -p certs
   openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/dev-key.pem -out certs/dev-cert.pem \
     -days 825 -subj "/CN=sax2sheet-dev" \
     -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:<your-pc-lan-ip>"
   ```
2. Allow the port through Windows Firewall (run in an **elevated** PowerShell
   — this changes a system security setting, so do it yourself rather than
   via an automated tool):
   ```powershell
   New-NetFirewallRule -DisplayName "sax2sheet LAN" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow
   ```

Then, any time you want LAN access: double-click `run-lan.bat`. It prints the
URL to open on your iPad/phone (same wifi network as this PC). Your browser
will warn the cert isn't trusted the first time — that's expected for a
self-signed cert; tap through (Advanced → Visit anyway / Continue).

**Known limitation:** Web MIDI isn't implemented by any browser on iOS
(including Chrome/Edge for iOS, which are all WebKit under the hood), so a
MIDI keyboard plugged into an iPad won't be detected there — the tutorial
falls back to mic input automatically on iOS. MIDI keyboards work normally
from a desktop browser.

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
   box-select, confidence filter, undo; sampled playback for every supported
   instrument (Soundfont-player, FluidR3_GM).
3. **Analysis, quantization & transposition** -- librosa tempo/key estimate;
   grid/swing quantization; per-instrument transposition (Bb/Eb sax family,
   guitar's conventional +1-octave notation, piano's concert pitch) with
   octave-fold + flag for out-of-range notes; unit-tested
   (`tests/test_quantize.py`, `tests/test_transpose.py`).
4. **Notation & export** -- music21-built score; MusicXML/MIDI export;
   VexFlow staff preview; client-side SVG -> PDF (jsPDF + svg2pdf.js), so the
   exported PDF is exactly the SVG shown on screen.
5. **Stem separation** -- optional Demucs stage (`--extra separate`), stem
   caching, in-browser stem audition and re-transcription without
   re-separating, with an optional GPU device for the separation pass.

Sample playback (sections 3-4) uses vendored local sample files
(`web/vendor/soundfonts/`) rather than a CDN, so it works without live
internet access -- consistent with this being a local tool. A "Test speaker
(beep)" button plays a plain oscillator tone with no sample loading involved,
for isolating browser/audio-output problems from sample-loading problems.
Rendering the staff preview (section 5) is instant and purely client-side;
MusicXML/MIDI generation via music21 (the slow step) only runs when you
actually click a download link, not on every staff render.

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
- Guitar and piano's written ranges/transpositions are approximations (see
  `core/models.py` `INSTRUMENTS`) -- guitar in particular can be voiced far
  wider than standard notation covers, so expect more octave-folding on
  wide-range source material than with the sax family.
- The staff preview (and the current PDF/MusicXML export) always renders on
  a single treble staff. This is a reasonable fit for sax/guitar but not for
  piano, where a real piano part would split across a grand staff (treble +
  bass clef) -- low piano notes will show with many ledger lines instead.
