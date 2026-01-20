# Database Refactoring Checklist

## Current State

### Existing Tables
| Table | Purpose | Columns |
|-------|---------|---------|
| `sold_items` | Individual sold items (not linked to parent sale) | id, item, item_price, quantity, time, total, amount_paid, change_given |
| `payments` | Payment records per sale | id, sale_id, payment_type, amount, created_at |
| `receipts` | Receipt text copies | id, sale_id, receipt_number, receipt_text, created_at |
| `customer_invoices` | A4 invoices to customers | id, invoice_number, customer_id, issue_date, due_date, total_amount, vat_amount, status, notes, created_at |
| `customer_invoice_items` | Items in customer invoices | id, invoice_id, item_name, quantity, unit_price, vat_rate, total |
| `refunds` | Refund records | id, original_sale_id, item, quantity, refund_amount, reason, refund_method, processed_by, created_at |

### Problems
1. `sold_items` has no parent "sale" - each item is independent
2. Multiple items in one transaction have different timestamps
3. `payments` and `receipts` duplicate sale_id and created_at
4. `customer_invoices` is separate from regular sales but could be unified

---

## Refactoring Tasks

### Phase 1: Create Unified Sales Table ✅ COMPLETED
- [x] Design new `sales` table schema:
  ```sql
  CREATE TABLE sales (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      receipt_number INTEGER NOT NULL,
      customer_id INTEGER,              -- NULL for regular sales, set for customer invoices
      invoice_number TEXT,              -- NULL for regular sales, set for customer invoices
      payment_type TEXT NOT NULL,       -- 'cash', 'card', 'split'
      cash_amount REAL DEFAULT 0,
      card_amount REAL DEFAULT 0,
      amount_tendered REAL DEFAULT 0,
      change_given REAL DEFAULT 0,
      total_amount REAL NOT NULL,
      vat_amount REAL NOT NULL,
      receipt_text TEXT,                -- Full receipt text
      status TEXT DEFAULT 'completed',  -- 'completed', 'refunded', 'partial_refund'
      notes TEXT,
      cashier_id INTEGER,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (customer_id) REFERENCES customers(id),
      FOREIGN KEY (cashier_id) REFERENCES users(id)
  )
  ```
- [x] Created `UnifiedSalesRepository` class with methods:
  - `create_sale()` - creates sale record
  - `get_by_id()` - get sale by ID
  - `get_sales_by_date()` - for reports
  - `get_sales_by_customer()` - customer history
  - `get_recent_sales()` - recent sales list
  - `update_status()` - update sale status
  - `get_next_receipt_number()` - auto-increment receipt numbers

### Phase 2: Link Sold Items to Sales ✅ COMPLETED
- [x] Add `sale_id` foreign key column to `sold_items`
- [x] Add `item_id` foreign key column to `sold_items` (optional link to inventory)
- [x] Add `vat_rate` column to `sold_items`
- [x] Add migration for existing databases (columns added if not present)
- [x] Add `record_sale_item()` to SalesRepository
- [x] Add `get_items_by_sale_id()` to SalesRepository
- [x] Add `get_sale_with_items()` to UnifiedSalesRepository
- [x] Add `get_sales_with_items_by_date()` to UnifiedSalesRepository
- [x] Add `create_sale_with_items()` to UnifiedSalesRepository (atomic transaction)
- [ ] Remove `time`, `amount_paid`, `change_given` columns (deferred to Phase 3 migration)
- [x] Current schema:
  ```sql
  CREATE TABLE sold_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sale_id INTEGER,                  -- NEW: Link to sales table
      item_id INTEGER,                  -- NEW: Link to inventory item (optional)
      item TEXT NOT NULL,
      item_price REAL NOT NULL,
      quantity REAL NOT NULL,
      vat_rate REAL DEFAULT 0.20,       -- NEW: VAT rate
      total REAL NOT NULL,
      time TEXT,                        -- DEPRECATED: Use sale's created_at
      amount_paid REAL,                 -- DEPRECATED: Use sale's amount_tendered
      change_given REAL DEFAULT 0,      -- DEPRECATED: Use sale's change_given
      FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
      FOREIGN KEY (item_id) REFERENCES inventory(id)
  )
  ```

### Phase 3: Remove Redundant Tables ✅ COMPLETED
- [x] Migrate data from `payments` to `sales` table
- [x] Migrate data from `receipts` to `sales` table
- [x] Migrate data from `customer_invoices` to `sales` table
- [x] Migrate data from `customer_invoice_items` to `sold_items` table
- [x] Add `_migrations` table for tracking applied migrations
- [x] Add `run_migrations()` method to Database class
- [x] Add `verify_migration()` method to check migration success
- [x] Add `cleanup_old_tables()` method to drop old tables (requires confirmation)
- [ ] Drop `payments` table (run `cleanup_old_tables(confirm=True)` after verification)
- [ ] Drop `receipts` table
- [ ] Drop `customer_invoices` table
- [ ] Drop `customer_invoice_items` table

**How to run the migration:**
```python
from pos_db_layer import Database

db = Database()

# Run the migration
stats = db.run_migrations()
print(f"Migration stats: {stats}")

# Verify success
verification = db.verify_migration()
print(f"Verification: {verification}")

# If verification passes, drop old tables
if verification['success']:
    cleanup = db.cleanup_old_tables(confirm=True)
    print(f"Cleanup: {cleanup}")
```

### Phase 4: Update Refunds Table ✅ COMPLETED
- [x] Update `refunds.original_sale_id` to reference new `sales` table
- [x] Add `migrate_refunds_to_sales()` method to Database class
- [x] Verify foreign key integrity

**Run Phase 4:**
```python
db.migrate_refunds_to_sales()
```

### Phase 5: Update Repository Classes ✅ COMPLETED
- [x] `UnifiedSalesRepository` has all needed methods:
  - [x] `create_sale()` - creates sale record
  - [x] `create_sale_with_items()` - creates sale with items in transaction
  - [x] `get_by_id()` - get sale by ID
  - [x] `get_sale_with_items()` - returns sale with items
  - [x] `get_sales_by_date()` - for reports
  - [x] `get_sales_with_items_by_date()` - sales with items for a date
  - [x] `get_sales_by_customer()` - customer history
  - [x] `get_payment_summary_by_date()` - payment totals by type
  - [x] `get_sale_by_receipt_number()` - lookup by receipt number
  - [x] `update_receipt_text()` - update receipt text
  - [x] `get_refunds_for_sale()` - get refunds for a sale
- [x] `SalesRepository` has new methods for sold_items:
  - [x] `record_sale_item()` - record item linked to sale
  - [x] `get_items_by_sale_id()` - get items for a sale
- [x] Mark `PaymentRepository` as DEPRECATED
- [x] Mark `ReceiptRepository` as DEPRECATED
- [x] Mark `CustomerInvoiceRepository` as DEPRECATED

### Phase 6: Update Business Logic ✅ COMPLETED
- [x] Update `POSService.__init__()` to accept `unified_sales_repo`
- [x] Update `POSService.sell_multiple_items()` to use new structure
  - Uses `unified_sales.create_sale_with_items()` for atomic transaction
  - Falls back to old structure if unified_sales_repo not provided
- [x] Update `DailyReportService.__init__()` to accept `unified_sales_repo`
- [x] Update `DailyReportService.generate_daily_report()` to query new tables
  - Added `_generate_report_unified()` for new structure
  - Added `_generate_report_legacy()` for backward compatibility
- [x] Update `DailyReportService.generate_cash_reconciliation()` to use new structure
- [ ] Update `RefundService` to use new sale structure (deferred - works with current FK update)

### Phase 7: Update UI Layer ✅ COMPLETED
- [x] Import `UnifiedSalesRepository` in pos_tui.py
- [x] Create `unified_sales_repo` instance in `POSApp.__init__()`
- [x] Pass `unified_sales_repo` to `POSService`
- [x] Pass `unified_sales_repo` to `DailyReportService`
- [x] Store `unified_sales` reference in POSApp for direct access
- [ ] Update `ReceiptViewerScreen` (optional - works with current structure)
- [ ] Update reports screens (optional - uses DailyReportService)
- [ ] Update refunds screen (optional - works with FK update)

### Phase 8: Migration Script ✅ COMPLETED (Integrated into Database class)
- [x] `run_migrations()` - Migrates existing data
- [x] `verify_migration()` - Verifies data integrity
- [x] `cleanup_old_tables(confirm=True)` - Drops old tables
- [x] `get_migration_status()` - Check applied migrations

### Phase 9: New Sales Screen (F7) ✅ COMPLETED
- [x] Rename F7 from "Refunds" to "Prodaja" (Sales)
- [x] Move Refunds to F11
- [x] Create new `SalesHistoryScreen` with split-panel layout:
  - [x] Left panel (30% width):
    - [x] List of receipts/sales
    - [x] Show receipt number, time, total
    - [x] Clickable rows to select sale
  - [x] Right panel (70% width):
    - [x] Show items from selected receipt
    - [x] Display item name, quantity, price, total
- [x] Keep date input at top ("Pretraga prodaje")
- [x] Default to today's date on screen open
- [x] Add keyboard navigation between panels (Tab key)
- [x] Add "Povraćaj" button (placeholder for refund functionality)
- [x] Add "Štampaj" button for printing receipt

```
┌─────────────────────────────────────────────────────────────┐
│ Pretraga prodaje: [2024-01-19        ]                      │
├─────────────────┬───────────────────────────────────────────┤
│ Računi          │ Stavke računa #001                        │
├─────────────────┼───────────────────────────────────────────┤
│ #001  14:30:22  │ Artikal           Kol.   Cena     Ukupno  │
│ #002  14:45:10  │ ─────────────────────────────────────────│
│ #003  15:02:33  │ Mleko 1L          2.00   120.00   240.00  │
│ #004  15:30:00  │ Hleb              1.00    80.00    80.00  │
│ ...             │ Jogurt            3.00    50.00   150.00  │
│                 │ ─────────────────────────────────────────│
│                 │ UKUPNO:                          470.00   │
│                 │ Plaćeno: Gotovina                         │
├─────────────────┴───────────────────────────────────────────┤
│ [Povraćaj]  [Štampaj]  [Zatvori]                           │
└─────────────────────────────────────────────────────────────┘
```

---

## New Unified Structure

```
sales (1) -----> (many) sold_items
   |
   +---> customer_id (optional, for invoices)
   +---> receipt_text (fiscal receipt)
   +---> payment info (cash/card amounts)
   +---> invoice_number (if customer invoice)
```

## Benefits
1. Single source of truth for all sales
2. Proper linking between sale and items
3. Consistent timestamps
4. Customer invoices are just sales with customer_id set
5. Easier reporting and querying
6. Reduced data duplication
