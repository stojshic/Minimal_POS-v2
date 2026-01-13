"""
Database layer for POS system
Handles all database operations with clean interfaces
"""
import sqlite3
from contextlib import contextmanager
from typing import List, Optional, Dict, Any
from datetime import datetime

from pandas.core.config_init import pc_east_asian_width_doc


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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Sold items table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sold_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item TEXT NOT NULL,
                    item_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    time TEXT NOT NULL,
                    total REAL NOT NULL,
                    amount_paid REAL,
                    change_given REAL DEFAULT 0
                )
            """)

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
    
    def add(self, item: str, price: float, quantity: float, barcode: Optional[str] = None) -> int:
        """Add new inventory item"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO inventory (item, barcode, price, quantity) 
                   VALUES (?, ?, ?, ?)""",
                (item, barcode, price, quantity)
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


class SalesRepository:
    """Repository for sales transactions"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def record_sale(self, item: str, price: float, quantity: float,
                    amount_paid: Optional[float] = None,
                    change_given: Optional[float] = None) -> int:
        """Record a sale transaction"""
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

class PaymentRepository:
    """Repository for payment operations"""

    def __init__(self, db: Database):
        self.db = db
        
    def record_payment(self, sale_id: int, payment_type: str, amount: float) -> int:
        """
            Record a payment for sale

            Args:
                sale_id: ID of the sale transaction
                payment_type: 'cash' or 'card'
                amount: Amount paid with this method
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO payments (sale_id, payment_type, amount)
                    VALUES (?, ?, ?)""",
                (sale_id, payment_type, amount)
            )
            return cursor.lastrowid

    def get_payments_by_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all payments for a specific date"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT p.*, s.time
                   FROM payments p
                   JOIN sold_items s ON p.sale_id = s.id
                   ORDER BY s.time""",
                (date,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_payment_summary_by_date(self, date: str) -> Dict[str, float]:
        """
        Get payment totals by type for a date

        Returns:
            Dict with 'cash', 'card' and 'total' amounts
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT
                        payment_type,
                        SUM(amount) as total
                    FROM payments p
                    JOIN sold_items s ON p.sale_id = s.id
                    WHERE DATE(s.time) = ?
                    GROUP BY payment_type""",
                (date,)
            )

            results = cursor.fetchall()
            summary = {'cash': 0.0, 'card': 0.0, 'total': 0.0}

            for row in results:
                payment_type = row['payment_type']
                total = row['total']
                summary[payment_type] = total
                summary['total'] += total

            return summary

    def get_sale_payments(self, sale_id: int) -> List[Dict[str, Any]]:
        """Get all payments for a sale"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM payments WHERE sale_id = ?""",
                (sale_id,)
            )
            return [dict(row) for row in cursor.fetchall()]


class ReceiptRepository:
    """Repository for receipt storage"""

    def __init__(self, db: Database):
        self.db = db

    def save_receipt(self, sale_id: int, receipt_number: int, receipt_text: str) -> int:
        """Save receipt copy to database"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO receipts (sale_id, receipt_number, receipt_text)
                   VALUES (?, ?, ?)""",
                (sale_id, receipt_number, receipt_text)
            )
            return cursor.lastrowid

    def get_receipt_by_sale_id(self, sale_id: int) -> Optional[Dict[str, Any]]:
        """Get receipt for a specific sale"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM receipts WHERE sale_id = ?",
                (sale_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_receipt_by_number(self, receipt_number: int) -> Optional[Dict[str, Any]]:
        """Get receipt by receipt number"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM receipts WHERE receipt_number = ?",
                (receipt_number,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None


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

