"""
Exports Sheet1 (Inventory) as a PDF and emails it to the specified address.
Called when the manager sends: EXPORT to someone@example.com
"""

import os
import smtplib
import io
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from config import GMAIL_SENDER, GMAIL_APP_PASSWORD
from sheets import inv_sheet


def build_pdf() -> bytes:
    """Reads Sheet1 and returns a PDF as bytes."""
    rows = inv_sheet.get_all_values()
    if not rows:
        raise ValueError("Sheet1 is empty.")

    headers = rows[0]   # ["#", "Item", "Unit", "Quantity", "Last Updated"]
    data_rows = rows[1:]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15*mm,
        rightMargin=15*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
    )

    styles = getSampleStyleSheet()
    elements = []

    # Title
    title = Paragraph(
        f"<b>Warehouse Inventory Report</b>",
        styles["Title"]
    )
    elements.append(title)

    # Timestamp
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subtitle = Paragraph(f"Generated: {ts}", styles["Normal"])
    elements.append(subtitle)
    elements.append(Spacer(1, 8*mm))

    # Table data
    table_data = [headers] + data_rows

    col_widths = [15*mm, 60*mm, 30*mm, 30*mm, 55*mm]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#2c5f2e")),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 10),
        ("ALIGN",       (0, 0), (-1, 0), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        # Data rows
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f9f2")]),
        ("ALIGN",       (0, 1), (0, -1), "CENTER"),   # # column
        ("ALIGN",       (2, 1), (3, -1), "CENTER"),   # Unit + Qty columns
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING",  (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
    ]))

    elements.append(table)

    # Row count footer
    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(f"Total items: {len(data_rows)}", styles["Normal"]))

    doc.build(elements)
    return buf.getvalue()


def send_export_email(to_email: str) -> str:
    """Builds the PDF and emails it. Returns a status message string."""
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        return "❌ Email not configured. Set GMAIL_SENDER and GMAIL_APP_PASSWORD in Render."

    try:
        pdf_bytes = build_pdf()
    except ValueError as e:
        return f"❌ Export failed: {e}"

    ts_label = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"inventory_{ts_label}.pdf"

    # Build email
    msg = MIMEMultipart()
    msg["From"] = GMAIL_SENDER
    msg["To"] = to_email
    msg["Subject"] = f"Warehouse Inventory Export — {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    body = (
        "Please find the current warehouse inventory report attached.\n\n"
        f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "— Warehouse Bot"
    )
    msg.attach(MIMEText(body, "plain"))

    # Attach PDF
    part = MIMEBase("application", "octet-stream")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    # Send via Gmail SMTP (port 587 with STARTTLS — port 465 is blocked on Render)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, to_email, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        return "❌ Gmail authentication failed. Check GMAIL_APP_PASSWORD in Render."
    except Exception as e:
        return f"❌ Failed to send email: {e}"

    return (
        f"✅ Inventory exported and sent to *{to_email}*.\n"
        f"  File: `{filename}`"
    )
