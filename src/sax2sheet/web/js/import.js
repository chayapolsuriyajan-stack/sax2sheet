// Wires the "Imported score" panel: upload a MusicXML/MXL/MIDI file, render
// its grand staff (or single staff), and export PDF/MusicXML/MIDI. This is
// the alternate entry path to the app that skips audio transcription
// entirely -- see core/score_import.py. Deliberately separate from app.js's
// audio-pipeline wiring since the two flows share almost nothing past the
// project id.

const scoreFileInput = document.getElementById("score-file-input");
const importStatus = document.getElementById("import-status");
const omrFileInput = document.getElementById("omr-file-input");
const omrStatus = document.getElementById("omr-status");

const scoredocPanel = document.getElementById("scoredoc-panel");
const scoredocProjectIdEl = document.getElementById("scoredoc-project-id");
const scoredocTitleEl = document.getElementById("scoredoc-title");
const renderScoredocBtn = document.getElementById("render-scoredoc-btn");
const exportScoredocPdfBtn = document.getElementById("export-scoredoc-pdf-btn");
const downloadScoredocMusicxml = document.getElementById("download-scoredoc-musicxml");
const downloadScoredocMidi = document.getElementById("download-scoredoc-midi");
const scoredocStatus = document.getElementById("scoredoc-status");
const scoredocStaffContainer = document.getElementById("scoredoc-staff-container");

const tutorialPlayBtn = document.getElementById("tutorial-play-btn");
const tutorialPauseBtn = document.getElementById("tutorial-pause-btn");
const tutorialRestartBtn = document.getElementById("tutorial-restart-btn");
const tutorialTempoSlider = document.getElementById("tutorial-tempo-slider");
const tutorialTempoValue = document.getElementById("tutorial-tempo-value");
const fallingNotesContainer = document.getElementById("fallingnotes-container");
const keyboardContainer = document.getElementById("keyboard-container");

const tutorialEnableInputBtn = document.getElementById("tutorial-enable-input-btn");
const tutorialWaitCheckbox = document.getElementById("tutorial-wait-checkbox");
const tutorialInputStatus = document.getElementById("tutorial-input-status");

let currentScoreProjectId = null;
let scoredocExportedFiles = null; // cached {musicxml_url, midi_url} once export has actually run

let tutorialKeyboard = null;
let tutorialFallingNotes = null;
let tutorialTransport = null;
let tutorialController = null;

async function onProjectImported(project, statusEl, label) {
  statusEl.textContent = `Imported: ${project.source_label}`;
  currentScoreProjectId = project.project_id;
  scoredocExportedFiles = null;

  scoredocProjectIdEl.textContent = project.project_id;
  scoredocPanel.hidden = false;

  const doc = await api.getScoreDoc(project.project_id);
  scoredocTitleEl.textContent = doc.title || "(untitled)";
}

scoreFileInput.addEventListener("change", async () => {
  const file = scoreFileInput.files[0];
  if (!file) return;
  importStatus.textContent = `Importing ${file.name}...`;
  try {
    const project = await api.uploadScore(file);
    await onProjectImported(project, importStatus);
  } catch (e) {
    console.error("Score import failed", e);
    importStatus.textContent = `Import failed: ${e.message}`;
  }
});

omrFileInput.addEventListener("change", async () => {
  const file = omrFileInput.files[0];
  if (!file) return;
  omrStatus.textContent = `Scanning ${file.name} (OMR -- this can take a few minutes)...`;
  omrFileInput.disabled = true;
  try {
    const project = await api.uploadScan(file);
    await onProjectImported(project, omrStatus);
    omrStatus.textContent = `Imported via OMR: ${project.source_label}. Check the result carefully -- OMR accuracy is approximate.`;
  } catch (e) {
    console.error("OMR import failed", e);
    omrStatus.textContent = `OMR failed: ${e.message}`;
  } finally {
    omrFileInput.disabled = false;
  }
});

renderScoredocBtn.addEventListener("click", async () => {
  if (!currentScoreProjectId) return;
  scoredocStatus.textContent = "Rendering...";
  renderScoredocBtn.disabled = true;
  try {
    // The full ScoreDoc already has everything renderGrandStaff needs;
    // build the score_model shape client-side (mirrors
    // core/notation.score_doc_to_json_model) rather than round-tripping
    // through the export endpoint just to draw a preview -- export is the
    // slow step (music21 building + writing files) and should only run
    // when a download is actually requested, same reasoning as the audio
    // pipeline's "Render staff" button.
    const doc = await api.getScoreDoc(currentScoreProjectId);
    const model = scoreDocToModel(doc);
    renderGrandStaff(scoredocStaffContainer, model);
    setUpTutorial(model);
    scoredocStatus.textContent = `Rendered ${model.notes.length} notes across ${model.staves} staff/staves.`;
  } catch (e) {
    console.error("Render failed", e);
    scoredocStatus.textContent = `Error: ${e.message}`;
  } finally {
    renderScoredocBtn.disabled = false;
  }
});

function setUpTutorial(model) {
  if (tutorialTransport) tutorialTransport.pause();

  const pitches = model.notes.map((n) => n.written_pitch_midi);
  const minMidi = pitches.length ? Math.max(21, Math.min(...pitches) - 3) : 48;
  const maxMidi = pitches.length ? Math.min(108, Math.max(...pitches) + 3) : 84;

  if (!tutorialKeyboard) {
    tutorialKeyboard = new PianoKeyboard(keyboardContainer, { minMidi, maxMidi });
  } else {
    tutorialKeyboard.setRange(minMidi, maxMidi);
  }
  tutorialKeyboard.draw();

  if (!tutorialFallingNotes) {
    tutorialFallingNotes = new FallingNotes(fallingNotesContainer, tutorialKeyboard);
  }
  tutorialFallingNotes.setNotes(model.notes);

  if (!tutorialTransport) {
    tutorialTransport = new Transport(model.bpm);
    tutorialTransport.onTick((beat) => tutorialFallingNotes.render(beat));
  } else {
    tutorialTransport.bpm = model.bpm;
    tutorialTransport.seek(0);
  }
  tutorialTransport.tickOnce();

  if (tutorialController) tutorialController.stop();
  tutorialController = new TutorialController(tutorialTransport, model.notes);
  tutorialController.onStatus = renderTutorialInputStatus;
  tutorialController.onWaitModeChange = syncTutorialWaitModeUI;
  tutorialWaitCheckbox.checked = false;
  tutorialWaitCheckbox.disabled = true;
  tutorialInputStatus.textContent = "";
}

/** Keeps the checkbox/Play/Pause buttons in sync with wait mode's actual
 * state -- fires on both a user toggling the checkbox AND wait mode turning
 * itself off automatically when the piece completes (verified: without
 * this, completing a piece in wait mode left Play permanently disabled).
 */
function syncTutorialWaitModeUI(enabled) {
  tutorialWaitCheckbox.checked = enabled;
  tutorialPlayBtn.disabled = enabled;
  tutorialPauseBtn.disabled = enabled;
  // Deliberately doesn't touch tutorialInputStatus's text here -- leaves
  // whatever the last onStatus update said (e.g. "✓ F4 (4/4)") visible
  // after auto-completion, instead of clearing it.
}

function midiName(midi) {
  const names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const octave = Math.floor(midi / 12) - 1;
  return `${names[((midi % 12) + 12) % 12]}${octave}`;
}

function renderTutorialInputStatus({ expected, satisfied, groupIndex, total }) {
  const names = expected.map(midiName).join(", ");
  tutorialInputStatus.textContent = satisfied
    ? `✓ ${names} (${groupIndex + 1}/${total})`
    : `Waiting for: ${names} (${groupIndex + 1}/${total})`;
  tutorialInputStatus.style.color = satisfied ? "#5bc0ff" : "";
}

tutorialEnableInputBtn.addEventListener("click", async () => {
  if (!tutorialController) {
    tutorialInputStatus.textContent = "Compute/render the tutorial first.";
    return;
  }
  tutorialEnableInputBtn.disabled = true;
  tutorialInputStatus.textContent = "Requesting input access...";
  try {
    const active = await tutorialController.ensureInput();
    if (active === "midi") {
      tutorialInputStatus.textContent = "MIDI keyboard connected.";
      tutorialWaitCheckbox.disabled = false;
    } else if (active === "mic") {
      tutorialInputStatus.textContent = "No MIDI device found -- using microphone (approximate for chords).";
      tutorialWaitCheckbox.disabled = false;
    } else {
      tutorialInputStatus.textContent = "No input available (MIDI/mic access denied or unsupported).";
    }
  } catch (e) {
    console.error("Enabling tutorial input failed", e);
    tutorialInputStatus.textContent = `Error: ${e.message}`;
  } finally {
    tutorialEnableInputBtn.disabled = false;
  }
});

tutorialWaitCheckbox.addEventListener("change", () => {
  // Wait mode drives the transport itself (pauses, then advances on a
  // correct note) -- free-running Play/Pause would fight that.
  // syncTutorialWaitModeUI (wired as onWaitModeChange) disables/re-enables
  // them, and also handles the auto-off-on-completion case.
  if (!tutorialController) return;
  tutorialController.setWaitMode(tutorialWaitCheckbox.checked);
});

tutorialPlayBtn.addEventListener("click", () => {
  if (!tutorialTransport) return;
  tutorialTransport.play();
});

tutorialPauseBtn.addEventListener("click", () => {
  if (!tutorialTransport) return;
  tutorialTransport.pause();
});

tutorialRestartBtn.addEventListener("click", () => {
  if (!tutorialTransport) return;
  tutorialTransport.pause();
  tutorialTransport.seek(0);
  tutorialTransport.tickOnce();
  // Re-sync wait mode's chord-group cursor back to the start too, or it'd
  // stay wherever it was mid-piece while the transport visibly rewound.
  if (tutorialController && tutorialController.waitMode) {
    tutorialController.setWaitMode(true);
  }
});

tutorialTempoSlider.addEventListener("input", () => {
  const scale = parseFloat(tutorialTempoSlider.value);
  tutorialTempoValue.textContent = `${Math.round(scale * 100)}%`;
  if (tutorialTransport) tutorialTransport.setTempoScale(scale);
});

function scoreDocToModel(doc, partId = null) {
  const target = partId ? doc.parts.find((p) => p.part_id === partId) : doc.parts[0];
  if (!target) return { title: doc.title, key_sharps: 0, time_signature: "4/4", bpm: 120, staves: 1, notes: [] };
  const notes = doc.notes
    .filter((n) => n.part_id === target.part_id && !n.deleted)
    .map((n) => ({
      beat: n.beat,
      duration_beats: n.duration_beats,
      written_pitch_midi: n.pitch_midi,
      staff: n.staff,
      hand: n.hand,
      finger: n.finger,
      folded: n.folded,
    }));
  return {
    title: doc.title,
    key_sharps: doc.key_signatures.length ? doc.key_signatures[0].sharps : 0,
    time_signature: doc.time_signatures.length ? doc.time_signatures[0].time_signature : "4/4",
    bpm: doc.tempos.length ? doc.tempos[0].bpm : 120,
    staves: target.staves,
    notes,
  };
}

exportScoredocPdfBtn.addEventListener("click", async () => {
  try {
    await exportStaffToPdf(scoredocStaffContainer, "sax2sheet-imported-score.pdf");
  } catch (e) {
    scoredocStatus.textContent = `PDF export error: ${e.message}`;
  }
});

async function ensureScoredocExported() {
  if (scoredocExportedFiles) return scoredocExportedFiles;
  scoredocStatus.textContent = "Building MusicXML/MIDI...";
  const result = await api.exportScoreDoc(currentScoreProjectId);
  scoredocExportedFiles = { musicxml_url: result.musicxml_url, midi_url: result.midi_url };
  return scoredocExportedFiles;
}

async function downloadScoredocExport(ev, urlKey, label) {
  ev.preventDefault();
  const link = ev.currentTarget;
  const originalText = link.textContent;
  link.textContent = `Preparing ${label}...`;
  try {
    const files = await ensureScoredocExported();
    scoredocStatus.textContent = `${label} ready.`;
    window.location.href = files[urlKey];
  } catch (e) {
    scoredocStatus.textContent = `Error: ${e.message}`;
  } finally {
    link.textContent = originalText;
  }
}

downloadScoredocMusicxml.addEventListener("click", (ev) => downloadScoredocExport(ev, "musicxml_url", "MusicXML"));
downloadScoredocMidi.addEventListener("click", (ev) => downloadScoredocExport(ev, "midi_url", "MIDI"));
