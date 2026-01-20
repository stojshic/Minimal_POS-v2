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
    payment_type: str  # 'cash', 'card' or 'split'
    cash_amount: float = 0.0
    card_amount: float = 0.0
    amount_tendered: float = 0.0  # How much customer gave (for cash)
    change_given: float = 0.0  # Change returned
    customer_id: Optional[int] = None  # Selected customer for invoice
    customer_tax_id_type: Optional[str] = None  # 'pib' or 'jmbg'


@dataclass
class SaleResult:
    """Result of a sale operation"""
    success: bool
    message: str
    remaining_quantity: Optional[float] = None
    sale_id: Optional[int] = None
    payment_info: Optional['PaymentInfo'] = None
    sale_items: Optional[List[dict]] = None  # Items in the sale for PDF
    customer_info: Optional[dict] = None  # Customer data for PDF invoice


@dataclass
class InvoiceItem:
    """Item to be added to invoice"""
    item_name: str
    price: float
    quantity: float
    barcode: Optional[str] = None


class POSService:
    """Main business logic service for POS operations"""

    def __init__(self, inventory_repo, sales_repo, invoice_repo,
                 customer_repo=None, unified_sales_repo=None,
                 payment_repo=None, receipt_repo=None):
        self.inventory = inventory_repo
        self.sales = sales_repo  # Old SalesRepository (for backward compat)
        self.invoices = invoice_repo
        self.payments = payment_repo  # Deprecated - only used in legacy fallback
        self.receipts = receipt_repo  # Deprecated - only used in legacy fallback
        self.customers = customer_repo
        self.unified_sales = unified_sales_repo  # New UnifiedSalesRepository
        self.fiscal_printer = FiscalReceipt(STORE_CONFIG)
    
    def sell_items(self, items: List[dict], payment_info: PaymentInfo,
                   allow_oversell: bool = False) -> SaleResult:
        """
        Sell one or more items in a single transaction.

        Args:
            items: List of dicts with 'id' and 'quantity'
            payment_info: Payment details
            allow_oversell: Allow selling out of stock items

        Returns:
            SaleResult for the transaction
        """
        from datetime import datetime

        if not items:
            return SaleResult(success=False, message="No items to sell")

        # Validate all items first
        all_items_data = []
        total_amount = 0.0
        total_vat = 0.0

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
            vat_rate = item.get('vat_rate', 0.20)
            item_vat = item_total * vat_rate / (1 + vat_rate)
            total_amount += item_total
            total_vat += item_vat

            all_items_data.append({
                'id': item['id'],
                'item': item['item'],
                'item_name': item['item'],
                'price': item['price'],
                'unit_price': item['price'],
                'quantity': cart_item['quantity'],
                'vat_rate': vat_rate,
                'item_id': item['id'],
                'total': item_total
            })

        # Look up customer if provided
        customer_info = None
        if payment_info.customer_id and self.customers:
            customer_info = self.customers.get_by_id(payment_info.customer_id)
            if customer_info:
                customer_info['tax_id_type'] = payment_info.customer_tax_id_type

        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        # Use unified sales repository if available (new structure)
        if self.unified_sales:
            receipt_number = self.unified_sales.get_next_receipt_number()

            sale_data = {
                'sale_id': None,
                'timestamp': timestamp,
                'items': all_items_data,
                'payment_info': {
                    'payment_type': payment_info.payment_type,
                    'cash_amount': payment_info.cash_amount,
                    'card_amount': payment_info.card_amount,
                    'amount_tendered': payment_info.amount_tendered,
                    'change_given': payment_info.change_given,
                },
                'customer_info': customer_info
            }

            receipt_text = self.fiscal_printer.generate_receipt(sale_data)

            sale_id = self.unified_sales.create_sale_with_items(
                receipt_number=receipt_number,
                payment_type=payment_info.payment_type,
                total_amount=total_amount,
                vat_amount=total_vat,
                items=all_items_data,
                cash_amount=payment_info.cash_amount,
                card_amount=payment_info.card_amount,
                amount_tendered=payment_info.amount_tendered,
                change_given=payment_info.change_given,
                customer_id=payment_info.customer_id,
                receipt_text=receipt_text
            )

            for item_data in all_items_data:
                self.inventory.update_quantity(item_data['id'], -item_data['quantity'])

        else:
            # Fallback to old structure (backward compatibility)
            sale_ids = []
            for item_data in all_items_data:
                sale_id = self.sales.record_sale(
                    item=item_data['item'],
                    price=item_data['price'],
                    quantity=item_data['quantity'],
                    amount_paid=None,
                    change_given=None
                )
                sale_ids.append(sale_id)
                self.inventory.update_quantity(item_data['id'], -item_data['quantity'])

            if payment_info.payment_type == 'split':
                self.payments.record_payment(sale_ids[0], 'cash', payment_info.cash_amount)
                self.payments.record_payment(sale_ids[0], 'card', payment_info.card_amount)
            else:
                self.payments.record_payment(sale_ids[0], payment_info.payment_type, total_amount)

            sale_id = sale_ids[0]

            sale_data = {
                'sale_id': sale_id,
                'timestamp': timestamp,
                'items': all_items_data,
                'payment_info': {
                    'payment_type': payment_info.payment_type,
                    'cash_amount': payment_info.cash_amount,
                    'card_amount': payment_info.card_amount,
                    'amount_tendered': payment_info.amount_tendered,
                    'change_given': payment_info.change_given,
                },
                'customer_info': customer_info
            }

            receipt_text = self.fiscal_printer.generate_receipt(sale_data)
            self.receipts.save_receipt(
                sale_id=sale_id,
                receipt_number=self.fiscal_printer.receipt_counter - 1,
                receipt_text=receipt_text
            )

        # Calculate remaining quantity for single-item sales
        remaining_qty = None
        if len(items) == 1:
            item = self.inventory.get_by_id(items[0]['id'])
            if item:
                remaining_qty = item['quantity']

        return SaleResult(
            success=True,
            message=f"Sold {len(items)} item(s)",
            sale_id=sale_id,
            payment_info=payment_info,
            sale_items=all_items_data,
            customer_info=customer_info,
            remaining_quantity=remaining_qty
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
            payment_info: Payment details (required for sale)
            allow_oversell: Allow selling when out of stock

        Returns:
            SaleResult with success/failure info
        """
        item = self.inventory.get_by_barcode(barcode)

        if not item:
            return SaleResult(
                success=False,
                message=f"Barcode '{barcode}' not found in system"
            )

        if not payment_info:
            return SaleResult(
                success=False,
                message="Payment info is required"
            )

        return self.sell_items(
            items=[{'id': item['id'], 'quantity': quantity}],
            payment_info=payment_info,
            allow_oversell=allow_oversell
        )

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

    def __init__(self, sales_repo, payment_repo, inventory_repo, unified_sales_repo=None):
        self.sales = sales_repo  # Old SalesRepository (sold_items)
        self.payments = payment_repo  # Deprecated
        self.inventory = inventory_repo
        self.unified_sales = unified_sales_repo  # New UnifiedSalesRepository

    def generate_daily_report(self, date: str) -> dict:
        """
        Generate comprehensive daily report

        Args:
            date: Date in format 'YYYY-MM-DD'

        Returns:
            Dict containing all report data
        """
        # Use unified sales if available, otherwise fall back to old structure
        if self.unified_sales:
            return self._generate_report_unified(date)
        else:
            return self._generate_report_legacy(date)

    def _generate_report_unified(self, date: str) -> dict:
        """Generate report using new unified sales table"""
        from pos_db_layer import RefundRepository

        sales_data = self.unified_sales.get_sales_with_items_by_date(date)
        payment_summary = self.unified_sales.get_payment_summary_by_date(date)
        refunds = RefundRepository(self.unified_sales.db).get_refunds_by_date(date)

        if not sales_data and not refunds:
            return {
                'date': date,
                'has_sales': False,
                'message': 'Nema prodaje niti povraćaja za ovaj datum'
            }

        # Calculate basic stats
        total_refunds = sum(r['refund_amount'] for r in refunds)
        total_revenue = sum(s['sale']['total_amount'] for s in sales_data) - total_refunds
        total_transactions = len(sales_data)
        total_items_sold = sum(
            sum(item['quantity'] for item in s['items'])
            for s in sales_data
        )

        # Calculate VAT breakdown from sales table
        vat_summary = {}
        for sale_data in sales_data:
            sale = sale_data['sale']
            for item in sale_data['items']:
                vat_rate = item.get('vat_rate', 0.20)
                if vat_rate not in vat_summary:
                    vat_summary[vat_rate] = {'base': 0, 'vat': 0, 'total': 0}

                item_total = item['total']
                base = item_total / (1 + vat_rate)
                vat = item_total - base

                vat_summary[vat_rate]['base'] += base
                vat_summary[vat_rate]['vat'] += vat
                vat_summary[vat_rate]['total'] += item_total

        # Top selling items
        item_sales = {}
        for sale_data in sales_data:
            for item in sale_data['items']:
                item_name = item['item']
                if item_name not in item_sales:
                    item_sales[item_name] = {'quantity': 0, 'revenue': 0}

                item_sales[item_name]['quantity'] += item['quantity']
                item_sales[item_name]['revenue'] += item['total']

        top_items = sorted(
            item_sales.items(),
            key=lambda x: x[1]['revenue'],
            reverse=True
        )[:10]

        # Hourly breakdown
        hourly_sales = {}
        for sale_data in sales_data:
            sale = sale_data['sale']
            hour = sale['created_at'].split()[1].split(':')[0]

            if hour not in hourly_sales:
                hourly_sales[hour] = {'transactions': 0, 'revenue': 0}

            hourly_sales[hour]['transactions'] += 1
            hourly_sales[hour]['revenue'] += sale['total_amount']

        avg_transaction = total_revenue / total_transactions if total_transactions > 0 else 0

        # Flatten sales for detail view
        sales_detail = []
        for sale_data in sales_data:
            sale = sale_data['sale']
            for item in sale_data['items']:
                sales_detail.append({
                    'sale_id': sale['id'],
                    'item': item['item'],
                    'item_price': item['item_price'],
                    'quantity': item['quantity'],
                    'total': item['total'],
                    'time': sale['created_at'],
                    'payment_type': sale['payment_type']
                })

        return {
            'date': date,
            'has_sales': True,
            'summary': {
                'total_revenue': total_revenue,
                'total_transactions': total_transactions,
                'total_items_sold': total_items_sold,
                'avg_transaction': avg_transaction,
                'total_refunds': total_refunds,
                'refund_count': len(refunds)
            },
            'payments': payment_summary,
            'vat_breakdown': vat_summary,
            'top_items': top_items,
            'hourly_sales': sorted(hourly_sales.items()),
            'sales_detail': sales_detail,
            'refunds': refunds
        }

    def _generate_report_legacy(self, date: str) -> dict:
        """Generate report using old sales structure (backward compatibility)"""
        sales = self.sales.get_sales_by_date(date)
        payment_summary = self.payments.get_payment_summary_by_date(date)

        from pos_db_layer import RefundRepository
        refunds = RefundRepository(self.sales.db).get_refunds_by_date(date)

        if not sales and not refunds:
            return {
                'date': date,
                'has_sales': False,
                'message': 'Nema prodaje niti povraćaja za ovaj datum'
            }

        # Calculate basic stats
        total_refunds = sum(r['refund_amount'] for r in refunds)
        total_revenue = sum(sale['total'] for sale in sales) - total_refunds
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
                'total_refunds': total_refunds,
                'refund_count': len(refunds)
            },
            'payments': payment_summary,
            'vat_breakdown': vat_summary,
            'top_items': top_items,
            'hourly_sales': sorted(hourly_sales.items()),
            'sales_detail': sales,
            'refunds': refunds
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
        # Use unified sales if available
        if self.unified_sales:
            payment_summary = self.unified_sales.get_payment_summary_by_date(date)
            sales = self.unified_sales.get_sales_by_date(date)
            total_change_given = sum(
                sale.get('change_given', 0) or 0
                for sale in sales
            )
        else:
            payment_summary = self.payments.get_payment_summary_by_date(date)
            sales = self.sales.get_sales_by_date(date)
            total_change_given = sum(
                sale.get('change_given', 0) or 0
                for sale in sales
                if sale.get('change_given')
            )

        expected_cash = payment_summary['cash']
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


    # In pos_business_logic.py, UserService class

    def delete_user(self, user_id: int) -> Tuple[bool, str]:
        """
        Delete user permanently

        Returns:
            (success, message)
        """
        # Safety check: prevent deleting yourself
        # (You'd need to pass current_user_id to check this)

        # Safety check: prevent deleting last admin
        all_users = self.users.get_all_users()
        admins = [u for u in all_users if u['role'] == 'admin' and u['is_active']]
        user_to_delete = next((u for u in all_users if u['id'] == user_id), None)

        if user_to_delete and user_to_delete['role'] == 'admin' and len(admins) == 1:
            return False, "Ne možete obrisati poslednjeg administratora!"

        success = self.users.delete_user(user_id)
        if success:
            return True, f"Korisnik obrisan"
        else:
            return False, "Greška pri brisanju korisnika"


class RefundService:
    """Service for handling refunds and returns"""
    
    def __init__(self, sales_repo, inventory_repo, refund_repo):
        self.sales = sales_repo
        self.inventory = inventory_repo
        self.refunds = refund_repo
    
    def process_refund(
        self,
        sale_id: int,
        item_name: str,
        quantity: float,
        refund_method: str,
        reason: str = "",
        user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Process a refund
        
        Args:
            sale_id: Original sale ID
            item_name: Item being returned
            quantity: Quantity to refund
            refund_method: 'cash' or 'card'
            reason: Reason for return
            user_id: User processing the refund
            
        Returns:
            (success, message)
        """
        # Find the original sale
        # Note: We'll need to add a method to get sale by ID
        # For now, we'll calculate refund amount based on item
        
        # Get item from inventory to find current price
        items = self.inventory.search(item_name)
        if not items:
            return False, f"Artikal '{item_name}' nije pronađen"
        
        item = items[0]
        refund_amount = item['price'] * quantity
        
        # Record the refund
        self.refunds.record_refund(
            original_sale_id=sale_id,
            item=item_name,
            quantity=quantity,
            refund_amount=refund_amount,
            refund_method=refund_method,
            reason=reason,
            processed_by=user_id
        )
        
        # Return items to inventory
        self.inventory.update_quantity(item['id'], quantity)
        
        return True, f"Povraćaj: {quantity}x {item_name} = {refund_amount:.2f} RSD"
