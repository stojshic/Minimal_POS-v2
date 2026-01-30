"""
Database layer for POS system
Handles all database operations with clean interfaces
"""
import sqlite3
import shutil
import os
from contextlib import contextmanager
from typing import List, Optional, Dict, Any, Tuple
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

    def backup(self, backup_dir: str = "backups") -> Tuple[bool, str]:
        """
        Create a backup of the database.

        Args:
            backup_dir: Directory to store backups

        Returns:
            (success, filepath or error message)
        """
        try:
            # Create backup directory if it doesn't exist
            os.makedirs(backup_dir, exist_ok=True)

            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"data_backup_{timestamp}.db"
            backup_path = os.path.join(backup_dir, backup_filename)

            # Use SQLite's backup API for safe backup
            with sqlite3.connect(self.db_path) as source:
                with sqlite3.connect(backup_path) as dest:
                    source.backup(dest)

            # Verify backup was created
            if os.path.exists(backup_path):
                size_kb = os.path.getsize(backup_path) / 1024
                return True, f"{backup_path} ({size_kb:.1f} KB)"

            return False, "Backup file was not created"

        except Exception as e:
            return False, str(e)

    def get_backup_list(self, backup_dir: str = "backups") -> List[Dict[str, Any]]:
        """Get list of existing backups"""
        backups = []
        if os.path.exists(backup_dir):
            for filename in os.listdir(backup_dir):
                if filename.endswith('.db') and filename.startswith('data_backup_'):
                    filepath = os.path.join(backup_dir, filename)
                    stat = os.stat(filepath)
                    backups.append({
                        'filename': filename,
                        'path': filepath,
                        'size_kb': stat.st_size / 1024,
                        'created_at': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    })
        # Sort by newest first
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        return backups

    def restore_from_backup(self, backup_path: str) -> Tuple[bool, str]:
        """
        Restore database from a backup file.

        WARNING: This will overwrite the current database!

        Args:
            backup_path: Path to the backup file

        Returns:
            (success, message)
        """
        try:
            if not os.path.exists(backup_path):
                return False, "Backup file not found"

            # First create a backup of current state
            self.backup()

            # Copy backup over current database
            shutil.copy2(backup_path, self.db_path)

            return True, "Database restored successfully"

        except Exception as e:
            return False, str(e)

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
                import bcrypt
                # Default admin password: "admin123" (should be changed after first login!)
                default_password = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
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
            # Categories table
            # ============================================================

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    display_order INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    icon TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration: Add category_id to inventory table if it doesn't exist
            cursor.execute("PRAGMA table_info(inventory)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'category_id' not in columns:
                cursor.execute("ALTER TABLE inventory ADD COLUMN category_id INTEGER REFERENCES categories(id)")

            # Seed default categories if table is empty
            cursor.execute("SELECT COUNT(*) FROM categories")
            if cursor.fetchone()[0] == 0:
                default_categories = [
                    ("Bez kategorije", 0, 1, ""),
                    ("Pivo", 1, 1, "🍺"),
                    ("Vino", 2, 1, "🍷"),
                    ("Žestoka pića", 3, 1, "🥃"),
                    ("Sokovi i voda", 4, 1, "🥤"),
                    ("Kafa i čaj", 5, 1, "☕"),
                    ("Predjela", 10, 1, "🥗"),
                    ("Glavno jelo", 11, 1, "🍽️"),
                    ("Roštilj", 12, 1, "🥩"),
                    ("Salate", 13, 1, "🥬"),
                    ("Deserti", 14, 1, "🍰"),
                ]
                cursor.executemany(
                    "INSERT INTO categories (name, display_order, is_active, icon) VALUES (?, ?, ?, ?)",
                    default_categories
                )

            # Assign existing items to "Bez kategorije" (id=1) if they have no category
            cursor.execute("UPDATE inventory SET category_id = 1 WHERE category_id IS NULL")

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
                    last_ticket TEXT,
                    FOREIGN KEY (table_id) REFERENCES restaurant_tables(id),
                    FOREIGN KEY (waiter_id) REFERENCES users(id)
                )
            """)

            # Migration: Add last_ticket column to table_sessions if it doesn't exist
            cursor.execute("PRAGMA table_info(table_sessions)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'last_ticket' not in columns:
                cursor.execute("ALTER TABLE table_sessions ADD COLUMN last_ticket TEXT")

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

            # ============================================================
            # System settings table (key-value store)
            # ============================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Initialize default settings if they don't exist
            cursor.execute("SELECT COUNT(*) FROM settings WHERE key = 'receipt_counter'")
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO settings (key, value) VALUES ('receipt_counter', '1')"
                )

            # ============================================================
            # Login attempts tracking table (for brute-force protection)
            # ============================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    attempt_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    success INTEGER DEFAULT 0,
                    ip_address TEXT
                )
            """)

            # Add index for faster username lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_login_attempts_username
                ON login_attempts(username, attempt_time)
            """)

            # ============================================================
            # Stock adjustments table (for inventory corrections with audit trail)
            # ============================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    adjustment_type TEXT NOT NULL,
                    quantity_before REAL NOT NULL,
                    quantity_change REAL NOT NULL,
                    quantity_after REAL NOT NULL,
                    reason_code TEXT NOT NULL,
                    notes TEXT,
                    adjusted_by INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_id) REFERENCES inventory(id),
                    FOREIGN KEY (adjusted_by) REFERENCES users(id)
                )
            """)


class SettingsRepository:
    """Repository for system settings (key-value store)"""

    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: str = None) -> Optional[str]:
        """Get a setting value by key"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else default

    def get_int(self, key: str, default: int = 0) -> int:
        """Get a setting value as integer"""
        value = self.get(key)
        return int(value) if value is not None else default

    def set(self, key: str, value: str) -> bool:
        """Set a setting value (insert or update)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO settings (key, value, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP""",
                (key, value, value)
            )
            return cursor.rowcount > 0

    def increment(self, key: str) -> int:
        """Increment a numeric setting and return the new value"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE settings
                   SET value = CAST(value AS INTEGER) + 1,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE key = ?""",
                (key,)
            )
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return int(row['value']) if row else 0


class StockAdjustmentRepository:
    """Repository for stock adjustment operations"""

    # Standard reason codes for stock adjustments
    REASON_CODES = {
        'count': 'Inventura',
        'damage': 'Oštećenje',
        'theft': 'Krađa',
        'expired': 'Istekao rok',
        'return_supplier': 'Povraćaj dobavljaču',
        'correction': 'Korekcija greške',
        'sample': 'Uzorak/Degustacija',
        'internal_use': 'Interna upotreba',
        'other': 'Ostalo',
    }

    def __init__(self, db: Database):
        self.db = db

    def record_adjustment(
        self,
        item_id: int,
        item_name: str,
        adjustment_type: str,
        quantity_before: float,
        quantity_change: float,
        quantity_after: float,
        reason_code: str,
        notes: str = "",
        adjusted_by: Optional[int] = None
    ) -> int:
        """Record a stock adjustment"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO stock_adjustments
                   (item_id, item_name, adjustment_type, quantity_before,
                    quantity_change, quantity_after, reason_code, notes, adjusted_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item_id, item_name, adjustment_type, quantity_before,
                 quantity_change, quantity_after, reason_code, notes, adjusted_by)
            )
            return cursor.lastrowid

    def get_adjustments_by_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all adjustments for a specific date"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT sa.*, u.full_name as adjusted_by_name
                   FROM stock_adjustments sa
                   LEFT JOIN users u ON sa.adjusted_by = u.id
                   WHERE DATE(sa.created_at) = ?
                   ORDER BY sa.created_at DESC""",
                (date,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_adjustments_by_item(self, item_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get adjustment history for a specific item"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT sa.*, u.full_name as adjusted_by_name
                   FROM stock_adjustments sa
                   LEFT JOIN users u ON sa.adjusted_by = u.id
                   WHERE sa.item_id = ?
                   ORDER BY sa.created_at DESC
                   LIMIT ?""",
                (item_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_recent_adjustments(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent adjustments across all items"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT sa.*, u.full_name as adjusted_by_name
                   FROM stock_adjustments sa
                   LEFT JOIN users u ON sa.adjusted_by = u.id
                   ORDER BY sa.created_at DESC
                   LIMIT ?""",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]


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
        """Search inventory by item name, including category info"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT i.*, c.name as category_name, c.icon as category_icon
                   FROM inventory i
                   LEFT JOIN categories c ON i.category_id = c.id
                   WHERE i.item LIKE ?
                   ORDER BY i.item""",
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
            vat_rate: float = 0.20, item_type: str = 'other', category_id: Optional[int] = 1) -> int:
        """Add new inventory item"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO inventory (item, barcode, price, quantity, vat_rate, item_type, category_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (item, barcode, price, quantity, vat_rate, item_type, category_id)
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
                    item_type: str = 'other', category_id: Optional[int] = 1) -> bool:
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
                       category_id = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (name, barcode, price, quantity, vat_rate, item_type, category_id, item_id)
            )
            return cursor.rowcount > 0

    def get_by_category(self, category_id: Optional[int] = None, search_term: str = "") -> List[Dict[str, Any]]:
        """Get inventory items filtered by category and optional search term"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if category_id is None:
                # No category filter - return all items
                cursor.execute(
                    """SELECT i.*, c.name as category_name, c.icon as category_icon
                       FROM inventory i
                       LEFT JOIN categories c ON i.category_id = c.id
                       WHERE i.item LIKE ?
                       ORDER BY i.item""",
                    (f"%{search_term}%",)
                )
            else:
                cursor.execute(
                    """SELECT i.*, c.name as category_name, c.icon as category_icon
                       FROM inventory i
                       LEFT JOIN categories c ON i.category_id = c.id
                       WHERE i.category_id = ? AND i.item LIKE ?
                       ORDER BY i.item""",
                    (category_id, f"%{search_term}%")
                )
            return [dict(row) for row in cursor.fetchall()]


class CategoryRepository:
    """Repository for category management"""

    def __init__(self, db: Database):
        self.db = db

    def get_all(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all categories ordered by display_order"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if include_inactive:
                cursor.execute(
                    "SELECT * FROM categories ORDER BY display_order, name"
                )
            else:
                cursor.execute(
                    "SELECT * FROM categories WHERE is_active = 1 ORDER BY display_order, name"
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Get category by ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get category by name"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM categories WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create(self, name: str, display_order: int = 0, icon: str = "") -> int:
        """Create a new category"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO categories (name, display_order, icon)
                   VALUES (?, ?, ?)""",
                (name, display_order, icon)
            )
            return cursor.lastrowid

    def update(self, category_id: int, name: str, display_order: int, icon: str) -> bool:
        """Update category"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE categories
                   SET name = ?, display_order = ?, icon = ?
                   WHERE id = ?""",
                (name, display_order, icon, category_id)
            )
            return cursor.rowcount > 0

    def set_active(self, category_id: int, is_active: bool) -> bool:
        """Set category active/inactive"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE categories SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, category_id)
            )
            return cursor.rowcount > 0

    def delete(self, category_id: int) -> bool:
        """Delete a category (moves items to 'Bez kategorije')"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Move items from this category to "Bez kategorije" (id=1)
            cursor.execute(
                "UPDATE inventory SET category_id = 1 WHERE category_id = ?",
                (category_id,)
            )
            # Delete the category
            cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            return cursor.rowcount > 0

    def get_item_count(self, category_id: int) -> int:
        """Get count of items in a category"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM inventory WHERE category_id = ?",
                (category_id,)
            )
            return cursor.fetchone()[0]


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

    def get_recent_sales(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent sales with proper date from sales table"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT si.*, COALESCE(si.time, s.created_at) as sale_date
                   FROM sold_items si
                   LEFT JOIN sales s ON si.sale_id = s.id
                   ORDER BY si.id DESC LIMIT ?""",
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

class UnifiedSalesRepository:
    """Repository for the new unified sales table (Phase 1 of DB refactoring)"""

    def __init__(self, db: Database):
        self.db = db

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

    def authenticate(self, username: str, password: str,
                     max_attempts: int = 5, lockout_minutes: int = 15) -> tuple:
        """
        Verify username and password with brute-force protection.

        Supports both legacy SHA-256 and new bcrypt password hashes.
        Legacy passwords are automatically upgraded to bcrypt on successful login.

        Args:
            username: The username to authenticate
            password: The password to verify
            max_attempts: Maximum failed attempts before lockout
            lockout_minutes: Duration of lockout in minutes

        Returns:
            Tuple of (user_dict or None, error_message or None)
            - (user, None) on success
            - (None, "locked:X") if locked out (X = remaining minutes)
            - (None, "invalid") if credentials invalid
        """
        import hashlib
        import bcrypt

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Check for lockout first (inline to use same connection)
            cursor.execute(
                """SELECT COUNT(*) FROM login_attempts
                   WHERE username = ? AND success = 0
                   AND attempt_time > datetime('now', ? || ' minutes')""",
                (username, -lockout_minutes)
            )
            failed_count = cursor.fetchone()[0]

            if failed_count >= max_attempts:
                # Calculate remaining lockout time
                cursor.execute(
                    """SELECT MIN(attempt_time) FROM login_attempts
                       WHERE username = ? AND success = 0
                       AND attempt_time > datetime('now', ? || ' minutes')""",
                    (username, -lockout_minutes)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    from datetime import datetime
                    first_attempt = datetime.fromisoformat(row[0])
                    now = datetime.now()
                    elapsed = (now - first_attempt).total_seconds() / 60
                    remaining = int(lockout_minutes - elapsed) + 1
                    return (None, f"locked:{max(1, remaining)}")
                return (None, f"locked:{lockout_minutes}")

            # Get user by username
            cursor.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1",
                (username,)
            )
            row = cursor.fetchone()

            if not row:
                # Record failed attempt for non-existent users (prevent enumeration)
                cursor.execute(
                    "INSERT INTO login_attempts (username, success) VALUES (?, 0)",
                    (username,)
                )
                return (None, "invalid")

            user = dict(row)
            stored_hash = user['password_hash']
            authenticated = False

            # Check if it's a bcrypt hash (starts with $2b$ or $2a$ or $2y$)
            if stored_hash.startswith('$2'):
                # Modern bcrypt verification
                if bcrypt.checkpw(password.encode(), stored_hash.encode()):
                    authenticated = True
                    cursor.execute(
                        "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                        (user['id'],)
                    )
            else:
                # Legacy SHA-256 verification
                legacy_hash = hashlib.sha256(password.encode()).hexdigest()
                if stored_hash == legacy_hash:
                    authenticated = True
                    # Migrate to bcrypt on successful login
                    new_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                    cursor.execute(
                        "UPDATE users SET password_hash = ?, last_login = CURRENT_TIMESTAMP WHERE id = ?",
                        (new_hash, user['id'])
                    )

            if authenticated:
                # Clear failed attempts and record success
                cursor.execute(
                    "DELETE FROM login_attempts WHERE username = ? AND success = 0",
                    (username,)
                )
                cursor.execute(
                    "INSERT INTO login_attempts (username, success) VALUES (?, 1)",
                    (username,)
                )
                return (user, None)
            else:
                # Record failed attempt
                cursor.execute(
                    "INSERT INTO login_attempts (username, success) VALUES (?, 0)",
                    (username,)
                )
                return (None, "invalid")

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users (for admin)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY username")
            return [dict(row) for row in cursor.fetchall()]

    def create_user(self, username: str, password: str, full_name: str, role: str) -> int:
        """Create new user with bcrypt password hashing"""
        import bcrypt
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO users (username, password_hash, full_name, role)
                   VALUES (?, ?, ?, ?)""",
                (username, password_hash, full_name, role)
            )
            return cursor.lastrowid

    def update_password(self, user_id: int, new_password: str) -> bool:
        """Change user password using bcrypt"""
        import bcrypt
        password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

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

    def record_login_attempt(self, username: str, success: bool) -> None:
        """Record a login attempt (successful or failed)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO login_attempts (username, success) VALUES (?, ?)",
                (username, 1 if success else 0)
            )

    def get_failed_attempts_count(self, username: str, minutes: int = 15) -> int:
        """Get count of failed login attempts in the last N minutes"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(*) FROM login_attempts
                   WHERE username = ? AND success = 0
                   AND attempt_time > datetime('now', ? || ' minutes')""",
                (username, -minutes)
            )
            return cursor.fetchone()[0]

    def clear_failed_attempts(self, username: str) -> None:
        """Clear failed login attempts for a user (call on successful login)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM login_attempts WHERE username = ? AND success = 0",
                (username,)
            )

    def is_locked_out(self, username: str, max_attempts: int = 5, lockout_minutes: int = 15) -> tuple:
        """
        Check if user is locked out due to too many failed attempts.

        Returns:
            (is_locked: bool, remaining_minutes: int)
        """
        failed_count = self.get_failed_attempts_count(username, lockout_minutes)
        if failed_count >= max_attempts:
            # Get time of first failed attempt in the window to calculate remaining lockout
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT MIN(attempt_time) FROM login_attempts
                       WHERE username = ? AND success = 0
                       AND attempt_time > datetime('now', ? || ' minutes')""",
                    (username, -lockout_minutes)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    from datetime import datetime
                    first_attempt = datetime.fromisoformat(row[0])
                    now = datetime.now()
                    elapsed = (now - first_attempt).total_seconds() / 60
                    remaining = int(lockout_minutes - elapsed) + 1
                    return (True, max(1, remaining))
            return (True, lockout_minutes)
        return (False, 0)


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

    def save_last_ticket(self, session_id: int, ticket_text: str) -> bool:
        """Save last printed ticket for a session (for re-printing)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE table_sessions SET last_ticket = ? WHERE id = ?",
                (ticket_text, session_id)
            )
            return cursor.rowcount > 0

    def get_last_ticket(self, session_id: int) -> Optional[str]:
        """Get last printed ticket for a session"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_ticket FROM table_sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            return row['last_ticket'] if row else None

    # ============================================================
    # Report Methods
    # ============================================================

    def get_sessions_by_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all closed sessions for a specific date"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, t.name as table_name, u.full_name as waiter_name
                FROM table_sessions s
                JOIN restaurant_tables t ON s.table_id = t.id
                LEFT JOIN users u ON s.waiter_id = u.id
                WHERE DATE(s.closed_at) = ? AND s.status = 'closed'
                ORDER BY s.closed_at
            """, (date,))
            return [dict(row) for row in cursor.fetchall()]

    def get_sales_by_table(self, date: str) -> List[Dict[str, Any]]:
        """Get sales grouped by table for a date"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    t.id as table_id,
                    t.name as table_name,
                    COUNT(s.id) as session_count,
                    COALESCE(SUM(s.total_amount), 0) as total_revenue,
                    AVG(
                        CASE WHEN s.closed_at IS NOT NULL
                        THEN (julianday(s.closed_at) - julianday(s.opened_at)) * 24 * 60
                        ELSE NULL END
                    ) as avg_duration_minutes
                FROM restaurant_tables t
                LEFT JOIN table_sessions s ON t.id = s.table_id
                    AND DATE(s.closed_at) = ? AND s.status = 'closed'
                WHERE t.is_active = 1
                GROUP BY t.id, t.name
                ORDER BY total_revenue DESC
            """, (date,))
            return [dict(row) for row in cursor.fetchall()]

    def get_sales_by_waiter(self, date: str) -> List[Dict[str, Any]]:
        """Get sales grouped by waiter for a date"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    u.id as waiter_id,
                    u.full_name as waiter_name,
                    COUNT(s.id) as session_count,
                    COALESCE(SUM(s.total_amount), 0) as total_revenue,
                    AVG(s.total_amount) as avg_ticket
                FROM table_sessions s
                JOIN users u ON s.waiter_id = u.id
                WHERE DATE(s.closed_at) = ? AND s.status = 'closed'
                GROUP BY u.id, u.full_name
                ORDER BY total_revenue DESC
            """, (date,))
            return [dict(row) for row in cursor.fetchall()]

    def get_turnover_stats(self, date: str) -> Dict[str, Any]:
        """Get table turnover statistics for a date"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total_sessions,
                    AVG(
                        (julianday(closed_at) - julianday(opened_at)) * 24 * 60
                    ) as avg_duration_minutes,
                    MIN(
                        (julianday(closed_at) - julianday(opened_at)) * 24 * 60
                    ) as min_duration_minutes,
                    MAX(
                        (julianday(closed_at) - julianday(opened_at)) * 24 * 60
                    ) as max_duration_minutes
                FROM table_sessions
                WHERE DATE(closed_at) = ? AND status = 'closed'
                    AND closed_at IS NOT NULL AND opened_at IS NOT NULL
            """, (date,))
            row = cursor.fetchone()
            return dict(row) if row else {
                'total_sessions': 0,
                'avg_duration_minutes': 0,
                'min_duration_minutes': 0,
                'max_duration_minutes': 0
            }

    def get_session_history(self, limit: int = 50, table_id: int = None) -> List[Dict[str, Any]]:
        """Get recent session history"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if table_id:
                cursor.execute("""
                    SELECT s.*, t.name as table_name, u.full_name as waiter_name
                    FROM table_sessions s
                    JOIN restaurant_tables t ON s.table_id = t.id
                    LEFT JOIN users u ON s.waiter_id = u.id
                    WHERE s.table_id = ? AND s.status = 'closed'
                    ORDER BY s.closed_at DESC
                    LIMIT ?
                """, (table_id, limit))
            else:
                cursor.execute("""
                    SELECT s.*, t.name as table_name, u.full_name as waiter_name
                    FROM table_sessions s
                    JOIN restaurant_tables t ON s.table_id = t.id
                    LEFT JOIN users u ON s.waiter_id = u.id
                    WHERE s.status = 'closed'
                    ORDER BY s.closed_at DESC
                    LIMIT ?
                """, (limit,))
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

    def find_order_by_item(self, session_id: int, item_id: int) -> Optional[Dict[str, Any]]:
        """Find existing order for an item in a session (for aggregation)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM table_orders
                WHERE session_id = ? AND item_id = ?
                LIMIT 1
            """, (session_id, item_id))
            row = cursor.fetchone()
            return dict(row) if row else None

    def increment_quantity(self, order_id: int, additional_qty: float) -> bool:
        """Increment order quantity by additional amount"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE table_orders
                   SET quantity = quantity + ?,
                       total_price = (quantity + ?) * unit_price
                   WHERE id = ?""",
                (additional_qty, additional_qty, order_id)
            )
            return cursor.rowcount > 0

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


