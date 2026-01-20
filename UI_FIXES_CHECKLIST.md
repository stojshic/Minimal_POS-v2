# UI Fixes Checklist

## Tasks

### 1. Remove F11 Refunds Screen ✅ COMPLETED
- [x] Remove F11 binding from POSApp.BINDINGS
- [x] Remove `action_refunds()` method from POSApp
- [x] Keep RefundsScreen class for reference (logic reuse) or remove entirely

### 2. Implement Refund from F7 (Sales History) Screen ✅ COMPLETED
- [x] Create new `RefundSaleScreen` that opens when clicking "Povraćaj" button
- [x] RefundSaleScreen should display:
  - [x] Sale/receipt info header (receipt number, date, total)
  - [x] DataTable with all items from the receipt (item, quantity sold, price, total)
  - [x] Quantity already refunded (if partial refund was done before)
- [x] Three action buttons:
  - [x] "Povraćaj ceo račun" - Refund entire invoice
  - [x] "Povraćaj stavku" - Refund selected item (opens quantity input)
  - [x] "Zatvori" - Close/cancel
- [x] Quantity input validation:
  - [x] Min: 1
  - [x] Max: quantity sold minus already refunded
  - [x] Show error if trying to refund more than available
- [x] After refund:
  - [x] Record refund in database
  - [x] Update inventory (return items to stock)
  - [x] Update sale status if fully refunded
  - [x] Show confirmation message

### 3. Fix Receipt Viewer After Sale ✅ COMPLETED
- [x] Find where `handle_checkout()` processes the sale result
- [x] Updated to use `unified_sales.get_by_id()` instead of deprecated receipts repo
- [x] Pass sale data (receipt text, items, customer) to ReceiptViewerScreen
- [x] Verify receipt is displayed correctly

### 4. Fix Footer Not Showing on Screens ✅ COMPLETED
- [x] Added `yield Footer()` to screen compose() methods
- [x] Fixed on: CustomerManagementScreen, InventoryManagementScreen, UserManagementScreen
- [x] Fixed on: ReportsScreen, DailyReportScreen, InvoiceManagementScreen
- [x] Fixed on: SalesHistoryScreen, RefundsScreen

### 5. F2 Returns to Main Screen from Any Screen ✅ COMPLETED
- [x] Added F2 binding to each screen's BINDINGS pointing to "close" action
- [x] Added to: CustomerManagementScreen, UserManagementScreen, InventoryManagementScreen
- [x] Added to: InvoiceManagementScreen, ReportsScreen, DailyReportScreen, SalesHistoryScreen
- [x] Test from: F6 (Invoices), F7 (Sales), F4 (Reports), etc.

### 6. Fix Screen Stacking (Main Screens Should Not Stack) ✅ COMPLETED
- [x] Created `open_main_screen()` method in POSApp
  - [x] Dismisses all screens back to base (POS sales screen)
  - [x] Then pushes the new main screen
- [x] Updated action methods to use `open_main_screen()`:
  - [x] `action_user_management()`
  - [x] `action_customers()`
  - [x] `action_sales_history()`
  - [x] `action_invoices()`
  - [x] `action_inventory()`
  - [x] `action_reports()`
- [x] Sub-screens (RefundSaleScreen, DailyReportScreen, etc.) still use `push_screen()` to stack correctly

---

## Implementation Summary

### New Screens Added:
1. **RefundSaleScreen** - Main refund screen showing sale items with refund status
2. **RefundItemQuantityScreen** - Dialog for entering quantity to refund for single item
3. **RefundConfirmScreen** - Confirmation dialog for full receipt refund

### Key Methods Added to POSApp:
- `open_main_screen()` - Opens a main screen without stacking (dismisses existing screens first)

### Screen Stacking Behavior:
```
Base Screen (POS Sales)
    ↓ F3, F4, F6, F7, F8, F10
Main Screen (e.g., Inventory, Reports, Sales History)
    ↓ Sub-screen actions (refund, daily report, etc.)
Sub-Screen (e.g., RefundSaleScreen, DailyReportScreen)
    ↓ Dialog actions
Dialog Screen (e.g., RefundItemQuantityScreen)
```

**Navigation Rules:**
- Main screens (F3, F4, F6, F7, F8, F10) → Replace any existing main screen
- Sub-screens → Stack on top of their parent main screen
- ESC from main screen → Returns to POS sales screen
- ESC from sub-screen → Returns to parent main screen
- F2 from anywhere → Returns to POS sales screen
