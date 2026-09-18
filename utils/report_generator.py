import csv
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

def sanitize_csv_value(val):
    if isinstance(val, str) and val.startswith(('=', '+', '-', '@')):
        return "'" + val
    return val

def generate_csv(headers, rows):
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow([sanitize_csv_value(h) for h in headers])
    cw.writerows([[sanitize_csv_value(cell) for cell in row] for row in rows])
    output = si.getvalue()
    si.close()
    return output

def generate_pdf(title, summary, headers, rows):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    styles = getSampleStyleSheet()
    elements.append(Paragraph(title, styles['Title']))
    elements.append(Spacer(1, 12))
    
    for line in summary:
        elements.append(Paragraph(line, styles['Normal']))
    elements.append(Spacer(1, 12))
    
    if not rows:
        elements.append(Paragraph("No records found.", styles['Normal']))
    else:
        # Table data
        data = [headers] + rows
        t = Table(data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 1, colors.silver)
        ]))
        elements.append(t)
        
    doc.build(elements)
    
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
