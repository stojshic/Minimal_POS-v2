# Development Checklist

## F6 Otpremnice (Invoices) - Screen Redesign ✅ DONE
- [x] Rename F6 from "Invoices" to "Otpremnice"
- [x] Redesign screen layout (two tables side-by-side like F7 Prodaja)
  - [x] Left table: List all previous Otpremnice
  - [x] Right table: Items for current/selected otpremnica
- [x] Left side components:
  - [x] "Nova otpremnica" button (upper left, above datatable)
  - [x] DataTable showing all previous otpremnice
  - [x] Clicking an otpremnica loads its items in right table
- [x] Right side components:
  - [x] Input field (moved from left side)
  - [x] Input field disabled by default
  - [x] Input field enabled when "Nova otpremnica" is clicked
  - [x] "Dodaj stavku" button adds items to right datatable (existing functionality)

## F4 Reports - Weekly and Monthly Reports ✅ DONE
- [x] Add "Nedeljni izvestaj" (weekly report) button
- [x] Add "Mesecni izvestaj" (monthly report) button
- [x] Implement weekly report generation logic
- [x] Implement monthly report generation logic
- [x] Restrict these buttons to Admin users only (already implemented - buttons only show for is_admin=True)

## Logout Security Fix ✅ DONE
- [x] Fix: Admin logs out on restricted screen (e.g., Users), cashier logs in and sees that screen
- [x] Modify logout method to close/pop all screens
- [x] Ensure Sales screen (F2 Prodaja) is shown after any user logs in
- [x] Test with different user roles

## Time Zone Bug ✅ DONE
- [x] Investigate -1 hour time offset on sales
- [x] Example: Sale at 23:23 saves as 22:23
- [x] Check datetime handling in:
  - [x] `pos_business_logic.py` (sell_items, timestamps) - uses local time correctly
  - [x] `pos_db_layer.py` (database storage) - was using SQLite CURRENT_TIMESTAMP (UTC)
  - [x] `receipt_printer.py` (receipt generation) - uses local time correctly
- [x] Fix timezone/UTC conversion issue
  - Root cause: SQLite's CURRENT_TIMESTAMP defaults to UTC
  - Fix: Explicitly pass local time to create_sale and create_sale_with_items

## Inventory Screen - Full Article Editing ✅ DONE
- [x] Currently only price changes are saved
- [x] Implement editing for:
  - [x] Barcode
  - [x] Item name
  - [x] PDV (VAT rate)
- [x] Update `AddEditItemScreen` to use comprehensive `update_item` method
- [x] Add `update_item` method to InventoryRepository (updates all fields)
- [x] Update `add` method to accept vat_rate parameter

## VAT Implementation Audit ✅ DONE
- [x] Audit VAT implementation across the entire application
- [x] Check areas:
  - [x] Inventory items (VAT rate storage) - correctly stored and edited
  - [x] Sales processing (VAT calculation) - uses item's vat_rate correctly
  - [x] Receipts (VAT display) - uses item's vat_rate correctly
  - [x] Reports (VAT breakdown) - fixed hardcoded VAT in legacy report
  - [x] Invoices/Otpremnice (VAT handling) - VAT not stored (low priority for goods receiving)
- [x] Ensure consistent VAT rates from `config.py` are used
- [x] Fix any missing or incorrect VAT calculations
  - Fixed: `_generate_report_legacy` was using hardcoded 0.20, now uses `sale.get('vat_rate', 0.20)`
