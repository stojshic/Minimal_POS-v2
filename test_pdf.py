"""
Test PDF generation with ReportLab
"""
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pdf_utils import register_fonts, get_font, PAGE_HEIGHT, PAGE_WIDTH, MARGIN_LEFT

def test_pdf():
    """Generate a simple test PDF"""
    
    register_fonts()
    font=get_font()

    # Create PDF
    c = canvas.Canvas("test_invoice.pdf", pagesize=A4)
    
    # Add text with Serbian font
    c.setFont(font, 20)
    c.drawString(MARGIN_LEFT, PAGE_HEIGHT - 100, "TEST FAKTURA")

    c.setFont(font, 12)
    c.drawString(MARGIN_LEFT, PAGE_HEIGHT - 150, "Serbian characters: ČčĆćŠšĐđŽž")
    c.drawString(MARGIN_LEFT, PAGE_HEIGHT - 170, "Numbers: 1234567890")
    c.drawString(MARGIN_LEFT, PAGE_HEIGHT - 190, "Currency: 1.234,56 RSD")
    
    # Draw a line
    c.line(MARGIN_LEFT, PAGE_HEIGHT - 220, PAGE_WIDTH - MARGIN_LEFT, PAGE_HEIGHT - 220)
    
    # Save
    c.save()
    print("✅ PDF created: test_invoice.pdf")

if __name__ == "__main__":
    test_pdf()