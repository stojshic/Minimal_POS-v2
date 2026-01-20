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

## F4 Reports - Weekly and Monthly Reports
- [ ] Add "Nedeljni izvestaj" (weekly report) button
- [ ] Add "Mesecni izvestaj" (monthly report) button
- [ ] Implement weekly report generation logic
- [ ] Implement monthly report generation logic
- [ ] Restrict these buttons to Admin users only (hide or disable for cashiers)

## Logout Security Fix
- [ ] Fix: Admin logs out on restricted screen (e.g., Users), cashier logs in and sees that screen
- [ ] Modify logout method to close/pop all screens
- [ ] Ensure Sales screen (F7 Prodaja) is shown after any user logs in
- [ ] Test with different user roles

## Time Zone Bug
- [ ] Investigate -1 hour time offset on sales
- [ ] Example: Sale at 23:23 saves as 22:23
- [ ] Check datetime handling in:
  - [ ] `pos_business_logic.py` (sell_items, timestamps)
  - [ ] `pos_db_layer.py` (database storage)
  - [ ] `receipt_printer.py` (receipt generation)
- [ ] Fix timezone/UTC conversion issue

## Inventory Screen - Full Article Editing
- [ ] Currently only price changes are saved
- [ ] Implement editing for:
  - [ ] Barcode
  - [ ] Item name
  - [ ] PDV (VAT rate)
- [ ] Update `UpdateItemScreen` or create comprehensive edit dialog
- [ ] Update repository methods if needed

## VAT Implementation Audit
- [ ] Audit VAT implementation across the entire application
- [ ] Check areas:
  - [ ] Inventory items (VAT rate storage)
  - [ ] Sales processing (VAT calculation)
  - [ ] Receipts (VAT display)
  - [ ] Reports (VAT breakdown)
  - [ ] Invoices/Otpremnice (VAT handling)
- [ ] Ensure consistent VAT rates from `config.py` are used
- [ ] Fix any missing or incorrect VAT calculations
