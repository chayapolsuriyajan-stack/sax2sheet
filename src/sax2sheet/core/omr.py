"""OMR (optical music recognition): PDF/photo -> MusicXML, via the isolated
`oemer` tool (see plan: score import + play-along tutorial mode). This is
the third and last score-import source -- upload and OMR both converge on
score_import.import_score_upload() once a MusicXML file exists.

oemer is NOT a project dependency -- it's installed and run in its own
isolated environment via `uv tool run --from oemer`, because oemer depends
on onnxruntime-gpu, which provides the same importable `onnxruntime` module
as the plain onnxruntime this project already uses for Basic Pitch. Running
it out-of-process sidesteps that collision entirely; nothing from oemer's
dependency tree ever enters this project's own venv.

Three compatibility fixes below, all verified empirically against this
environment rather than assumed:
  - oemer's bundled ONNX model fails against onnxruntime >=1.30 with
    "[ShapeInferenceError] Attribute pads must not contain negative values"
    on the model's conv2d_transpose node. Pinned to 1.16.3.
  - onnxruntime 1.16.3 needs numpy<2 (a numpy 1.x/2.x ABI mismatch
    otherwise crashes the import with "_ARRAY_API not found").
  - GPU is force-disabled via CUDA_VISIBLE_DEVICES="" in the subprocess
    environment. oemer's own dependency on onnxruntime-gpu can't be fully
    avoided even when we additionally pin plain onnxruntime (uv still
    resolves both into the ephemeral tool env), but hiding CUDA devices
    from the driver makes onnxruntime's execution-provider selection fall
    back to CPU regardless of which variant is actually installed.

Known limitation: oemer's clustering step throws on near-empty input (a
single sparse measure -- "Found array with 1 sample(s) ... while a minimum
of 2 is required by AgglomerativeClustering"). A real scanned page with
normal musical content doesn't hit this; it only showed up against a
synthetic one-measure test image during development.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PINNED_ONNXRUNTIME = "onnxruntime-gpu==1.16.3"
PINNED_NUMPY = "numpy<2"
OEMER_TIMEOUT_S = 600

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
SUPPORTED_OMR_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}


def is_available() -> bool:
    """Whether OMR can even be attempted -- checks that `uv` is on PATH.
    The oemer package itself is resolved on demand by `uv tool run
    --from oemer`, so nothing needs to be pre-installed; the first call
    downloads oemer and its ~330MB of model weights, which is slow but
    only happens once (uv and oemer both cache what they fetch).
    """
    return shutil.which("uv") is not None


def pdf_first_page_to_image(pdf_path: Path, dpi: int = 300) -> Path:
    """Renders page 1 of a PDF to a PNG in a fresh temp directory the
    caller owns. Multi-page PDFs only OMR their first page for now -- a
    known scope limitation, not a technical ceiling; extending to every
    page is a matter of looping this and running oemer per page.
    """
    import pymupdf

    out_dir = Path(tempfile.mkdtemp(prefix="sax2sheet_omr_"))
    doc = pymupdf.open(str(pdf_path))
    if doc.page_count == 0:
        raise RuntimeError("PDF has no pages")

    mat = pymupdf.Matrix(dpi / 72, dpi / 72)
    pix = doc[0].get_pixmap(matrix=mat)
    image_path = out_dir / "page1.png"
    pix.save(str(image_path))
    return image_path


def run_oemer(image_path: Path) -> Path:
    """Runs oemer on a single page image in its isolated environment,
    returning the produced MusicXML path. Raises RuntimeError with oemer's
    own error output on failure.
    """
    if not is_available():
        raise RuntimeError(
            "OMR requires `uv` on PATH to run the isolated oemer tool environment "
            "(uv tool run --from oemer)."
        )

    out_dir = image_path.parent
    cmd = [
        "uv", "tool", "run", "--python", "3.11", "--from", "oemer",
        "--with", PINNED_ONNXRUNTIME, "--with", PINNED_NUMPY,
        "oemer", str(image_path), "-o", str(out_dir),
    ]
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = ""  # force CPU -- see module docstring

    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=OEMER_TIMEOUT_S)
    if result.returncode != 0:
        raise RuntimeError(f"OMR failed on {image_path.name}:\n{result.stderr[-3000:]}")

    produced = out_dir / f"{image_path.stem}.musicxml"
    if not produced.exists():
        raise RuntimeError(f"oemer did not produce the expected output file: {produced}")
    return produced


def scan_to_musicxml(input_path: Path) -> Path:
    """Top-level entry point: a PDF or a plain image, either way returns a
    MusicXML path ready for score_import.import_score_upload().
    """
    suffix = input_path.suffix.lower()
    if suffix == ".pdf":
        image_path = pdf_first_page_to_image(input_path)
    elif suffix in IMAGE_SUFFIXES:
        image_path = input_path
    else:
        raise ValueError(
            f"unsupported OMR input type: {suffix!r} "
            f"(supported: {', '.join(sorted(SUPPORTED_OMR_SUFFIXES))})"
        )

    return run_oemer(image_path)
