// Renders a VexFlow staff from the simplified score model produced by
// core/notation.score_to_json_model (see backend for the authoritative
// data). This is a *preview* renderer: it rounds arbitrary durations to the
// nearest standard note value and does not tie notes across barlines.
//
// The authoritative, fully-correct notation (arbitrary durations properly
// split into tied/dotted notes) lives in the exported MusicXML, which
// music21 builds directly from the same quantized/transposed notes -- see
// core/notation.py. Triplet-grid quantization is likewise approximated here
// (rounded to the nearest binary duration) since full tuplet layout is a
// v2 concern; MIDI/MusicXML exports are unaffected by this approximation.

const STANDARD_DURATIONS = [
  { beats: 4, vex: "w" },
  { beats: 3, vex: "hd" },
  { beats: 2, vex: "h" },
  { beats: 1.5, vex: "qd" },
  { beats: 1, vex: "q" },
  { beats: 0.75, vex: "8d" },
  { beats: 0.5, vex: "8" },
  { beats: 0.375, vex: "16d" },
  { beats: 0.25, vex: "16" },
  { beats: 0.125, vex: "32" },
  { beats: 0.0625, vex: "64" },
];

function roundToStandardDuration(beats) {
  let best = STANDARD_DURATIONS[STANDARD_DURATIONS.length - 1];
  let bestDiff = Infinity;
  for (const d of STANDARD_DURATIONS) {
    const diff = Math.abs(d.beats - beats);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = d;
    }
  }
  return best;
}

const MIDI_NOTE_NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"];
function midiToVexKey(midi) {
  const name = MIDI_NOTE_NAMES[((midi % 12) + 12) % 12];
  const octave = Math.floor(midi / 12) - 1;
  return `${name}/${octave}`;
}

const KEY_BY_SHARPS = {
  "-7": "Cb", "-6": "Gb", "-5": "Db", "-4": "Ab", "-3": "Eb", "-2": "Bb", "-1": "F",
  0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B", 6: "F#", 7: "C#",
};
function keySharpsToVexKey(sharps) {
  return KEY_BY_SHARPS[sharps] || "C";
}

function beatsPerMeasure(timeSignature) {
  const [num, den] = timeSignature.split("/").map(Number);
  // Assumes a quarter-note beat grid (matches quantize.py); exact for
  // simple meters (4/4, 3/4, 2/4), an approximation for compound meters.
  return den === 4 ? num : (num * 4) / den;
}

/** @returns the VexFlow Renderer, mainly so callers can grab its SVG for export. */
function renderStaff(container, scoreModel) {
  container.innerHTML = "";
  const { Renderer, Stave, StaveNote, Voice, Formatter, Accidental } = Vex.Flow;

  const bpMeasure = beatsPerMeasure(scoreModel.time_signature);
  const measures = [];
  for (const n of scoreModel.notes) {
    const idx = Math.floor((n.beat + 1e-6) / bpMeasure);
    while (measures.length <= idx) measures.push([]);
    measures[idx].push(n);
  }
  if (measures.length === 0) measures.push([]);

  const measureWidth = 220;
  const measuresPerRow = 4;
  const rowHeight = 150;
  const rows = Math.ceil(measures.length / measuresPerRow);
  const width = Math.min(measures.length, measuresPerRow) * measureWidth + 40;
  const height = rows * rowHeight + 20;

  const renderer = new Renderer(container, Renderer.Backends.SVG);
  renderer.resize(width, height);
  const context = renderer.getContext();
  const keyName = keySharpsToVexKey(scoreModel.key_sharps);

  measures.forEach((measureNotes, mIdx) => {
    const row = Math.floor(mIdx / measuresPerRow);
    const col = mIdx % measuresPerRow;
    const x = 10 + col * measureWidth;
    const y = 20 + row * rowHeight;

    const stave = new Stave(x, y, measureWidth);
    if (col === 0) {
      stave.addClef("treble").addKeySignature(keyName);
      if (mIdx === 0) stave.addTimeSignature(scoreModel.time_signature);
    }
    stave.setContext(context).draw();

    const vexNotes = [];
    let cursor = 0;
    const sorted = [...measureNotes].sort((a, b) => a.beat - b.beat);
    for (const n of sorted) {
      const localBeat = n.beat - mIdx * bpMeasure;
      if (localBeat > cursor + 1e-6) {
        const restDur = roundToStandardDuration(localBeat - cursor);
        vexNotes.push(new StaveNote({ keys: ["b/4"], duration: restDur.vex + "r" }));
        cursor = localBeat;
      }
      const remaining = bpMeasure - cursor;
      const durInfo = roundToStandardDuration(Math.min(n.duration_beats, remaining));
      const staveNote = new StaveNote({ keys: [midiToVexKey(n.written_pitch_midi)], duration: durInfo.vex });
      if (n.folded) {
        staveNote.setStyle({ fillStyle: "#e8a33d", strokeStyle: "#e8a33d" });
      }
      vexNotes.push(staveNote);
      cursor += durInfo.beats;
    }
    if (cursor < bpMeasure - 1e-6) {
      const restDur = roundToStandardDuration(bpMeasure - cursor);
      vexNotes.push(new StaveNote({ keys: ["b/4"], duration: restDur.vex + "r" }));
    }

    const voice = new Voice({ num_beats: bpMeasure, beat_value: 4 }).setStrict(false);
    voice.addTickables(vexNotes);
    Accidental.applyAccidentals([voice], keyName);
    new Formatter().joinVoices([voice]).format([voice], measureWidth - 20);
    voice.draw(context, stave);
  });

  return renderer;
}
