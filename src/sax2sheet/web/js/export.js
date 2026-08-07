// Client-side SVG -> PDF export (jsPDF + svg2pdf.js). The exported PDF is
// built directly from the same <svg> the staff view rendered, so what you
// verify on screen is exactly what ends up in the PDF -- no second
// rendering path to drift out of sync.
async function exportStaffToPdf(container, filename = "score.pdf") {
  const svgEl = container.querySelector("svg");
  if (!svgEl) throw new Error("No rendered staff to export -- render the staff first.");

  const { jsPDF } = window.jspdf;

  const widthPx = parseFloat(svgEl.getAttribute("width")) || 800;
  const heightPx = parseFloat(svgEl.getAttribute("height")) || 200;
  const pxToPt = 72 / 96; // 96px/in source -> 72pt/in PDF
  const pdfWidth = widthPx * pxToPt;
  const pdfHeight = heightPx * pxToPt;

  const doc = new jsPDF({
    orientation: pdfWidth > pdfHeight ? "landscape" : "portrait",
    unit: "pt",
    format: [pdfWidth, pdfHeight],
  });
  await doc.svg(svgEl, { x: 0, y: 0, width: pdfWidth, height: pdfHeight });
  doc.save(filename);
}
