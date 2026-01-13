"""
Serbian fiscal receipt generator
"""
from datetime import datetime
from typing import List, Dict
import qrcode
from io import BytesIO


class FiscalReceipt:
    """Generates Serbian fiscal receipts"""

    def __init__(self, store_config: dict):
        self.config = store_config
        self.receipt_counter = 1 # Should be stored in DB in production

    def generate_qr_ascii(self, data: str) -> str:
        """Generate ASCII art QR code for terminal display"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # Get the QR matrix
        matrix = qr.get_matrix()

        # Convert to ASCII using unicode blocks
        ascii_qr = []
        for row in matrix:
            line = ""
            for cell in row:
                line += "██" if cell else "  "
            ascii_qr.append(line)

        return "\n".join(ascii_qr)

    def generate_receipt(self, sale_data: dict) -> str:
        """
        Generate fiscal receipt text

        Args:
            sale_data: Dict containing:
                - items: List of sold items with prices, quantities, VAT
                - payment_info: Payment details (cash/card/split)
                - sale_id: Transaction ID
                - timestamp: When sale occurred
        """
        receipt = []

        # Header - Store info
        receipt.append("=" * 40)
        receipt.append(self.config['name'].center(40))
        receipt.append(self.config['address'].center(40))
        receipt.append(f"PIB: {self.config['pib']}".center(40))
        receipt.append("=" * 40)
        receipt.append("")

        # Fiscal device info
        receipt.append(f"PFR: {self.config['pfr_number']}")
        receipt.append(f"Broj računa: {self.receipt_counter:06d}")
        receipt.append(f"Kasir: {self.config['cashier']}")
        receipt.append(f"Datum: {sale_data['timestamp']}")
        receipt.append("-" * 40)


        # Items
        receipt.append("")
        receipt.append("ARTIKLI:")
        receipt.append("-" * 40)

        total_by_vat = {}
        grand_total = 0

        for item in sale_data['items']:
            name = item['item']
            qty = item['quantity']
            price = item['price']
            vat_rate = item.get('vat_rate', 0.20)

            # Calculate line total
            line_total = price * qty
            grand_total += line_total

            # Track by VAT rate
            if vat_rate not in total_by_vat:
                total_by_vat[vat_rate] = {'base': 0, 'vat': 0, 'total': 0}

            base_price = line_total / (1 + vat_rate)
            vat_amount = line_total - base_price

            total_by_vat[vat_rate]['base'] += base_price
            total_by_vat[vat_rate]['vat'] += vat_amount
            total_by_vat[vat_rate]['total'] += line_total

            # Format item line
            receipt.append(f"{name[:25]:<25}")
            receipt.append(f"  {qty:.2f} x {price:.2f} = {line_total:>10.2f} RSD")

        receipt.append("-" * 40)

        # VAT breakdown
        receipt.append("")
        receipt.append("REKAPITULACIJA PDV:")
        receipt.append("-" * 40)
        receipt.append(f"{'Stopa':<10} {'Osnovica':<12} {'PDV':<12} {'Ukupno':<12}")

        for vat_rate in sorted(total_by_vat.keys()):
            data = total_by_vat[vat_rate]
            vat_percent = int(vat_rate * 100)
            receipt.append(
                f"{vat_percent}%{'':<7} "
                f"{data['base']:>10.2f}  "
                f"{data['vat']:>10.2f}  "
                f"{data['total']:>10.2f}"
            )

        receipt.append("-" * 40)
        receipt.append(f"{'UKUPNO:':<28} {grand_total:>10.2f} RSD")
        receipt.append("")

        # Payment info
        payment = sale_data.get('payment_info')
        if payment:
            receipt.append("NAČIN PLAĆANJA:")
            receipt.append("-" * 40)

            if payment['payment_type'] == 'cash':
                receipt.append(f"Gotovina:{'':<18} {payment['cash_amount']:>10.2f} RSD")
                receipt.append(f"Primljeno:{'':<17} {payment['amount_tendered']:>10.2f} RSD")
                receipt.append(f"Kusur:{'':<21} {payment['change_given']:>10.2f} RSD")

            elif payment['payment_type'] == 'card':
                receipt.append(f"Kartica:{'':<19} {payment['card_amount']:>10.2f} RSD")

            elif payment['payment_type'] == 'split':
                receipt.append(f"Gotovina:{'':<18} {payment['cash_amount']:>10.2f} RSD")
                receipt.append(f"Kartica:{'':<19} {payment['card_amount']:>10.2f} RSD")
                if payment['change_given'] > 0:
                    receipt.append(f"Kusur:{'':<21} {payment['change_given']:>10.2f} RSD")

        receipt.append("")
        receipt.append("=" * 40)
        receipt.append("Hvala na kupovini!".center(40))
        receipt.append("=" * 40)

        # QR code data (simplified - real fiscal QR has specific format)
        qr_data = f"PFR:{self.config['pfr_number']},ID:{sale_data['sale_id']},Total:{grand_total:.2f}"
        receipt.append("")
        receipt.append("QR KOD ZA VERIFIKACIJU:")
        receipt.append("")
        qr_ascii = self.generate_qr_ascii(qr_data)
        receipt.append(qr_ascii)

        self.receipt_counter += 1

        return "\n".join(receipt)

    def print_receipt(self, receipt_text: str):
        """
        Print receipt to printer or display
        In production, this would send to thermal printer
        """
        print("\n" + receipt_text + "\n")