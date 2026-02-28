import io
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

def build_certificate_pdf(*, certificate_no: str, issue_date: str,
                          student_name: str, usn: str, activity_type: str,
                          hours: float, points: int,
                          verify_url: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Border
    margin = 15 * mm
    c.rect(margin, margin, w - 2*margin, h - 2*margin)

    # Header
    c.setFont("Times-Bold", 18)
    c.drawCentredString(w/2, h - 40*mm, "CERTIFICATE")

    # Top line (Certificate No / Date)
    c.setFont("Times-Roman", 11)
    c.drawString(margin + 5*mm, h - 25*mm, f"Certificate No: {certificate_no}")
    c.drawRightString(w - margin - 5*mm, h - 25*mm, f"Date: {issue_date}")

    # Body
    c.setFont("Times-Roman", 13)
    y = h - 65*mm
    lines = [
        "This is to certify that",
        f"{student_name} (USN: {usn})",
        "has successfully completed the social activity",
        f"“{activity_type}”",
        f"Total Hours: {hours:.1f} hrs | Points Awarded: {points}",
    ]
    for i, line in enumerate(lines):
        font = "Times-Bold" if i in (1, 3) else "Times-Roman"
        size = 15 if i in (1, 3) else 13
        c.setFont(font, size)
        c.drawCentredString(w/2, y - i*12*mm, line)

    # Footer signatures placeholders
    c.setFont("Times-Roman", 11)
    c.drawString(margin + 10*mm, margin + 25*mm, "Faculty Signature")
    c.drawRightString(w - margin - 10*mm, margin + 25*mm, "Principal / Coordinator")

    # QR Code (bottom-right)
    qr = qrcode.QRCode(box_size=3, border=1)
    qr.add_data(verify_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    qr_buf = io.BytesIO()
    img.save(qr_buf, format="PNG")
    qr_buf.seek(0)

    qr_size = 32 * mm
    c.drawImage(qr_buf, w - margin - qr_size, margin + 10*mm, qr_size, qr_size, mask="auto")

    c.setFont("Times-Roman", 8)
    c.drawRightString(w - margin, margin + 7*mm, "Scan QR to verify")

    c.showPage()
    c.save()

    return buf.getvalue()