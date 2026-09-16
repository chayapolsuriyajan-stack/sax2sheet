// Microphone-based note detection for the play-along tutorial. Two
// genuinely different problems, handled differently (see the plan):
//   - Monophonic (single notes, e.g. sax, or checking one hand alone):
//     YIN autocorrelation pitch detection on a raw time-domain buffer ->
//     one confident fundamental frequency.
//   - Polyphonic (piano chords): NOT full chord transcription -- that's
//     unreliable in real time. Instead this VERIFIES whether energy is
//     present at each of the EXPECTED pitches' fundamentals (read off the
//     frequency-domain spectrum), which is a much more tractable question
//     than "what chord did you just play".
//
// Both read from the same AnalyserNode; callers choose which method fits
// what they're waiting for (see tutorial.js).

class MicInput {
  constructor({ timeFftSize = 4096, freqFftSize = 32768 } = {}) {
    // Two separate AnalyserNodes tapping the same source, because the two
    // detection methods have genuinely different resolution needs. YIN
    // operates on raw time-domain samples, so a moderate buffer is fine (and
    // keeps it responsive -- a bigger buffer means a longer window before a
    // pitch change is "seen"). Chord verification instead needs enough
    // FREQUENCY resolution to tell adjacent semitones apart: verified this
    // matters in practice -- at 4096 points (~10.8 Hz/bin), adjacent
    // semitones near middle C are only ~1.4 bins apart, and a live test
    // confirmed every semitone in a whole-tone range around a single played
    // note falsely read as "sounding". 32768 points (~1.35 Hz/bin, the
    // AnalyserNode maximum) gives a clean margin even down near C2, where
    // semitones are only ~3.9 Hz apart.
    this.timeFftSize = timeFftSize;
    this.freqFftSize = freqFftSize;
    this.ctx = null;
    this.timeAnalyser = null;
    this.freqAnalyser = null;
    this.source = null;
    this.stream = null;
    this.timeBuf = null;
    this.running = false;
  }

  async start() {
    if (this.running) return;
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    // iOS Safari (and some other browsers) create a fresh AudioContext
    // suspended even inside a user-gesture handler -- same fix already
    // applied in playback.js for the sample-playback path.
    if (this.ctx.state === "suspended") await this.ctx.resume();
    // Disable processing that fights pitch detection: echo cancellation and
    // noise suppression both distort the waveform in ways that throw off
    // autocorrelation-based pitch estimates.
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    this.source = this.ctx.createMediaStreamSource(this.stream);

    this.timeAnalyser = this.ctx.createAnalyser();
    this.timeAnalyser.fftSize = this.timeFftSize;
    this.timeAnalyser.smoothingTimeConstant = 0;

    this.freqAnalyser = this.ctx.createAnalyser();
    this.freqAnalyser.fftSize = this.freqFftSize;
    this.freqAnalyser.smoothingTimeConstant = 0;

    this.source.connect(this.timeAnalyser);
    this.source.connect(this.freqAnalyser);

    this.timeBuf = new Float32Array(this.timeAnalyser.fftSize);
    this.running = true;
  }

  stop() {
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.ctx) this.ctx.close();
    this.running = false;
  }

  /** Monophonic pitch detection via YIN. Returns {midi, freq, clarity} (0-1,
   * higher = more confident) or null if no confident single pitch was found
   * (silence, noise, or genuinely polyphonic input the algorithm can't
   * resolve to one fundamental).
   */
  detectMonophonicPitch() {
    if (!this.running) return null;
    this.timeAnalyser.getFloatTimeDomainData(this.timeBuf);
    const result = yinPitch(this.timeBuf, this.ctx.sampleRate);
    if (!result) return null;
    return { midi: freqToMidi(result.freq), freq: result.freq, clarity: result.clarity };
  }

  /** Polyphonic verification: for each expected MIDI pitch, checks whether
   * there's meaningful spectral energy at its FUNDAMENTAL only. Returns a
   * Set of the expected pitches that appear to actually be sounding.
   *
   * Deliberately fundamental-only, no harmonic fallback: an earlier version
   * of this also checked each note's 2nd harmonic as a fallback (reasoning
   * that a weak fundamental picked up by a laptop mic might still show a
   * clear harmonic), but that produces confirmed false positives whenever
   * the octave above is genuinely playing -- e.g. checking for C3 while C4
   * is actually sounding reads "yes, C3 is sounding" because C3's 2nd
   * harmonic and C4's fundamental are the same frequency. Verified via a
   * real AnalyserNode against a live C-E-G triad: with the harmonic
   * fallback, checking C3/G3 (an octave below the playing notes) false-
   * positived at the maximum byte level (255); fundamental-only correctly
   * reports 0 for both.
   *
   * Also uses getByteFrequencyData (quantized 0-255 over
   * [minDecibels, maxDecibels]) rather than getFloatFrequencyData: float dB
   * values for near-silent bins can read as extremely negative (verified:
   * -186dB against a theoretical floor), which made a relative-to-median
   * noise-floor threshold nearly meaningless -- practically anything read
   * as "above the floor". An absolute byte threshold is far more stable.
   * Verified against the same live triad: actually-playing notes read 255
   * (max), the worst false-positive-risk spillover onto a non-playing note
   * a step away measured 133 -- minPeakLevel's default of 170 sits cleanly
   * above that gap.
   *
   * KNOWN LIMITATION, verified and not resolvable by tuning these
   * parameters: this cannot reliably tell apart notes a semitone or two
   * apart, especially in the bass register. A single played note's energy
   * spreads across several neighboring FFT bins regardless of window
   * choice (the AnalyserNode's fixed Blackman windowing has a multi-bin-
   * wide main lobe) -- verified by sweeping toleranceCents from 35 down to
   * 8 with zero effect: a single C4 still read three adjacent semitones as
   * "sounding", and a single C2 read all five tested. This is the "mic +
   * polyphony stays approximate" limitation the project plan already
   * called out, not a bug introduced here. Practical effect: wait mode can
   * be fooled by a wrong note a semitone or two off the expected one,
   * particularly low on the keyboard. MIDI input has none of this
   * ambiguity, which is why it's preferred whenever available.
   */
  verifyExpectedPitches(expectedMidiList, { toleranceCents = 35, minPeakLevel = 170 } = {}) {
    if (!this.running) return new Set();
    const byteBuf = new Uint8Array(this.freqAnalyser.frequencyBinCount);
    this.freqAnalyser.getByteFrequencyData(byteBuf);
    const binHz = this.ctx.sampleRate / this.freqAnalyser.fftSize;

    const sounding = new Set();
    for (const midi of expectedMidiList) {
      const fundamentalHz = midiToFreq(midi);
      if (_peakByteNear(byteBuf, binHz, fundamentalHz, toleranceCents) >= minPeakLevel) {
        sounding.add(midi);
      }
    }
    return sounding;
  }
}

function _peakByteNear(byteBuf, binHz, targetHz, toleranceCents) {
  const lowHz = targetHz * Math.pow(2, -toleranceCents / 1200);
  const highHz = targetHz * Math.pow(2, toleranceCents / 1200);
  const lowBin = Math.max(0, Math.floor(lowHz / binHz));
  const highBin = Math.min(byteBuf.length - 1, Math.ceil(highHz / binHz));
  let peak = 0;
  for (let i = lowBin; i <= highBin; i++) {
    if (byteBuf[i] > peak) peak = byteBuf[i];
  }
  return peak;
}

function midiToFreq(midi) {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

function freqToMidi(freq) {
  return 69 + 12 * Math.log2(freq / 440);
}

// -- YIN pitch detection ----------------------------------------------------
// Standard YIN algorithm (de Cheveigne & Kawahara, 2002): a cumulative-mean
// normalized difference function, which is meaningfully more robust to
// octave errors than plain autocorrelation, at moderate extra cost. Verified
// against synthetic sine waves at known frequencies during development
// (script results, not asserted here since this file has no test harness --
// vanilla JS with no build step, see architecture notes).
function yinPitch(buf, sampleRate, { threshold = 0.15, minFreq = 60, maxFreq = 1500 } = {}) {
  const n = buf.length;
  const maxLag = Math.min(n - 1, Math.floor(sampleRate / minFreq));
  const minLag = Math.max(1, Math.floor(sampleRate / maxFreq));
  if (maxLag <= minLag) return null;

  const diff = new Float32Array(maxLag + 1);
  for (let lag = minLag; lag <= maxLag; lag++) {
    let sum = 0;
    for (let i = 0; i < n - lag; i++) {
      const d = buf[i] - buf[i + lag];
      sum += d * d;
    }
    diff[lag] = sum;
  }

  const cmnd = new Float32Array(maxLag + 1);
  cmnd[minLag] = 1;
  let runningSum = 0;
  for (let lag = minLag; lag <= maxLag; lag++) {
    runningSum += diff[lag];
    cmnd[lag] = runningSum > 0 ? (diff[lag] * lag) / runningSum : 1;
  }

  let tau = -1;
  for (let lag = minLag + 1; lag < maxLag; lag++) {
    if (cmnd[lag] < threshold) {
      while (lag + 1 <= maxLag && cmnd[lag + 1] < cmnd[lag]) lag++;
      tau = lag;
      break;
    }
  }
  if (tau === -1) return null; // no confident periodic pitch (silence/noise)

  // Parabolic interpolation around tau for sub-sample precision.
  let betterTau = tau;
  if (tau > minLag && tau < maxLag) {
    const s0 = cmnd[tau - 1], s1 = cmnd[tau], s2 = cmnd[tau + 1];
    const denom = 2 * (2 * s1 - s2 - s0);
    if (denom !== 0) {
      const adjustment = (s2 - s0) / denom;
      if (Number.isFinite(adjustment) && Math.abs(adjustment) < 1) betterTau = tau + adjustment;
    }
  }

  return { freq: sampleRate / betterTau, clarity: 1 - cmnd[tau] };
}
