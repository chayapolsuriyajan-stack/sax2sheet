// Wires the "Imported score" panel: upload a MusicXML/MXL/MIDI file, render
// its grand staff (or single staff), and export PDF/MusicXML/MIDI. This is
// the alternate entry path to the app that skips audio transcription
// entirely -- see core/score_import.py. Deliberately separate from app.js's
// audio-pipeline wiring since the two flows share almost nothing past the
// project id.

const scoreFileInput = document.getElementById("score-file-input");
const importStatus = document.getElementById("import-status");

const scoredocPanel = document.getElementById("scoredoc-panel");
const scoredocProjectIdEl = document.getElementById("scoredoc-project-id");
const scoredocTitleEl = document.getElementById("scoredoc-title");
const renderScoredocBtn = document.getElementById("render-scoredoc-btn");
const exportScoredocPdfBtn = document.getElementById("export-scoredoc-pdf-btn");
const downloadScoredocMusicxml = document.getElementById("download-scoredoc-musicxml");
const downloadScoredocMidi = document.getElementById("download-scoredoc-midi");
const scoredocStatus = document.getElementById("scoredoc-status");
const scoredocStaffContainer = document.getElementById("scoredoc-staff-container");

let currentScoreProjectId = null;
let scoredocExportedFiles = null; // cached {musicxml_url, midi_url} once export has actually run

scoreFileInput.addEventListener("change", async () => {
  const file = scoreFileInput.files[0];
  if (!file) return;
  importStatus.textContent = `Importing ${file.name}...`;
  try {
    const project = await api.uploadScore(file);
    importStatus.textContent = `Imported: ${project.source_label}`;
    currentScoreProjectId = project.project_id;
    scoredocExportedFiles = null;

    scoredocProjectIdEl.textContent = project.project_id;
    scoredocPanel.hidden = false;

    const doc = await api.getScoreDoc(project.project_id);
    scoredocTitleEl.textContent = doc.title || "(untitled)";
  } catch (e) {
    console.error("Score import failed", e);
    importStatus.textContent = `Import failed: ${e.message}`;
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
    scoredocStatus.textContent = `Rendered ${model.notes.length} notes across ${model.staves} staff/staves.`;
  } catch (e) {
    console.error("Render failed", e);
    scoredocStatus.textContent = `Error: ${e.message}`;
  } finally {
    renderScoredocBtn.disabled = false;
  }
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
