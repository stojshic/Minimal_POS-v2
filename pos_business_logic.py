"""
Business logic layer for POS system
Pure business rules - no UI dependencies
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime
from receipt_printer import FiscalReceipt
from config import STORE_CONFIG


@dataclass
class PaymentInfo:
    """Payment information for sale"""
    payment_type: str # 'cash', 'card' or 'split'
    cash_amount: float = 0.0
    card_amount: float = 0.0
    amount_tendered: float = 0.0 # How much customer gave (for cach)
    change_given: float = 0.0 # Chagnge returned


@dataclass
class SaleResult:
    """Result of a sale operation"""
    success: bool
    message: str
    remaining_quantity: Optional[float] = None
    sale_id: Optional[int] = None
    payment_info: Optional['PaymentInfo'] = None


@dataclass
class InvoiceItem:
    """Item to be added to invoice"""
    item_name: str
    price: float
    quantity: float
    barcode: Optional[str] = None


class POSService:
    """Main business logic service for POS operations"""
    
    def __init__(self, inventory_repo, sales_repo, invoice_repo, payment_repo, receipt_repo):
        self.inventory = inventory_repo
        self.sales = sales_repo
        self.invoices = invoice_repo
        self.payments = payment_repo
        self.receipts = receipt_repo
        self.fiscal_printer = FiscalReceipt(STORE_CONFIG)
    
    def sell_item(self, item_id: int, quantity: float,
                  payment_info: Optional[PaymentInfo] = None,
                  allow_oversell: bool = False) -> SaleResult:
        """
        Sell an item from inventory
        
        Args:
            item_id: ID of item to sell
            quantity: Quantity to sell
            allow_oversell: If True, allow selling more than available stock
            
        Returns:
            SaleResult with success status and details
        """
        # Get item from inventory
        item = self.inventory.get_by_id(item_id)
        if not item:
            return SaleResult(
                success=False,
                message=f"Item with ID {item_id} not found"
            )
        
        # Check stock availability
        current_qty = item['quantity']
        if current_qty < quantity and not allow_oversell:
            return SaleResult(
                success=False,
                message=f"Insufficient stock. Available: {current_qty}, Requested: {quantity}",
                remaining_quantity=current_qty
            )
        
        # Record the sale with payment info
        amount_paid = None
        change = None
        
        if payment_info:
            if payment_info.payment_type == 'cash':
                amount_paid = payment_info.amount_tendered
                change = payment_info.change_given
            elif payment_info.payment_type == 'card':
                amount_paid = item['price'] * quantity
                change = 0.0
            elif payment_info.payment_type == 'split':
                amount_paid = payment_info.cash_amount + payment_info.card_amount
                change = payment_info.change_given
        
        sale_id = self.sales.record_sale(
            item=item['item'],
            price=item['price'],
            quantity=quantity,
            amount_paid=amount_paid,
            change_given=change
        )
        
        # Record payment method(s)
        if payment_info:
            if payment_info.payment_type == 'split':
                # Split payment - record both
                self.payments.record_payment(sale_id, 'cash', payment_info.cash_amount)
                self.payments.record_payment(sale_id, 'card', payment_info.card_amount)
            else:
                # Single payment method
                total = item['price'] * quantity
                self.payments.record_payment(sale_id, payment_info.payment_type, total) 
        
        # Update inventory
        self.inventory.update_quantity(item_id, -quantity)

        # Generate and print receipt if payment info provided
        receipt_text = None
        if payment_info:
            receipt_text = self.generate_and_print_receipt(
                sale_id=sale_id,
                item_data={
                    'item': item['item'],
                    'price': item['price'],
                    'quantity': quantity,
                    'vat_rate': item.get('vat_rate', 0.20)
                },
                payment_info=payment_info
            )
            # Print to screen
            print("\n" + "=" * 50)
            print("FISKALNI RAČUN")
            print("=" * 50)
            print(receipt_text)
        
        return SaleResult(
            success=True,
            message=f"Sold {quantity}x {item['item']}",
            remaining_quantity=current_qty - quantity,
            sale_id=sale_id,
            payment_info=payment_info
        )

    def sell_multiple_items(self, items: List[dict], payment_info: PaymentInfo,
                            allow_oversell: bool = False) -> SaleResult:
        """
        Sell multiple items in one transaction

        Args:
            items: List of dicts with 'id', 'quantity'
            payment_info: Payment details
            allow_oversell: Allow selling out of stock items

        Returns:
            SaleResult for the transaction
        """
        from datetime import datetime

        # Validate all items first
        all_items_data = []
        total_amount = 0.0

        for cart_item in items:
            item = self.inventory.get_by_id(cart_item['id'])
            if not item:
                return SaleResult(
                    success=False,
                    message=f"Item ID {cart_item['id']} not found"
                )

            # Check stock
            if item['quantity'] < cart_item['quantity'] and not allow_oversell:
                return SaleResult(
                    success=False,
                    message=f"Insufficient stock for {item['item']}. Available: {item['quantity']}",
                    remaining_quantity=item['quantity']
                )

            item_total = item['price'] * cart_item['quantity']
            total_amount += item_total

            all_items_data.append({
                'id': item['id'],
                'item': item['item'],
                'price': item['price'],
                'quantity': cart_item['quantity'],
                'vat_rate': item.get('vat_rate', 0.20),
                'total': item_total
            })

        # Record each sale
        sale_ids = []
        for item_data in all_items_data:
            # Record sale (but don't generate receipt yet)
            sale_id = self.sales.record_sale(
                item=item_data['item'],
                price=item_data['price'],
                quantity=item_data['quantity'],
                amount_paid=None,  # Will update for first item only
                change_given=None
            )
            sale_ids.append(sale_id)

            # Update inventory
            self.inventory.update_quantity(item_data['id'], -item_data['quantity'])

        # Record payment for the transaction
        if payment_info.payment_type == 'split':
            self.payments.record_payment(sale_ids[0], 'cash', payment_info.cash_amount)
            self.payments.record_payment(sale_ids[0], 'card', payment_info.card_amount)
        else:
            self.payments.record_payment(sale_ids[0], payment_info.payment_type, total_amount)

        # Generate ONE receipt for all items
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        sale_data = {
            'sale_id': sale_ids[0],  # Use first sale ID
            'timestamp': timestamp,
            'items': all_items_data,  # All items in one receipt
            'payment_info': {
                'payment_type': payment_info.payment_type,
                'cash_amount': payment_info.cash_amount,
                'card_amount': payment_info.card_amount,
                'amount_tendered': payment_info.amount_tendered,
                'change_given': payment_info.change_given,
            }
        }

        # Generate and save receipt
        receipt_text = self.fiscal_printer.generate_receipt(sale_data)
        self.receipts.save_receipt(
            sale_id=sale_ids[0],
            receipt_number=self.fiscal_printer.receipt_counter - 1,
            receipt_text=receipt_text
        )

        return SaleResult(
            success=True,
            message=f"Sold {len(items)} items",
            sale_id=sale_ids[0],
            payment_info=payment_info
        )

    def search_inventory(self, search_term: str = "") -> List[dict]:
        """Search inventory items"""
        return self.inventory.search(search_term)
    
    def get_inventory_item(self, item_id: int) -> Optional[dict]:
        """Get single inventory item"""
        return self.inventory.get_by_id(item_id)
    
    def find_item_by_barcode(self, barcode: str) -> Optional[dict]:
        """
        Look up item by barcode - this is what gets called when scanner record_sale
        
        Args:
            barcode: The scanned barcode string


        Returns:
            Item dict if found, None if not found
        """
        return self.inventory.get_by_barcode(barcode)

    def sell_item_by_barcode(self, barcode: str, quantity: float = 1.0, 
                             payment_info: Optional[PaymentInfo] = None,
                             allow_oversell: bool = False) -> SaleResult:
        """
        Sell item using barcode instead of ID
 
        Args:
            barcode: Scanned barcode
            quantity: How many to sell (default 1)
            allow_oversell: Allow selling when out of stock
        
        Returns:
            SaleResult with success/failure info
        """
        # Find item by barcode
        item = self.inventory.get_by_barcode(barcode)

        if not item:
            return SaleResult(
                success = False,
                message = f"Barcode '{barcode}' not found in system"
            )
        # Use existing sell_item logic
        return self.sell_item(item['id'], quantity, payment_info, allow_oversell)

    def search_sales(self, search_term: str) -> List[dict]:
        """Search sales history"""
        return self.sales.search_sales(search_term)
    
    def get_recent_sales(self, limit: int = 10) -> List[dict]:
        """Get recent sales"""
        return self.sales.get_recent_sales(limit)
    
    def find_or_create_inventory_item(self, item_name: str) -> Tuple[Optional[int], List[dict]]:
        """
        Search for existing item by name
        Returns: (suggested_id, matching_items)
        """
        matches = self.inventory.search(item_name)
        
        if len(matches) == 1:
            # Exact or close match - suggest it
            return matches[0]['id'], matches
        
        return None, matches
    
    def add_or_update_inventory(
        self, 
        item_name: str, 
        price: float, 
        quantity: float,
        item_id: Optional[int] = None,
        barcode: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        """
        Add new item or update existing
        
        Returns: (success, message, item_id)
        """
        if item_id:
            # Update existing item
            success = self.inventory.update(item_id, price, quantity)
            if success:
                return True, f"Updated {item_name}", item_id
            return False, f"Failed to update item {item_id}", item_id
        else:
            # Add new item
            new_id = self.inventory.add(item_name, price, quantity, barcode)
            return True, f"Added new item: {item_name}", new_id
    
    def create_invoice_from_items(
        self, 
        invoice_number: str, 
        items: List[InvoiceItem]
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Create invoice and add items to inventory
        
        Returns: (success, message, invoice_id)
        """
        if not items:
            return False, "No items provided", None
        
        # Create invoice header
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y")
        time_str = now.strftime("%H:%M")
        
        try:
            invoice_id = self.invoices.create_invoice(invoice_number, date_str, time_str)
            
            # Process each item
            for item in items:
                # Add to invoice
                self.invoices.add_invoice_item(
                    invoice_id=invoice_id,
                    item=item.item_name,
                    price=item.price,
                    quantity=item.quantity
                )
                
                # Update inventory
                matches = self.inventory.search(item.item_name)
                if matches and matches[0]['item'].lower() == item.item_name.lower():
                    # Exact match - update
                    self.inventory.update(matches[0]['id'], item.price, item.quantity)
                else:
                    # Add new
                    self.inventory.add(item.item_name, item.price, item.quantity, item.barcode)
            
            return True, f"Invoice {invoice_number} created successfully", invoice_id
            
        except Exception as e:
            return False, f"Error creating invoice: {str(e)}", None
    
    def get_all_invoices(self) -> List[dict]:
        """Get all invoices"""
        return self.invoices.get_all_invoices()
    
    def get_invoice_details(self, invoice_id: int) -> Optional[dict]:
        """Get complete invoice details"""
        return self.invoices.get_invoice_details(invoice_id)

    def generate_and_print_receipt(self, sale_id: int, item_data: dict, payment_info: PaymentInfo) -> str:
        """
        Generate fiscal receipt for a sale

        Args:
            sale_id: ID of the sale
            item_data: Item details (name, price, quantity, vat_rate)
            payment_info: Payment information

        Returns:
            Receipt text
        """
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        # Prepare sale data for receipt
        sale_data = {
            'sale_id': sale_id,
            'timestamp': timestamp,
            'items': [item_data],  # Single item (can extend to multiple items per sale)
            'payment_info': {
                'payment_type': payment_info.payment_type,
                'cash_amount': payment_info.cash_amount,
                'card_amount': payment_info.card_amount,
                'amount_tendered': payment_info.amount_tendered,
                'change_given': payment_info.change_given,
            }
        }

        # Generate receipt
        receipt_text = self.fiscal_printer.generate_receipt(sale_data)

        # Save to database
        self.receipts.save_receipt(
            sale_id=sale_id,
            receipt_number=self.fiscal_printer.receipt_counter - 1,  # Counter already incremented
            receipt_text=receipt_text
        )

        return receipt_text


class ReportService:
    """Service for generating reports"""
    
    def __init__(self, inventory_repo, sales_repo):
        self.inventory = inventory_repo
        self.sales = sales_repo
    
    def low_stock_report(self, threshold: float = 10.0) -> List[dict]:
        """Get items below stock threshold"""
        all_items = self.inventory.get_all()
        return [item for item in all_items if item['quantity'] < threshold]
    
    def inventory_value_report(self) -> dict:
        """Calculate total inventory value"""
        all_items = self.inventory.get_all()
        total_value = sum(item['price'] * item['quantity'] for item in all_items)
        return {
            "total_items": len(all_items),
            "total_value": total_value,
            "items": all_items
        }
    
    def sales_summary(self, limit: int = 100) -> dict:
        """Get sales summary"""
        recent_sales = self.sales.get_recent_sales(limit)
        total_revenue = sum(sale['total'] for sale in recent_sales)
        total_items_sold = sum(sale['quantity'] for sale in recent_sales)
        
        return {
            "total_sales": len(recent_sales),
            "total_revenue": total_revenue,
            "total_items_sold": total_items_sold,
            "sales": recent_sales
        }


class DailyReportService:
    """Service for generating daily reports"""

    def __init__(self, sales_repo, payment_repo, inventory_repo):
        self.sales = sales_repo
        self.payments = payment_repo
        self.inventory = inventory_repo

    def generate_daily_report(self, date: str) -> dict:
        """
        Generate comprehensive daily report

        Args:
            date: Date in format 'YYYY-MM-DD'

        Returns:
            Dict containing all report data
        """
        sales = self.sales.get_sales_by_date(date)
        payment_summary = self.payments.get_payment_summary_by_date(date)

        if not sales:
            return {
                'date': date,
                'has_sales': False,
                'message': 'Nema prodaje za ovaj datum'
            }

        # Calculate basic stats
        total_revenue = sum(sale['total'] for sale in sales)
        total_transactions = len(sales)
        total_items_sold = sum(sale['quantity'] for sale in sales)

        # Calculate VAT breakdown
        vat_summary = {}
        for sale in sales:
            # Get item to find VAT rate (simplified - assumes we can lookup)
            vat_rate = 0.20  # Default, should lookup from inventory

            if vat_rate not in vat_summary:
                vat_summary[vat_rate] = {'base': 0, 'vat': 0, 'total': 0}

            base = sale['total'] / (1 + vat_rate)
            vat = sale['total'] - base

            vat_summary[vat_rate]['base'] += base
            vat_summary[vat_rate]['vat'] += vat
            vat_summary[vat_rate]['total'] += sale['total']

        # Top selling items
        item_sales = {}
        for sale in sales:
            item_name = sale['item']
            if item_name not in item_sales:
                item_sales[item_name] = {'quantity': 0, 'revenue': 0}

            item_sales[item_name]['quantity'] += sale['quantity']
            item_sales[item_name]['revenue'] += sale['total']

        # Sort by revenue
        top_items = sorted(
            item_sales.items(),
            key=lambda x: x[1]['revenue'],
            reverse=True
        )[:10]  # Top 10

        # Hourly breakdown
        hourly_sales = {}
        for sale in sales:
            # Extract hour from timestamp (format: 'YYYY-MM-DD HH:MM:SS')
            hour = sale['time'].split()[1].split(':')[0]  # Get HH

            if hour not in hourly_sales:
                hourly_sales[hour] = {'transactions': 0, 'revenue': 0}

            hourly_sales[hour]['transactions'] += 1
            hourly_sales[hour]['revenue'] += sale['total']

        # Calculate average transaction
        avg_transaction = total_revenue / total_transactions if total_transactions > 0 else 0

        return {
            'date': date,
            'has_sales': True,
            'summary': {
                'total_revenue': total_revenue,
                'total_transactions': total_transactions,
                'total_items_sold': total_items_sold,
                'avg_transaction': avg_transaction,
            },
            'payments': payment_summary,
            'vat_breakdown': vat_summary,
            'top_items': top_items,
            'hourly_sales': sorted(hourly_sales.items()),
            'sales_detail': sales
        }

    def generate_cash_reconciliation(self, date: str, actual_cash_in_drawer: float) -> dict:
        """
        Compare expected cash with actual counted cash

        Args:
            date: Date in format 'YYYY-MM-DD'
            actual_cash_in_drawer: Amount counted in cash drawer

        Returns:
            Reconciliation report
        """
        payment_summary = self.payments.get_payment_summary_by_date(date)
        expected_cash = payment_summary['cash']

        # Get all cash sales to calculate change given
        sales = self.sales.get_sales_by_date(date)
        total_change_given = sum(
            sale.get('change_given', 0) or 0
            for sale in sales
            if sale.get('change_given')
        )

        difference = actual_cash_in_drawer - expected_cash

        return {
            'date': date,
            'expected_cash': expected_cash,
            'actual_cash': actual_cash_in_drawer,
            'difference': difference,
            'total_change_given': total_change_given,
            'is_balanced': abs(difference) < 0.01  # Within 1 dinar
        }


class UserService:
    """Service for user management and authentication"""

    def __init__(self, user_repo):
        self.users = user_repo

    def login(self, username: str, password: str) -> Tuple[bool, Optional[dict], str]:
        """
        Authenticate user

        Returns:
            (success, user_dict, message)
        """
        if not username or not password:
            return False, None, "Korisničko ime i lozinka su obavezni!"

        user = self.users.authenticate(username, password)

        if user:
            return True, user, f"Dobrodošli, {user['full_name']}!"
        else:
            return False, None, "Pogrešno korisničko ime ili lozinka!"

    def create_cashier(self, username: str, password: str, full_name: str) -> Tuple[bool, str]:
        """
        Create new cashier user (admin only)

        Returns:
            (success, message)
        """
        if len(password) < 3:
            return False, "Lozinka mora imati najmanje 3 karaktera"

        try:
            user_id = self.users.create_user(username, password, full_name, "cashier")
            return True, f"Korisnik {username} uspešno kreiran"
        except Exception as e:
            return False, f"Greška: {str(e)}"

    def get_all_users(self) -> List[dict]:
        """Get all users (admin only)"""
        return self.users.get_all_users()

    def change_password(self, user_id: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        Change user's own password

        Returns:
            (success, message)
        """
        if len(new_password) < 3:
            return False, "Lozinka mora imati najmanje 3 karaktera"

        # Verify old passowrd first
        # TODO: Add Verification

        success = self.users.update_password(user_id, new_password)
        if success:
            return True, "Lozinka uspešno promenjena"
        else:
            return False, "Greška pri promeni lozinke"