"""
Database layer for POS system
Handles all database operations with clean interfaces
"""
import sqlite3
from contextlib import contextmanager
from typing import List, Optional, Dict, Any
from datetime import datetime


class Database:
    """Main database handler with context manager support"""
    
    def __init__(self, db_path: str = "data.db"):
        self.db_path = db_path
        self.initialize_tables()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Returns dict-like rows
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def initialize_tables(self):
        """Create all necessary tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_login TEXT
                )
            """)


            # Add default admin user if table is empty
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                import hashlib
                # Default admin password: "admin123" (should be changed after first login!)
                default_password = hashlib.sha256("admin123".encode()).hexdigest()
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, role)
                    VALUES (?, ?, ?, ?)
                """, ("admin", default_password, "Administrator", "admin"))
                conn.commit()

            # Inventory table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item TEXT NOT NULL,
                    barcode TEXT UNIQUE,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    vat_rate REAL DEFAULT 0.20,
                    item_type TEXT DEFAULT 'other',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration: Add item_type column if it doesn't exist
            cursor.execute("PRAGMA table_info(inventory)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'item_type' not in columns:
                cursor.execute("ALTER TABLE inventory ADD COLUMN item_type TEXT DEFAULT 'other'")
            
            # Sold items table (linked to sales table after Phase 2)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sold_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id INTEGER,
                    item_id INTEGER,
                    item TEXT NOT NULL,
                    item_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    vat_rate REAL DEFAULT 0.20,
                    total REAL NOT NULL,
                    time TEXT,
                    amount_paid REAL,
                    change_given REAL DEFAULT 0,
                    FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
                    FOREIGN KEY (item_id) REFERENCES inventory(id)
                )
            """)

            # Migration: Add new columns to sold_items if they don't exist
            cursor.execute("PRAGMA table_info(sold_items)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'sale_id' not in columns:
                cursor.execute("ALTER TABLE sold_items ADD COLUMN sale_id INTEGER REFERENCES sales(id)")
            if 'item_id' not in columns:
                cursor.execute("ALTER TABLE sold_items ADD COLUMN item_id INTEGER REFERENCES inventory(id)")
            if 'vat_rate' not in columns:
                cursor.execute("ALTER TABLE sold_items ADD COLUMN vat_rate REAL DEFAULT 0.20")

            # Payment records table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                payment_type TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sale_id) REFERENCES sold_items(id) ON DELETE CASCADE
                )
            """)

            # Receipts table (for storing receipt copies)
            # NOTE: This table will be deprecated after migration to unified sales table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id INTEGER NOT NULL,
                    receipt_number INTEGER NOT NULL,
                    receipt_text TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sale_id) REFERENCES sold_items(id) ON DELETE CASCADE
                )
            """)

            # Unified sales table - Phase 1 of DB refactoring
            # This table consolidates payments, receipts, and customer_invoices
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    receipt_number INTEGER NOT NULL,
                    customer_id INTEGER,
                    invoice_number TEXT,
                    payment_type TEXT NOT NULL,
                    cash_amount REAL DEFAULT 0,
                    card_amount REAL DEFAULT 0,
                    amount_tendered REAL DEFAULT 0,
                    change_given REAL DEFAULT 0,
                    total_amount REAL NOT NULL,
                    vat_amount REAL NOT NULL,
                    receipt_text TEXT,
                    status TEXT DEFAULT 'completed',
                    notes TEXT,
                    cashier_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(id),
                    FOREIGN KEY (cashier_id) REFERENCES users(id)
                )
            """)

            # Refunds table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS refunds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_sale_id INTEGER NOT NULL,
                    item TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    refund_amount REAL NOT NULL,
                    reason TEXT,
                    refund_method TEXT NOT NULL,
                    processed_by INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (original_sale_id) REFERENCES sold_items(id),
                    FOREIGN KEY (processed_by) REFERENCES users(id)
                )
            """)

            # Invoice table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invoice (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice TEXT NOT NULL UNIQUE,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Invoice data table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invoice_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id INTEGER NOT NULL,
                    item TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    total REAL NOT NULL,
                    FOREIGN KEY (invoice_id) REFERENCES invoice(id) ON DELETE CASCADE
                )
            """)

            # Customers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    company_name TEXT,
                    pib TEXT,
                    jmbg TEXT,
                    address TEXT,
                    city TEXT,
                    postal_code TEXT,
                    phone TEXT,
                    email TEXT,
                    is_company INTEGER DEFAULT 0,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration: Add jmbg column if it doesn't exist
            cursor.execute("PRAGMA table_info(customers)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'jmbg' not in columns:
                cursor.execute("ALTER TABLE customers ADD COLUMN jmbg TEXT")

            # Customer invoices table (different from supplier invoices)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customer_invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_number TEXT NOT NULL UNIQUE,
                    customer_id INTEGER,
                    issue_date TEXT NOT NULL,
                    due_date TEXT,
                    total_amount REAL NOT NULL,
                    vat_amount REAL NOT NULL,
                    status TEXT DEFAULT 'unpaid',
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(id)
                )
            """)

            # Customer invoice items
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customer_invoice_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    unit_price REAL NOT NULL,
                    vat_rate REAL NOT NULL,
                    total REAL NOT NULL,
                    FOREIGN KEY (invoice_id) REFERENCES customer_invoices(id) ON DELETE CASCADE
                )
            """)

            # Migration tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_name TEXT NOT NULL UNIQUE,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ============================================================
            # Restaurant mode tables
            # ============================================================

            # Restaurant tables (physical tables in the restaurant)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS restaurant_tables (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    position_row INTEGER DEFAULT 0,
                    position_col INTEGER DEFAULT 0,
                    capacity INTEGER DEFAULT 4,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table sessions (when a table is occupied)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS table_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_id INTEGER NOT NULL,
                    waiter_id INTEGER,
                    status TEXT DEFAULT 'open',
                    opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    closed_at TEXT,
                    total_amount REAL DEFAULT 0,
                    payment_type TEXT,
                    notes TEXT,
                    FOREIGN KEY (table_id) REFERENCES restaurant_tables(id),
                    FOREIGN KEY (waiter_id) REFERENCES users(id)
                )
            """)

            # Table orders (individual items ordered at a table)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS table_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    unit_price REAL NOT NULL,
                    total_price REAL NOT NULL,
                    item_type TEXT DEFAULT 'other',
                    status TEXT DEFAULT 'ordered',
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES table_sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (item_id) REFERENCES inventory(id)
                )
            """)

            # Migration: Add item_type column to table_orders if it doesn't exist
            cursor.execute("PRAGMA table_info(table_orders)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'item_type' not in columns:
                cursor.execute("ALTER TABLE table_orders ADD COLUMN item_type TEXT DEFAULT 'other'")

            # Initialize default restaurant tables if none exist
            cursor.execute("SELECT COUNT(*) FROM restaurant_tables")
            if cursor.fetchone()[0] == 0:
                default_tables = [
                    ("Sto 1", 0, 0, 4),
                    ("Sto 2", 0, 1, 4),
                    ("Sto 3", 0, 2, 4),
                    ("Sto 4", 1, 0, 4),
                    ("Sto 5", 1, 1, 4),
                    ("Sto 6", 1, 2, 4),
                ]
                cursor.executemany(
                    "INSERT INTO restaurant_tables (name, position_row, position_col, capacity) VALUES (?, ?, ?, ?)",
                    default_tables
                )

    def run_migrations(self) -> Dict[str, Any]:
        """
        Run Phase 3 data migrations to consolidate old tables into unified sales.

        This migrates:
        - Old sold_items + payments + receipts -> sales + sold_items (with sale_id)
        - customer_invoices + customer_invoice_items -> sales + sold_items

        Returns:
            Dict with migration statistics
        """
        stats = {
            'receipts_migrated': 0,
            'customer_invoices_migrated': 0,
            'sold_items_linked': 0,
            'errors': []
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if migration already done
            cursor.execute(
                "SELECT 1 FROM _migrations WHERE migration_name = 'phase3_consolidate_sales'"
            )
            if cursor.fetchone():
                stats['errors'].append('Migration already applied')
                return stats

            # ============================================================
            # PART 1: Migrate receipts -> sales, link sold_items
            # ============================================================
            # The old structure: receipts.sale_id points to a sold_item.id
            # We need to group sold_items by receipt and create proper sales

            cursor.execute("""
                SELECT r.id, r.sale_id, r.receipt_number, r.receipt_text, r.created_at
                FROM receipts r
                ORDER BY r.id
            """)
            receipts = cursor.fetchall()

            for receipt in receipts:
                receipt_id = receipt['id']
                old_sale_id = receipt['sale_id']  # This is actually a sold_item.id
                receipt_number = receipt['receipt_number']
                receipt_text = receipt['receipt_text']
                created_at = receipt['created_at']

                # Get the sold_item that this receipt points to
                cursor.execute(
                    "SELECT * FROM sold_items WHERE id = ?",
                    (old_sale_id,)
                )
                first_item = cursor.fetchone()
                if not first_item:
                    stats['errors'].append(f'Receipt {receipt_id}: sold_item {old_sale_id} not found')
                    continue

                # Get payment info for this sale
                cursor.execute(
                    "SELECT payment_type, amount FROM payments WHERE sale_id = ?",
                    (old_sale_id,)
                )
                payments = cursor.fetchall()

                # Determine payment type and amounts
                cash_amount = 0.0
                card_amount = 0.0
                payment_type = 'cash'

                for payment in payments:
                    if payment['payment_type'] == 'cash':
                        cash_amount += payment['amount']
                    elif payment['payment_type'] == 'card':
                        card_amount += payment['amount']

                if cash_amount > 0 and card_amount > 0:
                    payment_type = 'split'
                elif card_amount > 0:
                    payment_type = 'card'
                else:
                    payment_type = 'cash'

                # Get total and VAT from the sold_item
                # For old items, we need to calculate VAT (assume 20%)
                total_amount = first_item['total']
                vat_rate = first_item['vat_rate'] if first_item['vat_rate'] else 0.20
                vat_amount = total_amount * vat_rate / (1 + vat_rate)

                amount_tendered = first_item['amount_paid'] or total_amount
                change_given = first_item['change_given'] or 0

                # Create the sale record
                cursor.execute(
                    """INSERT INTO sales
                       (receipt_number, payment_type, cash_amount, card_amount,
                        amount_tendered, change_given, total_amount, vat_amount,
                        receipt_text, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)""",
                    (receipt_number, payment_type, cash_amount, card_amount,
                     amount_tendered, change_given, total_amount, vat_amount,
                     receipt_text, created_at)
                )
                new_sale_id = cursor.lastrowid

                # Link the sold_item to this sale
                cursor.execute(
                    "UPDATE sold_items SET sale_id = ? WHERE id = ?",
                    (new_sale_id, old_sale_id)
                )
                stats['sold_items_linked'] += 1
                stats['receipts_migrated'] += 1

            # ============================================================
            # PART 2: Migrate customer_invoices -> sales
            # ============================================================
            cursor.execute("""
                SELECT ci.*, c.name as customer_name
                FROM customer_invoices ci
                LEFT JOIN customers c ON ci.customer_id = c.id
                ORDER BY ci.id
            """)
            customer_invoices = cursor.fetchall()

            for invoice in customer_invoices:
                invoice_id = invoice['id']

                # Create sale record for this customer invoice
                cursor.execute(
                    """INSERT INTO sales
                       (receipt_number, customer_id, invoice_number, payment_type,
                        total_amount, vat_amount, status, notes, created_at)
                       VALUES (?, ?, ?, 'invoice', ?, ?, ?, ?, ?)""",
                    (0,  # No receipt number for invoices
                     invoice['customer_id'],
                     invoice['invoice_number'],
                     invoice['total_amount'],
                     invoice['vat_amount'],
                     invoice['status'],
                     invoice['notes'],
                     invoice['created_at'])
                )
                new_sale_id = cursor.lastrowid

                # Migrate invoice items to sold_items
                cursor.execute(
                    "SELECT * FROM customer_invoice_items WHERE invoice_id = ?",
                    (invoice_id,)
                )
                items = cursor.fetchall()

                for item in items:
                    cursor.execute(
                        """INSERT INTO sold_items
                           (sale_id, item, item_price, quantity, vat_rate, total)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (new_sale_id, item['item_name'], item['unit_price'],
                         item['quantity'], item['vat_rate'], item['total'])
                    )
                    stats['sold_items_linked'] += 1

                stats['customer_invoices_migrated'] += 1

            # ============================================================
            # PART 3: Handle orphan sold_items (no receipt)
            # ============================================================
            # Find sold_items that still have no sale_id
            cursor.execute(
                "SELECT * FROM sold_items WHERE sale_id IS NULL ORDER BY id"
            )
            orphans = cursor.fetchall()

            # Group orphans by timestamp (items within 1 minute are same sale)
            if orphans:
                current_group = []
                last_time = None

                for orphan in orphans:
                    item_time = orphan['time']

                    if last_time is None or self._times_within_minutes(last_time, item_time, 1):
                        current_group.append(orphan)
                    else:
                        # Process current group
                        if current_group:
                            self._create_sale_from_orphans(cursor, current_group, stats)
                        current_group = [orphan]

                    last_time = item_time

                # Process last group
                if current_group:
                    self._create_sale_from_orphans(cursor, current_group, stats)

            # Mark migration as complete
            cursor.execute(
                "INSERT INTO _migrations (migration_name) VALUES ('phase3_consolidate_sales')"
            )

        return stats

    def _times_within_minutes(self, time1: str, time2: str, minutes: int) -> bool:
        """Check if two timestamp strings are within N minutes of each other"""
        if not time1 or not time2:
            return False
        try:
            from datetime import datetime, timedelta
            t1 = datetime.strptime(time1, "%Y-%m-%d %H:%M:%S")
            t2 = datetime.strptime(time2, "%Y-%m-%d %H:%M:%S")
            return abs((t2 - t1).total_seconds()) <= minutes * 60
        except:
            return False

    def _create_sale_from_orphans(self, cursor, items: list, stats: dict):
        """Create a sale record from a group of orphan sold_items"""
        if not items:
            return

        # Calculate totals
        total_amount = sum(item['total'] for item in items)
        first_item = items[0]
        vat_rate = first_item['vat_rate'] if first_item['vat_rate'] else 0.20
        vat_amount = total_amount * vat_rate / (1 + vat_rate)

        # Get next receipt number
        cursor.execute("SELECT MAX(receipt_number) FROM sales")
        max_receipt = cursor.fetchone()[0] or 0
        receipt_number = max_receipt + 1

        amount_tendered = first_item['amount_paid'] or total_amount
        change_given = first_item['change_given'] or 0
        created_at = first_item['time']

        # Create sale record
        cursor.execute(
            """INSERT INTO sales
               (receipt_number, payment_type, amount_tendered, change_given,
                total_amount, vat_amount, status, created_at)
               VALUES (?, 'cash', ?, ?, ?, ?, 'completed', ?)""",
            (receipt_number, amount_tendered, change_given,
             total_amount, vat_amount, created_at)
        )
        new_sale_id = cursor.lastrowid

        # Link all items to this sale
        for item in items:
            cursor.execute(
                "UPDATE sold_items SET sale_id = ? WHERE id = ?",
                (new_sale_id, item['id'])
            )
            stats['sold_items_linked'] += 1

    def get_migration_status(self) -> Dict[str, Any]:
        """Check which migrations have been applied"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if migrations table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'"
            )
            if not cursor.fetchone():
                return {'migrations': [], 'phase3_applied': False}

            cursor.execute("SELECT migration_name, applied_at FROM _migrations ORDER BY id")
            migrations = [dict(row) for row in cursor.fetchall()]

            phase3_applied = any(m['migration_name'] == 'phase3_consolidate_sales' for m in migrations)

            return {
                'migrations': migrations,
                'phase3_applied': phase3_applied
            }

    def cleanup_old_tables(self, confirm: bool = False) -> Dict[str, Any]:
        """
        Drop old tables after Phase 3 migration is verified.

        WARNING: This permanently deletes data! Only run after verifying migration success.

        Args:
            confirm: Must be True to actually drop tables (safety flag)

        Returns:
            Dict with cleanup results
        """
        results = {
            'tables_dropped': [],
            'errors': []
        }

        if not confirm:
            results['errors'].append('Must pass confirm=True to drop tables')
            return results

        # Check if migration was applied
        status = self.get_migration_status()
        if not status['phase3_applied']:
            results['errors'].append('Phase 3 migration not applied - cannot cleanup')
            return results

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Tables to drop (old redundant tables)
            tables_to_drop = ['payments', 'receipts', 'customer_invoices', 'customer_invoice_items']

            for table in tables_to_drop:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                    results['tables_dropped'].append(table)
                except Exception as e:
                    results['errors'].append(f"Error dropping {table}: {str(e)}")

            # Record cleanup in migrations
            cursor.execute(
                "INSERT OR IGNORE INTO _migrations (migration_name) VALUES ('phase3_cleanup_old_tables')"
            )

        return results

    def verify_migration(self) -> Dict[str, Any]:
        """
        Verify Phase 3 migration was successful.

        Checks:
        - All sold_items have sale_id (or are orphans handled)
        - Sales table has expected records
        - Data integrity checks

        Returns:
            Dict with verification results
        """
        results = {
            'success': True,
            'checks': {},
            'warnings': []
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check 1: Count sales
            cursor.execute("SELECT COUNT(*) FROM sales")
            sales_count = cursor.fetchone()[0]
            results['checks']['sales_count'] = sales_count

            # Check 2: Count sold_items with sale_id
            cursor.execute("SELECT COUNT(*) FROM sold_items WHERE sale_id IS NOT NULL")
            linked_items = cursor.fetchone()[0]
            results['checks']['sold_items_linked'] = linked_items

            # Check 3: Count sold_items without sale_id (orphans)
            cursor.execute("SELECT COUNT(*) FROM sold_items WHERE sale_id IS NULL")
            orphan_items = cursor.fetchone()[0]
            results['checks']['sold_items_orphans'] = orphan_items
            if orphan_items > 0:
                results['warnings'].append(f'{orphan_items} sold_items still have no sale_id')
                results['success'] = False

            # Check 4: Verify receipt numbers are preserved
            cursor.execute("SELECT COUNT(DISTINCT receipt_number) FROM sales WHERE receipt_number > 0")
            unique_receipts = cursor.fetchone()[0]
            results['checks']['unique_receipt_numbers'] = unique_receipts

            # Check 5: Count migrated customer invoices
            cursor.execute("SELECT COUNT(*) FROM sales WHERE invoice_number IS NOT NULL")
            invoice_sales = cursor.fetchone()[0]
            results['checks']['customer_invoice_sales'] = invoice_sales

        return results

    def migrate_refunds_to_sales(self) -> Dict[str, Any]:
        """
        Phase 4: Update refunds table to reference sales instead of sold_items.

        Maps refunds.original_sale_id (old sold_items.id) to the new sales.id
        using the sold_items.sale_id relationship.

        Returns:
            Dict with migration statistics
        """
        stats = {
            'refunds_updated': 0,
            'refunds_skipped': 0,
            'errors': []
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if migration already done
            cursor.execute(
                "SELECT 1 FROM _migrations WHERE migration_name = 'phase4_refunds_to_sales'"
            )
            if cursor.fetchone():
                stats['errors'].append('Migration already applied')
                return stats

            # Check Phase 3 was done first
            cursor.execute(
                "SELECT 1 FROM _migrations WHERE migration_name = 'phase3_consolidate_sales'"
            )
            if not cursor.fetchone():
                stats['errors'].append('Phase 3 migration must be applied first')
                return stats

            # Get all refunds
            cursor.execute("SELECT id, original_sale_id FROM refunds")
            refunds = cursor.fetchall()

            for refund in refunds:
                refund_id = refund['id']
                old_sale_id = refund['original_sale_id']  # This is sold_items.id

                # Look up the new sale_id from sold_items
                cursor.execute(
                    "SELECT sale_id FROM sold_items WHERE id = ?",
                    (old_sale_id,)
                )
                row = cursor.fetchone()

                if row and row['sale_id']:
                    new_sale_id = row['sale_id']
                    cursor.execute(
                        "UPDATE refunds SET original_sale_id = ? WHERE id = ?",
                        (new_sale_id, refund_id)
                    )
                    stats['refunds_updated'] += 1
                else:
                    stats['refunds_skipped'] += 1
                    stats['errors'].append(
                        f"Refund {refund_id}: sold_item {old_sale_id} has no sale_id"
                    )

            # Mark migration as complete
            cursor.execute(
                "INSERT INTO _migrations (migration_name) VALUES ('phase4_refunds_to_sales')"
            )

        return stats


class InventoryRepository:
    """Repository pattern for inventory operations"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Get inventory item by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM inventory WHERE id = ?", 
                (item_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def search(self, search_term: str = "") -> List[Dict[str, Any]]:
        """Search inventory by item name"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM inventory WHERE item LIKE ? ORDER BY item",
                (f"%{search_term}%",)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_by_barcode(self, barcode: str) -> Optional[Dict[str, Any]]:
        """Get inventory item by barcode"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM inventory WHERE barcode = ?",
                (barcode,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all inventory items"""
        return self.search("")
    
    def add(self, item: str, price: float, quantity: float, barcode: Optional[str] = None,
            vat_rate: float = 0.20, item_type: str = 'other') -> int:
        """Add new inventory item"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO inventory (item, barcode, price, quantity, vat_rate, item_type)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (item, barcode, price, quantity, vat_rate, item_type)
            )
            return cursor.lastrowid
    
    def update_quantity(self, item_id: int, quantity_delta: float) -> bool:
        """Update inventory quantity (positive to add, negative to subtract)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE inventory 
                   SET quantity = quantity + ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (quantity_delta, item_id)
            )
            return cursor.rowcount > 0
    
    def update_price(self, item_id: int, new_price: float) -> bool:
        """Update item price"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE inventory 
                   SET price = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (new_price, item_id)
            )
            return cursor.rowcount > 0
    
    def update(self, item_id: int, price: float, quantity_delta: float) -> bool:
        """Update both price and quantity"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE inventory
                   SET price = ?,
                       quantity = quantity + ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (price, quantity_delta, item_id)
            )
            return cursor.rowcount > 0

    def update_item(self, item_id: int, name: str, barcode: Optional[str],
                    price: float, quantity: float, vat_rate: float,
                    item_type: str = 'other') -> bool:
        """Update all fields of an inventory item"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE inventory
                   SET item = ?,
                       barcode = ?,
                       price = ?,
                       quantity = ?,
                       vat_rate = ?,
                       item_type = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (name, barcode, price, quantity, vat_rate, item_type, item_id)
            )
            return cursor.rowcount > 0


class SalesRepository:
    """Repository for sales transactions (sold_items table)"""

    def __init__(self, db: Database):
        self.db = db

    def record_sale(self, item: str, price: float, quantity: float,
                    amount_paid: Optional[float] = None,
                    change_given: Optional[float] = None) -> int:
        """Record a sale transaction (legacy method - use record_sale_item for new sales)"""
        total = price * quantity
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO sold_items (item, item_price, quantity, time, total, amount_paid, change_given)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (item, price, quantity, timestamp, total, amount_paid, change_given)
            )
            return cursor.lastrowid

    def record_sale_item(
        self,
        sale_id: int,
        item_name: str,
        unit_price: float,
        quantity: float,
        vat_rate: float = 0.20,
        item_id: Optional[int] = None
    ) -> int:
        """Record a sold item linked to a sale (new method for Phase 2)"""
        line_total = unit_price * quantity

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO sold_items (sale_id, item_id, item, item_price, quantity, vat_rate, total)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sale_id, item_id, item_name, unit_price, quantity, vat_rate, line_total)
            )
            return cursor.lastrowid

    def get_items_by_sale_id(self, sale_id: int) -> List[Dict[str, Any]]:
        """Get all items for a specific sale"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM sold_items
                   WHERE sale_id = ?
                   ORDER BY id""",
                (sale_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_sales(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent sales"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM sold_items 
                   ORDER BY id DESC LIMIT ?""",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def search_sales(self, search_term: str) -> List[Dict[str, Any]]:
        """Search sales by item name"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM sold_items 
                   WHERE item LIKE ?
                   ORDER BY time DESC""",
                (f"%{search_term}%",)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_sales_by_date(self, date: str) -> List[Dict[str, Any]]:
        """
        Get all sales for a specific date

        Args:
            date: Date in format 'YYYY-MM-DD'
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM sold_items
                   WHERE DATE(time) = ?
                   ORDER BY time""",
                (date,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_sales_between_dates(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Get sales between two dates (inclusive)

        Args:
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM sold_items 
                   WHERE DATE(time) BETWEEN ? AND ?
                   ORDER BY time""",
                (start_date, end_date)
            )
            return [dict(row) for row in cursor.fetchall()]


class UnifiedSalesRepository:
    """Repository for the new unified sales table (Phase 1 of DB refactoring)"""

    def __init__(self, db: Database):
        self.db = db

    def create_sale(
        self,
        receipt_number: int,
        payment_type: str,
        total_amount: float,
        vat_amount: float,
        cash_amount: float = 0,
        card_amount: float = 0,
        amount_tendered: float = 0,
        change_given: float = 0,
        customer_id: Optional[int] = None,
        invoice_number: Optional[str] = None,
        receipt_text: Optional[str] = None,
        cashier_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> int:
        """Create a new sale record"""
        # Use local time instead of UTC (SQLite CURRENT_TIMESTAMP uses UTC)
        local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO sales
                   (receipt_number, customer_id, invoice_number, payment_type,
                    cash_amount, card_amount, amount_tendered, change_given,
                    total_amount, vat_amount, receipt_text, cashier_id, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (receipt_number, customer_id, invoice_number, payment_type,
                 cash_amount, card_amount, amount_tendered, change_given,
                 total_amount, vat_amount, receipt_text, cashier_id, notes, local_time)
            )
            return cursor.lastrowid

    def get_by_id(self, sale_id: int) -> Optional[Dict[str, Any]]:
        """Get sale by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sales WHERE id = ?", (sale_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_sales_by_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all sales for a specific date"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM sales
                   WHERE DATE(created_at) = ?
                   ORDER BY created_at""",
                (date,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_sales_by_customer(self, customer_id: int) -> List[Dict[str, Any]]:
        """Get all sales for a specific customer"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM sales
                   WHERE customer_id = ?
                   ORDER BY created_at DESC""",
                (customer_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_recent_sales(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent sales"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM sales
                   ORDER BY id DESC LIMIT ?""",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_status(self, sale_id: int, status: str) -> bool:
        """Update sale status (completed, refunded, partial_refund)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sales SET status = ? WHERE id = ?",
                (status, sale_id)
            )
            return cursor.rowcount > 0

    def get_next_receipt_number(self) -> int:
        """Get the next receipt number"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(receipt_number) FROM sales")
            result = cursor.fetchone()[0]
            return (result or 0) + 1

    def get_sale_with_items(self, sale_id: int) -> Optional[Dict[str, Any]]:
        """
        Get sale with all its items

        Returns:
            Dict with 'sale' (sale record) and 'items' (list of sold items)
            or None if sale not found
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Get sale record
            cursor.execute("SELECT * FROM sales WHERE id = ?", (sale_id,))
            sale_row = cursor.fetchone()
            if not sale_row:
                return None

            # Get items for this sale
            cursor.execute(
                """SELECT * FROM sold_items
                   WHERE sale_id = ?
                   ORDER BY id""",
                (sale_id,)
            )
            items = [dict(row) for row in cursor.fetchall()]

            return {
                'sale': dict(sale_row),
                'items': items
            }

    def get_sales_with_items_by_date(self, date: str) -> List[Dict[str, Any]]:
        """
        Get all sales for a date with their items

        Args:
            date: Date in format 'YYYY-MM-DD'

        Returns:
            List of dicts, each with 'sale' and 'items' keys
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Get all sales for the date
            cursor.execute(
                """SELECT * FROM sales
                   WHERE DATE(created_at) = ?
                   ORDER BY created_at""",
                (date,)
            )
            sales = [dict(row) for row in cursor.fetchall()]

            results = []
            for sale in sales:
                # Get items for each sale
                cursor.execute(
                    """SELECT * FROM sold_items
                       WHERE sale_id = ?
                       ORDER BY id""",
                    (sale['id'],)
                )
                items = [dict(row) for row in cursor.fetchall()]
                results.append({
                    'sale': sale,
                    'items': items
                })

            return results

    def create_sale_with_items(
        self,
        receipt_number: int,
        payment_type: str,
        total_amount: float,
        vat_amount: float,
        items: List[Dict[str, Any]],
        cash_amount: float = 0,
        card_amount: float = 0,
        amount_tendered: float = 0,
        change_given: float = 0,
        customer_id: Optional[int] = None,
        invoice_number: Optional[str] = None,
        receipt_text: Optional[str] = None,
        cashier_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> int:
        """
        Create a sale with all its items in a single transaction

        Args:
            items: List of dicts with keys:
                - item_name: str
                - unit_price: float
                - quantity: float
                - vat_rate: float (default 0.20)
                - item_id: Optional[int] (inventory item ID)

        Returns:
            sale_id of the created sale
        """
        # Use local time instead of UTC (SQLite CURRENT_TIMESTAMP uses UTC)
        local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Create sale record
            cursor.execute(
                """INSERT INTO sales
                   (receipt_number, customer_id, invoice_number, payment_type,
                    cash_amount, card_amount, amount_tendered, change_given,
                    total_amount, vat_amount, receipt_text, cashier_id, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (receipt_number, customer_id, invoice_number, payment_type,
                 cash_amount, card_amount, amount_tendered, change_given,
                 total_amount, vat_amount, receipt_text, cashier_id, notes, local_time)
            )
            sale_id = cursor.lastrowid

            # Insert all items
            for item in items:
                line_total = item['unit_price'] * item['quantity']
                cursor.execute(
                    """INSERT INTO sold_items
                       (sale_id, item_id, item, item_price, quantity, vat_rate, total)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (sale_id, item.get('item_id'), item['item_name'],
                     item['unit_price'], item['quantity'],
                     item.get('vat_rate', 0.20), line_total)
                )

            return sale_id

    def get_payment_summary_by_date(self, date: str) -> Dict[str, float]:
        """
        Get payment totals by type for a date (replaces PaymentRepository method)
        Accounts for refunds - subtracts refund amounts from totals.

        Args:
            date: Date in format 'YYYY-MM-DD'

        Returns:
            Dict with 'cash', 'card', 'total', 'refunds_cash', 'refunds_card' amounts
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Get sales totals
            cursor.execute(
                """SELECT
                        SUM(cash_amount) as cash_total,
                        SUM(card_amount) as card_total,
                        SUM(total_amount) as total
                   FROM sales
                   WHERE DATE(created_at) = ?""",
                (date,)
            )

            row = cursor.fetchone()
            summary = {
                'cash': row['cash_total'] or 0.0,
                'card': row['card_total'] or 0.0,
                'total': row['total'] or 0.0,
                'refunds_cash': 0.0,
                'refunds_card': 0.0
            }

            # Get refunds and subtract from totals
            cursor.execute(
                """SELECT refund_method, SUM(refund_amount) as refund_total
                   FROM refunds
                   WHERE DATE(created_at) = ?
                   GROUP BY refund_method""",
                (date,)
            )

            for refund_row in cursor.fetchall():
                method = refund_row['refund_method']
                amount = refund_row['refund_total'] or 0

                if method == 'cash':
                    summary['refunds_cash'] = amount
                    summary['cash'] -= amount
                elif method == 'card':
                    summary['refunds_card'] = amount
                    summary['card'] -= amount

                summary['total'] -= amount

            return summary

    def get_sales_with_items_between_dates(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Get all sales between two dates (inclusive) with their items

        Args:
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'

        Returns:
            List of dicts, each with 'sale' and 'items' keys
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """SELECT * FROM sales
                   WHERE DATE(created_at) BETWEEN ? AND ?
                   ORDER BY created_at""",
                (start_date, end_date)
            )
            sales = [dict(row) for row in cursor.fetchall()]

            results = []
            for sale in sales:
                cursor.execute(
                    """SELECT * FROM sold_items
                       WHERE sale_id = ?
                       ORDER BY id""",
                    (sale['id'],)
                )
                items = [dict(row) for row in cursor.fetchall()]
                results.append({
                    'sale': sale,
                    'items': items
                })

            return results

    def get_payment_summary_between_dates(self, start_date: str, end_date: str) -> Dict[str, float]:
        """
        Get payment totals by type between two dates (inclusive)
        Accounts for refunds - subtracts refund amounts from totals.

        Args:
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'

        Returns:
            Dict with 'cash', 'card', 'total', 'refunds_cash', 'refunds_card' amounts
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Get sales totals
            cursor.execute(
                """SELECT
                        SUM(cash_amount) as cash_total,
                        SUM(card_amount) as card_total,
                        SUM(total_amount) as total
                   FROM sales
                   WHERE DATE(created_at) BETWEEN ? AND ?""",
                (start_date, end_date)
            )

            row = cursor.fetchone()
            summary = {
                'cash': row['cash_total'] or 0.0,
                'card': row['card_total'] or 0.0,
                'total': row['total'] or 0.0,
                'refunds_cash': 0.0,
                'refunds_card': 0.0
            }

            # Get refunds and subtract from totals
            cursor.execute(
                """SELECT refund_method, SUM(refund_amount) as refund_total
                   FROM refunds
                   WHERE DATE(created_at) BETWEEN ? AND ?
                   GROUP BY refund_method""",
                (start_date, end_date)
            )

            for refund_row in cursor.fetchall():
                method = refund_row['refund_method']
                amount = refund_row['refund_total'] or 0

                if method == 'cash':
                    summary['refunds_cash'] = amount
                    summary['cash'] -= amount
                elif method == 'card':
                    summary['refunds_card'] = amount
                    summary['card'] -= amount

                summary['total'] -= amount

            return summary

    def get_daily_totals_between_dates(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Get daily totals between two dates for charting/comparison

        Args:
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'

        Returns:
            List of dicts with date, transaction_count, and total_revenue
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT
                        DATE(created_at) as date,
                        COUNT(*) as transaction_count,
                        SUM(total_amount) as total_revenue,
                        SUM(cash_amount) as cash_total,
                        SUM(card_amount) as card_total
                   FROM sales
                   WHERE DATE(created_at) BETWEEN ? AND ?
                   GROUP BY DATE(created_at)
                   ORDER BY date""",
                (start_date, end_date)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_sale_by_receipt_number(self, receipt_number: int) -> Optional[Dict[str, Any]]:
        """
        Get sale by receipt number (replaces ReceiptRepository.get_receipt_by_number)

        Args:
            receipt_number: The receipt number to look up

        Returns:
            Sale record or None
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sales WHERE receipt_number = ?",
                (receipt_number,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_receipt_text(self, sale_id: int, receipt_text: str) -> bool:
        """
        Update receipt text for an existing sale

        Args:
            sale_id: ID of the sale
            receipt_text: The receipt text to store

        Returns:
            True if updated, False if sale not found
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sales SET receipt_text = ? WHERE id = ?",
                (receipt_text, sale_id)
            )
            return cursor.rowcount > 0

    def get_refunds_for_sale(self, sale_id: int) -> List[Dict[str, Any]]:
        """Get all refunds for a specific sale"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM refunds
                   WHERE original_sale_id = ?
                   ORDER BY created_at DESC""",
                (sale_id,)
            )
            return [dict(row) for row in cursor.fetchall()]


class InvoiceRepository:
    """Repository for invoice operations"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create_invoice(self, invoice_number: str, date: str, time: str) -> int:
        """Create new invoice header"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO invoice (invoice, date, time)
                   VALUES (?, ?, ?)""",
                (invoice_number, date, time)
            )
            return cursor.lastrowid
    
    def add_invoice_item(self, invoice_id: int, item: str, price: float, quantity: float):
        """Add item to invoice"""
        total = price * quantity
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO invoice_data (invoice_id, item, price, quantity, total)
                   VALUES (?, ?, ?, ?, ?)""",
                (invoice_id, item, price, quantity, total)
            )
    
    def get_all_invoices(self) -> List[Dict[str, Any]]:
        """Get all invoice headers"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM invoice ORDER BY id ASC"""
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_invoice_details(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """Get complete invoice with all items"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get invoice header
            cursor.execute(
                "SELECT * FROM invoice WHERE id = ?",
                (invoice_id,)
            )
            header = cursor.fetchone()
            if not header:
                return None
            
            # Get invoice items
            cursor.execute(
                """SELECT * FROM invoice_data 
                   WHERE invoice_id = ?
                   ORDER BY id""",
                (invoice_id,)
            )
            items = [dict(row) for row in cursor.fetchall()]
            
            return {
                "header": dict(header),
                "items": items,
                "total": sum(item["total"] for item in items)
            }

class UserRepository:
    """Class for user management"""

    def __init__(self, db: Database):
        self.db = db

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Verify username and password

        Returns:
            User dict if valid, None if invalid
        """
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM users
                   WHERE username = ? AND password_hash = ? AND is_active = 1""",
                (username, password_hash)
            )
            row = cursor.fetchone()

            if row:
                user = dict(row)
                # Update last login
                cursor.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                    (user['id'],)
                )
                return user
            return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users (for admin)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY username")
            return [dict(row) for row in cursor.fetchall()]

    def create_user(self, username: str, password: str, full_name: str, role: str) -> int:
        """Create new user"""
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO users (username, password_hash, full_name, role)
                   VALUES (?, ?, ?, ?)""",
                (username, password_hash, full_name, role)
            )
            return cursor.lastrowid

    def update_password(self, user_id: int, new_password: str) -> bool:
        """Change user password"""
        import hashlib
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id)
            )
            return cursor.rowcount > 0

    def de_activate_user(self, user_id: int, is_active: int) -> bool:
        """Activate/Deactivate user (soft-delete)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (is_active, user_id)
            )
            return cursor.rowcount > 0


    # In pos_db_layer.py, UserRepository class

    def delete_user(self, user_id: int) -> bool:
        """
        Permanently delete a user from the database

        WARNING: This is a hard delete - cannot be undone!
        Consider preventing deletion of:
        - The last admin user
        - Currently logged-in user
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cursor.rowcount > 0


class RefundRepository:
    """Repository for refund operations"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def record_refund(
        self, 
        original_sale_id: int, 
        item: str, 
        quantity: float, 
        refund_amount: float,
        refund_method: str,
        reason: str = "",
        processed_by: Optional[int] = None
    ) -> int:
        """Record a refund transaction"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO refunds 
                   (original_sale_id, item, quantity, refund_amount, reason, refund_method, processed_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (original_sale_id, item, quantity, refund_amount, reason, refund_method, processed_by)
            )
            return cursor.lastrowid
    
    def get_refunds_by_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all refunds for a date"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM refunds 
                   WHERE DATE(created_at) = ?
                   ORDER BY created_at DESC""",
                (date,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_refunds_by_sale(self, sale_id: int) -> List[Dict[str, Any]]:
        """Get all refunds for a specific sale"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM refunds WHERE original_sale_id = ?",
                (sale_id,)
            )
            return [dict(row) for row in cursor.fetchall()]



class CustomerRepository:
    """Repository for customer management"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all customers"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM customers ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]
    
    def search(self, search_term: str) -> List[Dict[str, Any]]:
        """Search customers by name or company"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM customers 
                   WHERE name LIKE ? OR company_name LIKE ?
                   ORDER BY name""",
                (f"%{search_term}%", f"%{search_term}%")
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_by_id(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """Get customer by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create(
        self,
        name: str,
        company_name: str = "",
        pib: str = "",
        jmbg: str = "",
        address: str = "",
        city: str = "",
        postal_code: str = "",
        phone: str = "",
        email: str = "",
        is_company: bool = False,
        notes: str = ""
    ) -> int:
        """Create new customer"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO customers
                   (name, company_name, pib, jmbg, address, city, postal_code, phone, email, is_company, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, company_name, pib, jmbg, address, city, postal_code, phone, email, 1 if is_company else 0, notes)
            )
            return cursor.lastrowid
    
    def update(
        self,
        customer_id: int,
        name: str,
        company_name: str = "",
        pib: str = "",
        jmbg: str = "",
        address: str = "",
        city: str = "",
        postal_code: str = "",
        phone: str = "",
        email: str = "",
        is_company: bool = False,
        notes: str = ""
    ) -> bool:
        """Update customer"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE customers
                   SET name=?, company_name=?, pib=?, jmbg=?, address=?, city=?,
                       postal_code=?, phone=?, email=?, is_company=?, notes=?
                   WHERE id=?""",
                (name, company_name, pib, jmbg, address, city, postal_code, phone, email,
                 1 if is_company else 0, notes, customer_id)
            )
            return cursor.rowcount > 0

    def delete(self, customer_id: int) -> bool:
        """Delete customer by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
            return cursor.rowcount > 0


# ============================================================
# Restaurant Mode Repositories
# ============================================================

class TableRepository:
    """Repository for restaurant table management"""

    def __init__(self, db: Database):
        self.db = db

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all tables ordered by position"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM restaurant_tables
                ORDER BY position_row, position_col
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_active(self) -> List[Dict[str, Any]]:
        """Get only active tables"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM restaurant_tables
                WHERE is_active = 1
                ORDER BY position_row, position_col
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, table_id: int) -> Optional[Dict[str, Any]]:
        """Get table by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM restaurant_tables WHERE id = ?", (table_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create(self, name: str, row: int = 0, col: int = 0, capacity: int = 4) -> int:
        """Create new table"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO restaurant_tables (name, position_row, position_col, capacity)
                   VALUES (?, ?, ?, ?)""",
                (name, row, col, capacity)
            )
            return cursor.lastrowid

    def update(self, table_id: int, name: str, row: int, col: int, capacity: int) -> bool:
        """Update table"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE restaurant_tables
                   SET name=?, position_row=?, position_col=?, capacity=?
                   WHERE id=?""",
                (name, row, col, capacity, table_id)
            )
            return cursor.rowcount > 0

    def set_active(self, table_id: int, is_active: bool) -> bool:
        """Set table active/inactive"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE restaurant_tables SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, table_id)
            )
            return cursor.rowcount > 0

    def delete(self, table_id: int) -> bool:
        """Delete table"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM restaurant_tables WHERE id = ?", (table_id,))
            return cursor.rowcount > 0

    def get_tables_with_status(self) -> List[Dict[str, Any]]:
        """Get all active tables with their current session status"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    t.*,
                    s.id as session_id,
                    s.status as session_status,
                    s.opened_at,
                    COALESCE(s.total_amount, 0) as current_total,
                    u.full_name as waiter_name
                FROM restaurant_tables t
                LEFT JOIN table_sessions s ON t.id = s.table_id AND s.status = 'open'
                LEFT JOIN users u ON s.waiter_id = u.id
                WHERE t.is_active = 1
                ORDER BY t.position_row, t.position_col
            """)
            return [dict(row) for row in cursor.fetchall()]


class TableSessionRepository:
    """Repository for table sessions (when tables are occupied)"""

    def __init__(self, db: Database):
        self.db = db

    def get_open_session(self, table_id: int) -> Optional[Dict[str, Any]]:
        """Get currently open session for a table"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM table_sessions
                WHERE table_id = ? AND status = 'open'
            """, (table_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_by_id(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table_sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def open_session(self, table_id: int, waiter_id: int = None) -> int:
        """Open a new session for a table"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO table_sessions (table_id, waiter_id, status, opened_at)
                   VALUES (?, ?, 'open', ?)""",
                (table_id, waiter_id, datetime.now().isoformat())
            )
            return cursor.lastrowid

    def close_session(self, session_id: int, payment_type: str = 'cash') -> bool:
        """Close a session (table paid and leaving)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE table_sessions
                   SET status = 'closed', closed_at = ?, payment_type = ?
                   WHERE id = ?""",
                (datetime.now().isoformat(), payment_type, session_id)
            )
            return cursor.rowcount > 0

    def update_total(self, session_id: int, total: float) -> bool:
        """Update session total amount"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE table_sessions SET total_amount = ? WHERE id = ?",
                (total, session_id)
            )
            return cursor.rowcount > 0

    def get_session_history(self, table_id: int = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get session history, optionally filtered by table"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if table_id:
                cursor.execute("""
                    SELECT s.*, t.name as table_name, u.full_name as waiter_name
                    FROM table_sessions s
                    JOIN restaurant_tables t ON s.table_id = t.id
                    LEFT JOIN users u ON s.waiter_id = u.id
                    WHERE s.table_id = ?
                    ORDER BY s.opened_at DESC
                    LIMIT ?
                """, (table_id, limit))
            else:
                cursor.execute("""
                    SELECT s.*, t.name as table_name, u.full_name as waiter_name
                    FROM table_sessions s
                    JOIN restaurant_tables t ON s.table_id = t.id
                    LEFT JOIN users u ON s.waiter_id = u.id
                    ORDER BY s.opened_at DESC
                    LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_open_sessions(self) -> List[Dict[str, Any]]:
        """Get all currently open sessions"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, t.name as table_name, u.full_name as waiter_name
                FROM table_sessions s
                JOIN restaurant_tables t ON s.table_id = t.id
                LEFT JOIN users u ON s.waiter_id = u.id
                WHERE s.status = 'open'
                ORDER BY s.opened_at
            """)
            return [dict(row) for row in cursor.fetchall()]


class TableOrderRepository:
    """Repository for orders within a table session"""

    def __init__(self, db: Database):
        self.db = db

    def get_session_orders(self, session_id: int) -> List[Dict[str, Any]]:
        """Get all orders for a session"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM table_orders
                WHERE session_id = ?
                ORDER BY created_at
            """, (session_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Get order by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table_orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_order(
        self,
        session_id: int,
        item_id: int,
        item_name: str,
        quantity: float,
        unit_price: float,
        item_type: str = 'other',
        notes: str = ""
    ) -> int:
        """Add an order to a session"""
        total_price = quantity * unit_price
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO table_orders
                   (session_id, item_id, item_name, quantity, unit_price, total_price, item_type, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, item_id, item_name, quantity, unit_price, total_price, item_type, notes)
            )
            return cursor.lastrowid

    def update_quantity(self, order_id: int, quantity: float, unit_price: float) -> bool:
        """Update order quantity"""
        total_price = quantity * unit_price
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE table_orders
                   SET quantity = ?, total_price = ?
                   WHERE id = ?""",
                (quantity, total_price, order_id)
            )
            return cursor.rowcount > 0

    def update_status(self, order_id: int, status: str) -> bool:
        """Update order status (ordered, preparing, served)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE table_orders SET status = ? WHERE id = ?",
                (status, order_id)
            )
            return cursor.rowcount > 0

    def delete_order(self, order_id: int) -> bool:
        """Delete an order"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM table_orders WHERE id = ?", (order_id,))
            return cursor.rowcount > 0

    def get_session_total(self, session_id: int) -> float:
        """Calculate total for a session"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(total_price), 0) FROM table_orders WHERE session_id = ?",
                (session_id,)
            )
            return cursor.fetchone()[0]

    def get_orders_by_status(self, session_id: int, status: str) -> List[Dict[str, Any]]:
        """Get orders filtered by status"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM table_orders
                WHERE session_id = ? AND status = ?
                ORDER BY created_at
            """, (session_id, status))
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Get all pending orders across all open sessions (for kitchen display)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT o.*, t.name as table_name, s.id as session_id
                FROM table_orders o
                JOIN table_sessions s ON o.session_id = s.id
                JOIN restaurant_tables t ON s.table_id = t.id
                WHERE s.status = 'open' AND o.status = 'ordered'
                ORDER BY o.created_at
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_orders_by_item_type(self, session_id: int, item_type: str) -> List[Dict[str, Any]]:
        """Get orders filtered by item type (food/drink/other)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM table_orders
                WHERE session_id = ? AND item_type = ?
                ORDER BY created_at
            """, (session_id, item_type))
            return [dict(row) for row in cursor.fetchall()]

    def get_new_orders_by_type(self, session_id: int, item_type: str) -> List[Dict[str, Any]]:
        """Get only 'ordered' (not yet printed) orders filtered by item type"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM table_orders
                WHERE session_id = ? AND item_type = ? AND status = 'ordered'
                ORDER BY created_at
            """, (session_id, item_type))
            return [dict(row) for row in cursor.fetchall()]


