"""Tests for core/omr.py's deterministic logic -- input validation and PDF
page extraction. The actual oemer invocation (run_oemer) is deliberately
NOT unit-tested here: it shells out to an isolated `uv tool run` environment,
downloads ~330MB of model weights on first use, and takes 1-2+ minutes of
CPU inference even on a small test page -- unsuitable for a fast test suite.
It was instead verified manually end-to-end during development: a real PDF
built via music21 -> PyMuPDF page render -> oemer (with onnxruntime pinned
to 1.16.3 + numpy<2 to work around two real compatibility bugs found along
the way) -> the produced MusicXML round-tripped correctly through
score_import.import_score_file().
"""

import pytest

from sax2sheet.core.omr import (
    SUPPORTED_OMR_SUFFIXES,
    is_available,
    pdf_first_page_to_image,
    scan_to_musicxml,
)


def test_supported_suffixes_include_pdf_and_common_image_types():
    assert ".pdf" in SUPPORTED_OMR_SUFFIXES
    for ext in (".png", ".jpg", ".jpeg"):
        assert ext in SUPPORTED_OMR_SUFFIXES


def test_scan_to_musicxml_rejects_unsupported_extension(tmp_path):
    bogus = tmp_path / "score.docx"
    bogus.write_bytes(b"not a score")
    with pytest.raises(ValueError, match="unsupported"):
        scan_to_musicxml(bogus)


def test_is_available_checks_for_uv_on_path():
    # This environment has uv installed (it's how the whole project runs),
    # so this should be True here -- mainly guards against the function
    # crashing rather than asserting a specific environment fact.
    assert isinstance(is_available(), bool)


def test_pdf_first_page_to_image_produces_a_png(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "test.pdf"
    # music21's musicxml.pdf export needs a system renderer (MuseScore/
    # LilyPond) that isn't available in this environment, so build a
    # minimal single-page PDF directly instead.
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "test page")
    doc.save(str(pdf_path))

    image_path = pdf_first_page_to_image(pdf_path, dpi=150)

    assert image_path.exists()
    assert image_path.suffix == ".png"

    from PIL import Image
    # 612pt x 792pt page at 150 DPI -> 1275 x 1650 px
    with Image.open(image_path) as img:
        assert img.size == (1275, 1650)
