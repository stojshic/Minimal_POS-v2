"""
PDF Invoice Generator for POS System
Generates A4 PDF invoices with Serbian localization
"""
import os
import subprocess
import platform
from datetime import datetime
from typing import List, Dict, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from config import STORE_CONFIG


class PDFInvoiceGenerator:
    """Generates A4 PDF invoices"""

    def __init__(self, output_dir: str = "invoices"):
        self.output_dir = output_dir
        self._ensure_output_dir()
        self._register_fonts()
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _ensure_output_dir(self):
        """Create output directory if it doesn't exist"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def _register_fonts(self):
        """Register fonts with Serbian character support"""
        # Try common font paths for DejaVu (supports Serbian characters)
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]

        font_registered = False
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('Serbian', font_path))
                    font_registered = True
                    break
                except Exception:
                    continue

        if not font_registered:
            # Fallback to Helvetica (no Serbian support)
            self.font_name = 'Helvetica'
        else:
            self.font_name = 'Serbian'

    def _setup_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='InvoiceTitle',
            fontName=self.font_name,
            fontSize=16,
            alignment=1,  # Center
            spaceAfter=10
        ))
        self.styles.add(ParagraphStyle(
            name='InvoiceHeader',
            fontName=self.font_name,
            fontSize=10,
            alignment=0,  # Left
            spaceAfter=5
        ))
        self.styles.add(ParagraphStyle(
            name='InvoiceNormal',
            fontName=self.font_name,
            fontSize=9,
            alignment=0,
            spaceAfter=3
        ))

    def generate_invoice(
        self,
        sale_id: int,
        items: List[Dict],
        payment_info: Dict,
        customer_info: Optional[Dict] = None,
        timestamp: Optional[str] = None
    ) -> str:
        """
        Generate A4 PDF invoice

        Args:
            sale_id: Sale transaction ID
            items: List of sold items with price, quantity, vat_rate
            payment_info: Payment details (type, amounts)
            customer_info: Customer data (name, address, PIB/JMBG)
            timestamp: Sale timestamp

        Returns:
            Path to generated PDF file
        """
        # Generate invoice number
        now = datetime.now()
        year = now.year
        invoice_number = f"{year}-{sale_id:04d}"

        # Create filename
        filename = f"faktura_{invoice_number}.pdf"
        filepath = os.path.join(self.output_dir, filename)

        # Create document
        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )

        # Build content
        elements = []

        # Title
        elements.append(Paragraph(f"FAKTURA br. {invoice_number}", self.styles['InvoiceTitle']))
        elements.append(Spacer(1, 10*mm))

        # Store and customer info side by side
        store_customer_data = self._build_store_customer_table(customer_info)
        elements.append(store_customer_data)
        elements.append(Spacer(1, 10*mm))

        # Invoice details
        invoice_date = timestamp or now.strftime("%d.%m.%Y %H:%M")
        elements.append(Paragraph(f"Datum izdavanja: {invoice_date}", self.styles['InvoiceNormal']))
        elements.append(Spacer(1, 5*mm))

        # Items table
        items_table = self._build_items_table(items)
        elements.append(items_table)
        elements.append(Spacer(1, 5*mm))

        # VAT breakdown
        vat_table = self._build_vat_table(items)
        elements.append(vat_table)
        elements.append(Spacer(1, 5*mm))

        # Totals
        total_table = self._build_totals_table(items, payment_info)
        elements.append(total_table)
        elements.append(Spacer(1, 10*mm))

        # Payment info
        payment_text = self._get_payment_text(payment_info)
        elements.append(Paragraph(f"Nacin placanja: {payment_text}", self.styles['InvoiceNormal']))

        # Build PDF
        doc.build(elements)

        return filepath

    def _build_store_customer_table(self, customer_info: Optional[Dict]) -> Table:
        """Build two-column table with store and customer info"""
        # Store info
        store_lines = [
            f"<b>{STORE_CONFIG['name']}</b>",
            STORE_CONFIG['address'],
            f"PIB: {STORE_CONFIG['pib']}",
        ]
        store_text = '<br/>'.join(store_lines)

        # Customer info
        if customer_info:
            customer_name = customer_info.get('company_name') or customer_info.get('name', '')
            customer_lines = [f"<b>KUPAC:</b>", customer_name]

            # Add address if available
            if customer_info.get('address'):
                addr = customer_info['address']
                if customer_info.get('city'):
                    addr += f", {customer_info['city']}"
                customer_lines.append(addr)

            # Add tax ID based on type
            tax_id_type = customer_info.get('tax_id_type', 'pib')
            if tax_id_type == 'pib' and customer_info.get('pib'):
                customer_lines.append(f"PIB: {customer_info['pib']}")
            elif tax_id_type == 'jmbg' and customer_info.get('jmbg'):
                customer_lines.append(f"JMBG: {customer_info['jmbg']}")

            customer_text = '<br/>'.join(customer_lines)
        else:
            customer_text = "<b>KUPAC:</b><br/>Fizicko lice"

        data = [[
            Paragraph(store_text, self.styles['InvoiceNormal']),
            Paragraph(customer_text, self.styles['InvoiceNormal'])
        ]]

        table = Table(data, colWidths=[85*mm, 85*mm])
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))

        return table

    def _build_items_table(self, items: List[Dict]) -> Table:
        """Build items table"""
        # Header
        header = ['R.br.', 'Naziv artikla', 'Kol.', 'Cena', 'PDV %', 'Ukupno']

        data = [header]

        for idx, item in enumerate(items, 1):
            vat_rate = item.get('vat_rate', 0.20)
            vat_percent = int(vat_rate * 100)
            line_total = item['price'] * item['quantity']

            row = [
                str(idx),
                item['item'],
                f"{item['quantity']:.2f}",
                f"{item['price']:.2f}",
                f"{vat_percent}%",
                f"{line_total:.2f}"
            ]
            data.append(row)

        table = Table(data, colWidths=[15*mm, 70*mm, 20*mm, 25*mm, 20*mm, 25*mm])
        table.setStyle(TableStyle([
            # Header style
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), self.font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            # Body style
            ('FONTNAME', (0, 1), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # R.br.
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),   # Numbers right-aligned
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        return table

    def _build_vat_table(self, items: List[Dict]) -> Table:
        """Build VAT breakdown table"""
        # Calculate VAT by rate
        vat_summary = {}
        for item in items:
            vat_rate = item.get('vat_rate', 0.20)
            line_total = item['price'] * item['quantity']
            base = line_total / (1 + vat_rate)
            vat = line_total - base

            if vat_rate not in vat_summary:
                vat_summary[vat_rate] = {'base': 0, 'vat': 0, 'total': 0}

            vat_summary[vat_rate]['base'] += base
            vat_summary[vat_rate]['vat'] += vat
            vat_summary[vat_rate]['total'] += line_total

        # Build table
        header = ['PDV stopa', 'Osnovica', 'PDV iznos', 'Sa PDV']
        data = [header]

        for rate in sorted(vat_summary.keys()):
            vals = vat_summary[rate]
            row = [
                f"{int(rate * 100)}%",
                f"{vals['base']:.2f}",
                f"{vals['vat']:.2f}",
                f"{vals['total']:.2f}"
            ]
            data.append(row)

        table = Table(data, colWidths=[30*mm, 40*mm, 40*mm, 40*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))

        return table

    def _build_totals_table(self, items: List[Dict], payment_info: Dict) -> Table:
        """Build totals table"""
        grand_total = sum(item['price'] * item['quantity'] for item in items)

        # Calculate total VAT
        total_vat = 0
        total_base = 0
        for item in items:
            vat_rate = item.get('vat_rate', 0.20)
            line_total = item['price'] * item['quantity']
            base = line_total / (1 + vat_rate)
            total_base += base
            total_vat += line_total - base

        data = [
            ['Osnovica ukupno:', f"{total_base:.2f} RSD"],
            ['PDV ukupno:', f"{total_vat:.2f} RSD"],
            ['ZA UPLATU:', f"{grand_total:.2f} RSD"],
        ]

        table = Table(data, colWidths=[100*mm, 50*mm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, 1), 9),
            ('FONTSIZE', (0, 2), (-1, 2), 12),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 2), (-1, 2), self.font_name),
            ('BACKGROUND', (0, 2), (-1, 2), colors.lightgrey),
        ]))

        return table

    def _get_payment_text(self, payment_info: Dict) -> str:
        """Get payment method text"""
        payment_type = payment_info.get('payment_type', 'cash')

        if payment_type == 'cash':
            return "Gotovina"
        elif payment_type == 'card':
            return "Kartica"
        elif payment_type == 'split':
            cash = payment_info.get('cash_amount', 0)
            card = payment_info.get('card_amount', 0)
            return f"Kombinovano (Gotovina: {cash:.2f} RSD, Kartica: {card:.2f} RSD)"
        return "Nepoznato"

    def open_pdf(self, filepath: str):
        """Open PDF in system default viewer"""
        try:
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', filepath])
            elif platform.system() == 'Windows':
                os.startfile(filepath)
            else:  # Linux
                subprocess.run(['xdg-open', filepath])
        except Exception as e:
            print(f"Could not open PDF: {e}")
