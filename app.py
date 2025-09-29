import io, os, re
from flask import Flask, request, send_file, jsonify, Response
from flask_cors import CORS
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)
CORS(app)  # allow calls from your WordPress site (front-end)

# --- tiny HTML form so you can test it in a browser ---
HTML_FORM = """<!doctype html>
<title>Merge Cover + Resume</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<div style="max-width:600px;margin:40px auto;font-family:system-ui;">
  <h2>Merge Cover Letter + Resume</h2>
  <form action="/merge" method="post" enctype="multipart/form-data">
    <label>Applicant Name (used for filename)</label><br/>
    <input type="text" name="applicant_name" placeholder="First Last" style="width:100%;" required /><br/><br/>

    <label>Cover Letter Text</label><br/>
    <textarea name="cover_text" rows="10" style="width:100%;" required></textarea><br/><br/>

    <label>Resume (PDF)</label><br/>
    <input type="file" name="resume" accept="application/pdf" required /><br/><br/>

    <button type="submit">Create Combined PDF</button>
  </form>
  <p style="margin-top:14px;color:#666">Tip: Link to this page from WordPress or call the /merge endpoint from your form.</p>
</div>"""

@app.get("/")
def home():
    return Response(HTML_FORM, mimetype="text/html")

def render_cover_page(cover_text: str, title: str = "Cover Letter") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=1*inch, rightMargin=1*inch,
        topMargin=1*inch, bottomMargin=1*inch
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleSmall", fontSize=16, leading=20, spaceAfter=12))
    styles.add(ParagraphStyle(name="Body", fontSize=11, leading=14))
    safe_text = cover_text.replace("\r\n", "<br/>").replace("\n", "<br/>")
    doc.build([Paragraph(title, styles["TitleSmall"]), Paragraph(safe_text, styles["Body"])])
    out = buf.getvalue(); buf.close()
    return out

def make_filename_from_name(raw: str) -> str:
    """
    Convert 'First Middle Last' -> 'first-last.pdf' (lowercase, no spaces).
    - Takes first and last tokens only.
    - Strips anything that's not a letter or number.
    - Falls back to 'applicant' if empty.
    """
    # Grab alphanumeric tokens (handles simple names). Accents may be kept by browsers,
    # but this keeps filenames safe for most filesystems.
    tokens = re.findall(r"[A-Za-z0-9]+", raw.strip())
    if not tokens:
        base = "applicant"
    elif len(tokens) == 1:
        base = tokens[0]
    else:
        base = f"{tokens[0]}-{tokens[-1]}"
    return f"{base.lower()}.pdf"

@app.post("/merge")
def merge():
    try:
        # Name → filename
        applicant_name = (request.form.get("applicant_name") or "").strip()
        out_name = make_filename_from_name(applicant_name)

        # Cover text
        cover_text = (request.form.get("cover_text") or "").strip()
        if not cover_text:
            return jsonify({"error": "cover_text is required"}), 400

        # Resume
        f = request.files.get("resume")
        if not f:
            return jsonify({"error": "resume (PDF) is required"}), 400
        if not f.filename.lower().endswith(".pdf"):
            return jsonify({"error": "resume must be a PDF"}), 400

        # Build PDFs
        cover_pdf = PdfReader(io.BytesIO(render_cover_page(cover_text)))
        resume_pdf = PdfReader(f.stream)

        # Merge
        w = PdfWriter()
        for p in cover_pdf.pages: w.add_page(p)
        for p in resume_pdf.pages: w.add_page(p)

        out = io.BytesIO(); w.write(out); out.seek(0)
        return send_file(out, mimetype="application/pdf",
                         as_attachment=True, download_name=out_name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
