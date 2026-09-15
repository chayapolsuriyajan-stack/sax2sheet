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

function groupNotesIntoMeasures(notes, bpMeasure) {
  const measures = [];
  for (const n of notes) {
    const idx = Math.floor((n.beat + 1e-6) / bpMeasure);
    while (measures.length <= idx) measures.push([]);
    measures[idx].push(n);
  }
  if (measures.length === 0) measures.push([]);
  return measures;
}

/** Notes sharing a beat (chords) grouped together, sorted low-to-high pitch
 * within each group -- VexFlow wants chord keys ascending for correct
 * notehead/stem layout. */
function groupByBeat(notes) {
  const map = new Map();
  for (const n of notes) {
    if (!map.has(n.beat)) map.set(n.beat, []);
    map.get(n.beat).push(n);
  }
  return [...map.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([beat, group]) => [beat, [...group].sort((a, b) => a.written_pitch_midi - b.written_pitch_midi)]);
}

/** Builds the VexFlow tickables (notes/chords/rests) for one measure on one
 * staff, filling gaps with rests and adding fingering annotations when
 * present. Shared by the single-staff and grand-staff renderers below.
 */
function buildMeasureTickables(measureNotes, measureStartBeat, bpMeasure, restLine = "b/4") {
  const { StaveNote, Annotation } = Vex.Flow;
  const vexNotes = [];
  let cursor = 0;

  for (const [beat, group] of groupByBeat(measureNotes)) {
    const localBeat = beat - measureStartBeat;
    if (localBeat > cursor + 1e-6) {
      const restDur = roundToStandardDuration(localBeat - cursor);
      vexNotes.push(new StaveNote({ keys: [restLine], duration: restDur.vex + "r" }));
      cursor = localBeat;
    }
    const remaining = bpMeasure - cursor;
    const durInfo = roundToStandardDuration(Math.min(group[0].duration_beats, remaining));
    const keys = group.map((n) => midiToVexKey(n.written_pitch_midi));
    const staveNote = new StaveNote({ keys, duration: durInfo.vex });

    if (group.some((n) => n.folded)) {
      staveNote.setStyle({ fillStyle: "#e8a33d", strokeStyle: "#e8a33d" });
    }
    group.forEach((n, i) => {
      if (n.finger) {
        const ann = new Annotation(String(n.finger));
        ann.setVerticalJustification(Annotation.VerticalJustify.TOP);
        staveNote.addModifier(ann, i);
      }
    });

    vexNotes.push(staveNote);
    cursor += durInfo.beats;
  }
  if (cursor < bpMeasure - 1e-6) {
    const restDur = roundToStandardDuration(bpMeasure - cursor);
    vexNotes.push(new StaveNote({ keys: [restLine], duration: restDur.vex + "r" }));
  }
  return vexNotes;
}

function drawMeasureVoice(context, stave, tickables, bpMeasure, measureWidth, keyName) {
  const { Voice, Formatter, Accidental } = Vex.Flow;
  const voice = new Voice({ num_beats: bpMeasure, beat_value: 4 }).setStrict(false);
  voice.addTickables(tickables);
  Accidental.applyAccidentals([voice], keyName);
  new Formatter().joinVoices([voice]).format([voice], measureWidth - 20);
  voice.draw(context, stave);
}

/** @returns the VexFlow Renderer, mainly so callers can grab its SVG for export. */
function renderStaff(container, scoreModel) {
  container.innerHTML = "";
  const { Renderer, Stave } = Vex.Flow;

  const bpMeasure = beatsPerMeasure(scoreModel.time_signature);
  const measures = groupNotesIntoMeasures(scoreModel.notes, bpMeasure);

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

    const tickables = buildMeasureTickables(measureNotes, mIdx * bpMeasure, bpMeasure);
    drawMeasureVoice(context, stave, tickables, bpMeasure, measureWidth, keyName);
  });

  return renderer;
}

// -- Grand staff (imported scores) ------------------------------------------
// Renders from core/notation.score_doc_to_json_model's output: notes carry
// `staff` (1 = treble, 2 = bass), `hand`, and `finger` in addition to the
// fields renderStaff() above consumes. A one-staff part (e.g. an imported
// solo sax line) renders as a single stave; a two-staff part (piano) renders
// treble+bass joined by a brace, one system per row. Same "preview" caveats
// as renderStaff(): durations rounded to standard note values, no ties
// across barlines, no true tuplets -- the exported MusicXML (built directly
// from the same ScoreDoc by build_score_from_doc) isn't subject to those.
function renderGrandStaff(container, scoreDocModel) {
  container.innerHTML = "";
  const { Renderer, Stave, StaveConnector } = Vex.Flow;

  const staffCount = scoreDocModel.staves || 1;
  const bpMeasure = beatsPerMeasure(scoreDocModel.time_signature);
  const keyName = keySharpsToVexKey(scoreDocModel.key_sharps);

  const notesByStaff = [1, 2].slice(0, staffCount).map((s) =>
    scoreDocModel.notes.filter((n) => n.staff === s)
  );
  const measuresByStaff = notesByStaff.map((notes) => groupNotesIntoMeasures(notes, bpMeasure));
  const measureCount = Math.max(1, ...measuresByStaff.map((m) => m.length));

  const measureWidth = 240;
  const measuresPerRow = 3;
  const staveHeight = 90; // vertical space per stave within a system
  const systemHeight = staffCount === 2 ? staveHeight * 2 + 10 : staveHeight + 10;
  const rows = Math.ceil(measureCount / measuresPerRow);
  const leftMargin = staffCount === 2 ? 30 : 10; // room for the brace
  const width = Math.min(measureCount, measuresPerRow) * measureWidth + leftMargin + 20;
  const height = rows * systemHeight + 20;

  const renderer = new Renderer(container, Renderer.Backends.SVG);
  renderer.resize(width, height);
  const context = renderer.getContext();

  for (let mIdx = 0; mIdx < measureCount; mIdx++) {
    const row = Math.floor(mIdx / measuresPerRow);
    const col = mIdx % measuresPerRow;
    const x = leftMargin + col * measureWidth;
    const y0 = 10 + row * systemHeight;

    const staves = [];
    for (let s = 0; s < staffCount; s++) {
      const y = y0 + s * staveHeight;
      const stave = new Stave(x, y, measureWidth);
      if (col === 0) {
        stave.addClef(s === 0 ? "treble" : "bass").addKeySignature(keyName);
        if (mIdx === 0) stave.addTimeSignature(scoreDocModel.time_signature);
      }
      stave.setContext(context).draw();
      staves.push(stave);

      const measureNotes = measuresByStaff[s][mIdx] || [];
      const tickables = buildMeasureTickables(measureNotes, mIdx * bpMeasure, bpMeasure, s === 0 ? "b/4" : "d/3");
      drawMeasureVoice(context, stave, tickables, bpMeasure, measureWidth, keyName);
    }

    if (staffCount === 2 && col === 0) {
      const brace = new StaveConnector(staves[0], staves[1]).setType(StaveConnector.type.BRACE);
      brace.setContext(context).draw();
      const line = new StaveConnector(staves[0], staves[1]).setType(StaveConnector.type.SINGLE_LEFT);
      line.setContext(context).draw();
    }
  }

  return renderer;
}
