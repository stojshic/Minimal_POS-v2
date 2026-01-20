"""
PDF utilities for invoice generation
Handles fonts and common PDF functions
"""
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import os

# Register fonts for Serbian characters
def register_fonts():
    """Register TTF fonts that support Serbian characters"""
    try:
        # Try to use DejaVu fonts (widely available and support Serbian)
        # You might need to adjust paths based on your system
        
        # Common font locations
        font_paths = [
            "/usr/share/fonts/TTF/DejaVuSans.ttf",  # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:\\Windows\\Fonts\\DejaVuSans.ttf",  # Windows (if installed)
            "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",  # macOS
        ]
        
        # Try to find and register DejaVu Sans
        for font_path in font_paths:
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('DejaVu', font_path))
                print(f"✅ Registered font: {font_path}")
                return True
        
        # Fallback: use built-in Helvetica (limited Serbian support)
        print("⚠️  DejaVu font not found, using Helvetica (may not display Serbian correctly)")
        return False
        
    except Exception as e:
        print(f"❌ Error registering fonts: {e}")
        return False

# Common measurements
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_LEFT = 20 * mm
MARGIN_RIGHT = 20 * mm
MARGIN_TOP = 20 * mm
MARGIN_BOTTOM = 20 * mm

# Fonts
FONT_NORMAL = "DejaVu"
FONT_FALLBACK = "Helvetica"

def get_font():
    """Get the appropriate font (DejaVu if available, else Helvetica)"""
    try:
        pdfmetrics.getFont(FONT_NORMAL)
        return FONT_NORMAL
    except:
        return FONT_FALLBACK