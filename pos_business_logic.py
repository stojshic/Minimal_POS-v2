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
                 payment_repo=None, receipt_repo=None, settings_repo=None):
        self.inventory = inventory_repo
        self.sales = sales_repo  # Old SalesRepository (for backward compat)
        self.invoices = invoice_repo
        self.payments = payment_repo  # Deprecated - only used in legacy fallback
        self.receipts = receipt_repo  # Deprecated - only used in legacy fallback
        self.customers = customer_repo
        self.unified_sales = unified_sales_repo  # New UnifiedSalesRepository
        self.settings = settings_repo
        self.fiscal_printer = FiscalReceipt(STORE_CONFIG, settings_repo)
    
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

    def search_sales(self, search_term: str) -> List[dict]:
        """Search sales history"""
        return self.sales.search_sales(search_term)
    
    def get_recent_sales(self, limit: int = 10) -> List[dict]:
        """Get recent sales"""
        return self.sales.get_recent_sales(limit)
    
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

    def top_sellers_report(self, days: int = 30, limit: int = 20) -> List[dict]:
        """
        Get top selling items by quantity and revenue.

        Args:
            days: Number of days to look back
            limit: Maximum items to return

        Returns:
            List of dicts with item stats sorted by revenue
        """
        from datetime import datetime, timedelta
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Get all sales from the period
        all_sales = self.sales.get_recent_sales(10000)  # Get lots of sales

        # Filter by date and aggregate
        item_stats = {}
        for sale in all_sales:
            sale_date = sale.get('time', sale.get('created_at', ''))[:10]
            if sale_date >= start_date:
                item_name = sale['item']
                if item_name not in item_stats:
                    item_stats[item_name] = {
                        'item': item_name,
                        'quantity_sold': 0,
                        'revenue': 0,
                        'transactions': 0
                    }
                item_stats[item_name]['quantity_sold'] += sale['quantity']
                item_stats[item_name]['revenue'] += sale['total']
                item_stats[item_name]['transactions'] += 1

        # Sort by revenue and return top N
        sorted_items = sorted(
            item_stats.values(),
            key=lambda x: x['revenue'],
            reverse=True
        )
        return sorted_items[:limit]


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
            # Get VAT rate from sold_items record (stored when sale was made)
            vat_rate = sale.get('vat_rate', 0.20)

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

    def generate_weekly_report(self, year: int, week: int) -> dict:
        """
        Generate weekly report for a given ISO week number

        Args:
            year: Year (e.g., 2026)
            week: ISO week number (1-53)

        Returns:
            Dict containing weekly report data
        """
        from datetime import datetime, timedelta

        # Calculate start and end dates for the ISO week
        jan4 = datetime(year, 1, 4)
        start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
        start_date = start_of_week1 + timedelta(weeks=week - 1)
        end_date = start_date + timedelta(days=6)

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        return self._generate_period_report(start_str, end_str, f"Nedelja {week}, {year}")

    def generate_monthly_report(self, year: int, month: int) -> dict:
        """
        Generate monthly report

        Args:
            year: Year (e.g., 2026)
            month: Month (1-12)

        Returns:
            Dict containing monthly report data
        """
        from datetime import datetime
        import calendar

        start_date = datetime(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = datetime(year, month, last_day)

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        month_names = [
            "", "Januar", "Februar", "Mart", "April", "Maj", "Jun",
            "Jul", "Avgust", "Septembar", "Oktobar", "Novembar", "Decembar"
        ]
        period_name = f"{month_names[month]} {year}"

        return self._generate_period_report(start_str, end_str, period_name)

    def _generate_period_report(self, start_date: str, end_date: str, period_name: str) -> dict:
        """
        Generate report for a date range

        Args:
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'
            period_name: Human-readable period name

        Returns:
            Dict containing period report data
        """
        if not self.unified_sales:
            return {
                'period': period_name,
                'has_sales': False,
                'message': 'Nedeljni/mesečni izveštaji zahtevaju novu strukturu baze'
            }

        from pos_db_layer import RefundRepository

        sales_data = self.unified_sales.get_sales_with_items_between_dates(start_date, end_date)
        payment_summary = self.unified_sales.get_payment_summary_between_dates(start_date, end_date)
        daily_totals = self.unified_sales.get_daily_totals_between_dates(start_date, end_date)

        # Get refunds for the period
        refunds = []
        try:
            refund_repo = RefundRepository(self.unified_sales.db)
            # We need to get refunds for each day in the range
            from datetime import datetime, timedelta
            current = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            while current <= end:
                day_refunds = refund_repo.get_refunds_by_date(current.strftime("%Y-%m-%d"))
                refunds.extend(day_refunds)
                current += timedelta(days=1)
        except Exception:
            pass

        if not sales_data and not refunds:
            return {
                'period': period_name,
                'start_date': start_date,
                'end_date': end_date,
                'has_sales': False,
                'message': f'Nema prodaje za period {period_name}'
            }

        # Calculate basic stats
        total_refunds = sum(r['refund_amount'] for r in refunds)
        total_revenue = sum(s['sale']['total_amount'] for s in sales_data) - total_refunds
        total_transactions = len(sales_data)
        total_items_sold = sum(
            sum(item['quantity'] for item in s['items'])
            for s in sales_data
        )

        # Calculate VAT breakdown
        vat_summary = {}
        for sale_data in sales_data:
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

        avg_transaction = total_revenue / total_transactions if total_transactions > 0 else 0
        days_with_sales = len(daily_totals)
        avg_daily_revenue = total_revenue / days_with_sales if days_with_sales > 0 else 0

        return {
            'period': period_name,
            'start_date': start_date,
            'end_date': end_date,
            'has_sales': True,
            'summary': {
                'total_revenue': total_revenue,
                'total_transactions': total_transactions,
                'total_items_sold': total_items_sold,
                'avg_transaction': avg_transaction,
                'avg_daily_revenue': avg_daily_revenue,
                'days_with_sales': days_with_sales,
                'total_refunds': total_refunds,
                'refund_count': len(refunds)
            },
            'payments': payment_summary,
            'vat_breakdown': vat_summary,
            'top_items': top_items,
            'daily_totals': daily_totals,
            'refunds': refunds
        }

    def generate_restaurant_report(self, date: str, session_repo) -> dict:
        """
        Generate restaurant-specific daily report

        Args:
            date: Date in format 'YYYY-MM-DD'
            session_repo: TableSessionRepository instance

        Returns:
            Dict containing restaurant report data
        """
        # Get session data for the date
        sessions = session_repo.get_sessions_by_date(date)
        sales_by_table = session_repo.get_sales_by_table(date)
        sales_by_waiter = session_repo.get_sales_by_waiter(date)
        turnover_stats = session_repo.get_turnover_stats(date)

        if not sessions:
            return {
                'date': date,
                'has_data': False,
                'message': 'Nema podataka za ovaj datum'
            }

        # Calculate totals
        total_revenue = sum(s['total_amount'] or 0 for s in sessions)
        total_sessions = len(sessions)

        # Payment breakdown
        payment_breakdown = {}
        for session in sessions:
            ptype = session.get('payment_type', 'cash')
            if ptype not in payment_breakdown:
                payment_breakdown[ptype] = {'count': 0, 'total': 0}
            payment_breakdown[ptype]['count'] += 1
            payment_breakdown[ptype]['total'] += session['total_amount'] or 0

        # Hourly breakdown
        hourly_sessions = {}
        for session in sessions:
            if session.get('closed_at'):
                hour = session['closed_at'].split('T')[1].split(':')[0] if 'T' in session['closed_at'] else session['closed_at'].split()[1].split(':')[0]
                if hour not in hourly_sessions:
                    hourly_sessions[hour] = {'count': 0, 'revenue': 0}
                hourly_sessions[hour]['count'] += 1
                hourly_sessions[hour]['revenue'] += session['total_amount'] or 0

        return {
            'date': date,
            'has_data': True,
            'summary': {
                'total_revenue': total_revenue,
                'total_sessions': total_sessions,
                'avg_ticket': total_revenue / total_sessions if total_sessions > 0 else 0,
                'avg_duration_minutes': turnover_stats.get('avg_duration_minutes') or 0,
                'min_duration_minutes': turnover_stats.get('min_duration_minutes') or 0,
                'max_duration_minutes': turnover_stats.get('max_duration_minutes') or 0
            },
            'sales_by_table': sales_by_table,
            'sales_by_waiter': sales_by_waiter,
            'payment_breakdown': payment_breakdown,
            'hourly_sessions': sorted(hourly_sessions.items()),
            'sessions': sessions
        }


class UserService:
    """Service for user management and authentication"""

    def __init__(self, user_repo):
        self.users = user_repo

    def login(self, username: str, password: str) -> Tuple[bool, Optional[dict], str]:
        """
        Authenticate user with brute-force protection.

        Returns:
            (success, user_dict, message)
        """
        if not username or not password:
            return False, None, "Korisničko ime i lozinka su obavezni!"

        # Get lockout settings from config
        from config import CONFIG
        max_attempts = CONFIG.get('max_login_attempts', 5)
        lockout_minutes = CONFIG.get('lockout_duration_minutes', 15)

        user, error = self.users.authenticate(
            username, password,
            max_attempts=max_attempts,
            lockout_minutes=lockout_minutes
        )

        if user:
            return True, user, f"Dobrodošli, {user['full_name']}!"
        elif error and error.startswith("locked:"):
            remaining = error.split(":")[1]
            return False, None, f"Nalog zaključan! Pokušajte ponovo za {remaining} minuta."
        else:
            return False, None, "Pogrešno korisničko ime ili lozinka!"

    def get_all_users(self) -> List[dict]:
        """Get all users (admin only)"""
        return self.users.get_all_users()

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


class StockAdjustmentService:
    """Service for stock adjustments with audit trail"""

    def __init__(self, inventory_repo, adjustment_repo):
        self.inventory = inventory_repo
        self.adjustments = adjustment_repo

    def adjust_stock(
        self,
        item_id: int,
        new_quantity: float,
        reason_code: str,
        notes: str = "",
        user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Adjust stock to a specific quantity.

        Args:
            item_id: Inventory item ID
            new_quantity: New absolute quantity to set
            reason_code: Reason code for adjustment
            notes: Optional notes
            user_id: User making the adjustment

        Returns:
            (success, message)
        """
        # Get current item
        item = self.inventory.get_by_id(item_id)
        if not item:
            return False, "Artikal nije pronađen"

        old_quantity = item['quantity']
        quantity_change = new_quantity - old_quantity

        if quantity_change == 0:
            return False, "Količina je ista, nema promene"

        adjustment_type = "increase" if quantity_change > 0 else "decrease"

        # Update inventory
        # We need to set the absolute quantity, not add to it
        with self.inventory.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE inventory
                   SET quantity = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (new_quantity, item_id)
            )

        # Record adjustment
        self.adjustments.record_adjustment(
            item_id=item_id,
            item_name=item['item'],
            adjustment_type=adjustment_type,
            quantity_before=old_quantity,
            quantity_change=quantity_change,
            quantity_after=new_quantity,
            reason_code=reason_code,
            notes=notes,
            adjusted_by=user_id
        )

        reason_label = self.adjustments.REASON_CODES.get(reason_code, reason_code)
        return True, f"Korekcija: {item['item']} {old_quantity} → {new_quantity} ({reason_label})"

    def get_adjustment_history(self, item_id: int = None, limit: int = 100) -> List[dict]:
        """Get adjustment history, optionally filtered by item"""
        if item_id:
            return self.adjustments.get_adjustments_by_item(item_id, limit)
        return self.adjustments.get_recent_adjustments(limit)

    def get_reason_codes(self) -> dict:
        """Get available reason codes with labels"""
        return self.adjustments.REASON_CODES


class TableService:
    """Service for restaurant table management"""

    def __init__(self, table_repo, session_repo, order_repo, inventory_repo):
        self.tables = table_repo
        self.sessions = session_repo
        self.orders = order_repo
        self.inventory = inventory_repo

    # ============================================================
    # Table Management
    # ============================================================

    def get_all_tables(self) -> List[dict]:
        """Get all tables"""
        return self.tables.get_all()

    def get_tables_with_status(self) -> List[dict]:
        """Get all active tables with their current status (for grid display)"""
        tables = self.tables.get_tables_with_status()

        # Enhance with calculated totals from orders
        for table in tables:
            if table.get('session_id'):
                table['total'] = self.orders.get_session_total(table['session_id'])
                # Only mark as occupied if there are actual orders (total > 0)
                table['occupied'] = table['total'] > 0
            else:
                table['total'] = 0.0
                table['occupied'] = False

        return tables

    def create_table(self, name: str, row: int, col: int, capacity: int) -> Tuple[bool, str, int]:
        """Create a new table"""
        try:
            table_id = self.tables.create(name, row, col, capacity)
            return True, f"Sto '{name}' kreiran", table_id
        except Exception as e:
            return False, f"Greška: {str(e)}", 0

    def update_table(self, table_id: int, name: str, row: int, col: int, capacity: int) -> Tuple[bool, str]:
        """Update table info"""
        success = self.tables.update(table_id, name, row, col, capacity)
        if success:
            return True, f"Sto '{name}' ažuriran"
        return False, "Greška pri ažuriranju"

    def delete_table(self, table_id: int) -> Tuple[bool, str]:
        """Delete a table (only if not occupied)"""
        # Check if table has open session
        session = self.sessions.get_open_session(table_id)
        if session:
            return False, "Ne možete obrisati zauzet sto!"

        success = self.tables.delete(table_id)
        if success:
            return True, "Sto obrisan"
        return False, "Greška pri brisanju"

    def toggle_table_active(self, table_id: int) -> Tuple[bool, str]:
        """Toggle table active status"""
        table = self.tables.get_by_id(table_id)
        if not table:
            return False, "Sto nije pronađen"

        # Check if trying to deactivate occupied table
        if table['is_active']:
            session = self.sessions.get_open_session(table_id)
            if session:
                return False, "Ne možete deaktivirati zauzet sto!"

        new_status = not table['is_active']
        success = self.tables.set_active(table_id, new_status)
        if success:
            status_text = "aktiviran" if new_status else "deaktiviran"
            return True, f"Sto {status_text}"
        return False, "Greška pri promeni statusa"

    # ============================================================
    # Session Management
    # ============================================================

    def open_table(self, table_id: int, waiter_id: int = None) -> Tuple[bool, str, Optional[int]]:
        """Open a table (start new session)"""
        # Check if already open
        existing = self.sessions.get_open_session(table_id)
        if existing:
            return True, "Sto je već otvoren", existing['id']

        session_id = self.sessions.open_session(table_id, waiter_id)
        return True, "Sto otvoren", session_id

    def close_table(self, session_id: int, payment_type: str = 'cash') -> Tuple[bool, str]:
        """Close a table (finalize payment)"""
        session = self.sessions.get_by_id(session_id)
        if not session:
            return False, "Sesija nije pronađena"

        if session['status'] != 'open':
            return False, "Sesija je već zatvorena"

        # Calculate final total
        total = self.orders.get_session_total(session_id)
        self.sessions.update_total(session_id, total)

        # Close the session
        success = self.sessions.close_session(session_id, payment_type)
        if success:
            return True, f"Sto zatvoren. Ukupno: {total:.2f} RSD"
        return False, "Greška pri zatvaranju stola"

    # ============================================================
    # Order Management
    # ============================================================

    def add_order(
        self,
        session_id: int,
        item_id: int,
        quantity: float = 1.0,
        notes: str = ""
    ) -> Tuple[bool, str]:
        """Add an item to a table's order (aggregates if item already exists)"""
        # Get item from inventory
        item = self.inventory.get_by_id(item_id)
        if not item:
            return False, "Artikal nije pronađen"

        # Check if this item already exists in the session
        existing_order = self.orders.find_order_by_item(session_id, item_id)

        if existing_order:
            # Item exists - increment quantity
            new_qty = existing_order['quantity'] + quantity
            self.orders.increment_quantity(existing_order['id'], quantity)
            msg = f"Ažurirano: {new_qty:.0f}x {item['item']}"
        else:
            # New item - add to orders
            item_type = item.get('item_type', 'other')
            order_id = self.orders.add_order(
                session_id=session_id,
                item_id=item_id,
                item_name=item['item'],
                quantity=quantity,
                unit_price=item['price'],
                item_type=item_type,
                notes=notes
            )
            msg = f"Dodato: {quantity:.0f}x {item['item']}"

        # Update session total
        total = self.orders.get_session_total(session_id)
        self.sessions.update_total(session_id, total)

        return True, msg

    def remove_order(self, order_id: int) -> Tuple[bool, str]:
        """Remove an order from a table"""
        order = self.orders.get_by_id(order_id)
        if not order:
            return False, "Porudžbina nije pronađena"

        session_id = order['session_id']
        item_name = order['item_name']

        success = self.orders.delete_order(order_id)
        if success:
            # Update session total
            total = self.orders.get_session_total(session_id)
            self.sessions.update_total(session_id, total)
            return True, f"Uklonjeno: {item_name}"
        return False, "Greška pri uklanjanju"

    def update_order_quantity(self, order_id: int, new_quantity: float) -> Tuple[bool, str]:
        """Update quantity of an existing order"""
        order = self.orders.get_by_id(order_id)
        if not order:
            return False, "Porudžbina nije pronađena"

        if new_quantity <= 0:
            return self.remove_order(order_id)

        success = self.orders.update_quantity(order_id, new_quantity, order['unit_price'])
        if success:
            # Update session total
            total = self.orders.get_session_total(order['session_id'])
            self.sessions.update_total(order['session_id'], total)
            return True, f"Količina ažurirana: {new_quantity}x {order['item_name']}"
        return False, "Greška pri ažuriranju"

    def get_table_orders(self, session_id: int) -> List[dict]:
        """Get all orders for a session"""
        return self.orders.get_session_orders(session_id)

    def get_table_total(self, session_id: int) -> float:
        """Get total for a session"""
        return self.orders.get_session_total(session_id)

    def update_order_status(self, order_id: int, status: str) -> Tuple[bool, str]:
        """Update order status (ordered -> preparing -> served)"""
        valid_statuses = ['ordered', 'preparing', 'served']
        if status not in valid_statuses:
            return False, f"Nevažeći status. Dozvoljeni: {', '.join(valid_statuses)}"

        success = self.orders.update_status(order_id, status)
        if success:
            return True, f"Status ažuriran: {status}"
        return False, "Greška pri ažuriranju statusa"

    # ============================================================
    # Kitchen / Bar Display
    # ============================================================

    def get_pending_orders(self) -> List[dict]:
        """Get all pending orders for kitchen display"""
        return self.orders.get_pending_orders()

    def get_open_sessions(self) -> List[dict]:
        """Get all currently open sessions"""
        return self.sessions.get_open_sessions()

    def get_new_orders_by_type(self, session_id: int, item_type: str) -> List[dict]:
        """Get new (not yet printed) orders filtered by item type"""
        return self.orders.get_new_orders_by_type(session_id, item_type)

    def save_last_ticket(self, session_id: int, ticket_text: str) -> bool:
        """Save last printed ticket for re-printing"""
        return self.sessions.save_last_ticket(session_id, ticket_text)

    def get_last_ticket(self, session_id: int) -> Optional[str]:
        """Get last printed ticket for a session"""
        return self.sessions.get_last_ticket(session_id)


class CategoryService:
    """Service for managing item categories"""

    def __init__(self, category_repo, inventory_repo):
        self.categories = category_repo
        self.inventory = inventory_repo

    def get_all_categories(self, include_inactive: bool = False) -> List[dict]:
        """Get all categories, optionally including inactive ones"""
        return self.categories.get_all(include_inactive)

    def get_category(self, category_id: int) -> Optional[dict]:
        """Get a specific category by ID"""
        return self.categories.get_by_id(category_id)

    def create_category(self, name: str, display_order: int = 0, icon: str = "") -> Tuple[bool, str, Optional[int]]:
        """
        Create a new category

        Returns:
            (success, message, category_id)
        """
        if not name or not name.strip():
            return False, "Naziv kategorije je obavezan!", None

        # Check for duplicate name
        existing = self.categories.get_by_name(name.strip())
        if existing:
            return False, f"Kategorija '{name}' već postoji!", None

        try:
            category_id = self.categories.create(name.strip(), display_order, icon)
            return True, f"Kategorija '{name}' kreirana", category_id
        except Exception as e:
            return False, f"Greška: {str(e)}", None

    def update_category(self, category_id: int, name: str, display_order: int, icon: str) -> Tuple[bool, str]:
        """
        Update a category

        Returns:
            (success, message)
        """
        if not name or not name.strip():
            return False, "Naziv kategorije je obavezan!"

        # Check for duplicate name (excluding current category)
        existing = self.categories.get_by_name(name.strip())
        if existing and existing['id'] != category_id:
            return False, f"Kategorija '{name}' već postoji!"

        try:
            success = self.categories.update(category_id, name.strip(), display_order, icon)
            if success:
                return True, f"Kategorija '{name}' ažurirana"
            return False, "Greška pri ažuriranju kategorije"
        except Exception as e:
            return False, f"Greška: {str(e)}"

    def delete_category(self, category_id: int) -> Tuple[bool, str]:
        """
        Delete a category (prevents deleting "Bez kategorije")

        Returns:
            (success, message)
        """
        # Prevent deleting the default "Bez kategorije" category (id=1)
        if category_id == 1:
            return False, "Ne možete obrisati kategoriju 'Bez kategorije'!"

        category = self.categories.get_by_id(category_id)
        if not category:
            return False, "Kategorija nije pronađena!"

        item_count = self.categories.get_item_count(category_id)

        try:
            success = self.categories.delete(category_id)
            if success:
                msg = f"Kategorija '{category['name']}' obrisana"
                if item_count > 0:
                    msg += f" ({item_count} artikala prebačeno u 'Bez kategorije')"
                return True, msg
            return False, "Greška pri brisanju kategorije"
        except Exception as e:
            return False, f"Greška: {str(e)}"

    def toggle_category_active(self, category_id: int) -> Tuple[bool, str]:
        """
        Toggle category active status

        Returns:
            (success, message)
        """
        # Prevent deactivating the default category
        if category_id == 1:
            return False, "Ne možete deaktivirati kategoriju 'Bez kategorije'!"

        category = self.categories.get_by_id(category_id)
        if not category:
            return False, "Kategorija nije pronađena!"

        new_status = not category['is_active']
        try:
            success = self.categories.set_active(category_id, new_status)
            if success:
                status_text = "aktivirana" if new_status else "deaktivirana"
                return True, f"Kategorija '{category['name']}' {status_text}"
            return False, "Greška pri promeni statusa"
        except Exception as e:
            return False, f"Greška: {str(e)}"

    def get_items_by_category(self, category_id: Optional[int] = None, search: str = "") -> List[dict]:
        """Get inventory items filtered by category and search term"""
        return self.inventory.get_by_category(category_id, search)
