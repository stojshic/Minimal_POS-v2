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

        # Customer info (if provided)
        customer_info = sale_data.get('customer_info')
        if customer_info:
            receipt.append("")
            receipt.append("KUPAC:")
            customer_name = customer_info.get('company_name') or customer_info.get('name', '')
            receipt.append(f"  {customer_name[:36]}")
            if customer_info.get('address'):
                receipt.append(f"  {customer_info['address'][:36]}")
            tax_id_type = customer_info.get('tax_id_type', 'pib')
            if tax_id_type == 'pib' and customer_info.get('pib'):
                receipt.append(f"  PIB: {customer_info['pib']}")
            elif tax_id_type == 'jmbg' and customer_info.get('jmbg'):
                receipt.append(f"  JMBG: {customer_info['jmbg']}")
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


class OrderTicketPrinter:
    """Generates order tickets for kitchen and bar"""

    def __init__(self, width: int = 32):
        """
        Initialize ticket printer

        Args:
            width: Character width for ticket (default 32 for small thermal printers)
        """
        self.width = width

    def generate_ticket(
        self,
        table_name: str,
        orders: List[Dict],
        ticket_type: str = "all",
        waiter_name: str = None
    ) -> str:
        """
        Generate an order ticket for kitchen or bar

        Args:
            table_name: Name of the table (e.g., "Sto 1")
            orders: List of order dicts with item_name, quantity, notes, item_type
            ticket_type: "kitchen" (food only), "bar" (drinks only), or "all"
            waiter_name: Optional waiter name

        Returns:
            Formatted ticket text
        """
        # Filter orders by type if specified
        if ticket_type == "kitchen":
            filtered_orders = [o for o in orders if o.get('item_type') == 'food']
            header = "KUHINJA"
        elif ticket_type == "bar":
            filtered_orders = [o for o in orders if o.get('item_type') == 'drink']
            header = "ŠANK"
        else:
            filtered_orders = orders
            header = "PORUDŽBINA"

        if not filtered_orders:
            return ""

        ticket = []
        ticket.append("=" * self.width)
        ticket.append(header.center(self.width))
        ticket.append("=" * self.width)
        ticket.append("")
        ticket.append(f"Sto: {table_name}".center(self.width))
        ticket.append(f"{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}".center(self.width))
        if waiter_name:
            ticket.append(f"Konobar: {waiter_name}".center(self.width))
        ticket.append("")
        ticket.append("-" * self.width)

        # List items
        for order in filtered_orders:
            qty = order.get('quantity', 1)
            qty_str = f"{int(qty)}x" if qty == int(qty) else f"{qty:.1f}x"
            item_name = order.get('item_name', 'Unknown')

            # Truncate long names
            max_item_len = self.width - len(qty_str) - 1
            if len(item_name) > max_item_len:
                item_name = item_name[:max_item_len - 3] + "..."

            ticket.append(f"{qty_str} {item_name}")

            # Add notes if present
            notes = order.get('notes', '')
            if notes:
                # Indent notes and wrap if needed
                notes_prefix = "   >> "
                max_notes_len = self.width - len(notes_prefix)
                if len(notes) > max_notes_len:
                    notes = notes[:max_notes_len - 3] + "..."
                ticket.append(f"{notes_prefix}{notes}")

        ticket.append("-" * self.width)
        ticket.append(f"Ukupno stavki: {len(filtered_orders)}".center(self.width))
        ticket.append("=" * self.width)

        return "\n".join(ticket)

    def generate_kitchen_ticket(
        self,
        table_name: str,
        orders: List[Dict],
        waiter_name: str = None
    ) -> str:
        """Generate ticket for kitchen (food items only)"""
        return self.generate_ticket(table_name, orders, "kitchen", waiter_name)

    def generate_bar_ticket(
        self,
        table_name: str,
        orders: List[Dict],
        waiter_name: str = None
    ) -> str:
        """Generate ticket for bar (drink items only)"""
        return self.generate_ticket(table_name, orders, "bar", waiter_name)

    def generate_combined_ticket(
        self,
        table_name: str,
        orders: List[Dict],
        waiter_name: str = None
    ) -> str:
        """
        Generate separate tickets for kitchen and bar combined

        Returns both tickets concatenated with a separator
        """
        kitchen_ticket = self.generate_kitchen_ticket(table_name, orders, waiter_name)
        bar_ticket = self.generate_bar_ticket(table_name, orders, waiter_name)

        # Handle "other" type items - include in a general ticket
        other_orders = [o for o in orders if o.get('item_type') not in ('food', 'drink')]
        other_ticket = ""
        if other_orders:
            other_ticket = self.generate_ticket(table_name, other_orders, "all", waiter_name)

        tickets = []
        if kitchen_ticket:
            tickets.append(kitchen_ticket)
        if bar_ticket:
            tickets.append(bar_ticket)
        if other_ticket and not kitchen_ticket and not bar_ticket:
            # Only include "other" ticket if no kitchen or bar tickets
            tickets.append(other_ticket)

        if not tickets:
            # Fallback: all items together
            return self.generate_ticket(table_name, orders, "all", waiter_name)

        return "\n\n".join(tickets)