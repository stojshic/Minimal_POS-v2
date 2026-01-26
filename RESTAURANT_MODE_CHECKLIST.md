# Restaurant Mode - Implementation Checklist

## Phase 0: Preparation
- [x] Create new branch `restaurant-mode` from `claude`
- [x] Add `store_type` field to `STORE_CONFIG` in `config.py` (default: `"shop"`)

## Phase 1: Database Changes
- [x] Create `restaurant_tables` table (id, name, capacity, position_row, position_col, is_active)
- [x] Create `table_sessions` table (id, table_id, opened_at, closed_at, status, waiter_id, total_amount, payment_type)
- [x] Create `table_orders` table (id, session_id, item_id, item_name, quantity, unit_price, total_price, notes, status)
- [x] Add `TableRepository` to `pos_db_layer.py`
- [x] Add `TableSessionRepository` to `pos_db_layer.py`
- [x] Add `TableOrderRepository` to `pos_db_layer.py`
- [x] Create migration/init for default tables (6 tables in 3x2 grid)

## Phase 2: Business Logic
- [x] Create `TableService` in `pos_business_logic.py`
  - [x] `open_table(table_id, waiter_id)` - start new session
  - [x] `close_table(session_id)` - finalize and close
  - [x] `add_order(session_id, item_id, quantity, notes)`
  - [x] `remove_order(order_id)`
  - [x] `get_table_orders(session_id)`
  - [x] `get_table_total(session_id)`
  - [x] `get_tables_with_status()` - for grid display
  - [x] `generate_table_receipt()` - generate receipt for table
  - [x] `generate_order_ticket()` - generate kitchen/bar ticket
- [x] Wire up UI screens to use database
  - [x] RestaurantScreen - loads tables from DB
  - [x] TableOrderScreen - manages orders via TableService
  - [x] TableManagementScreen - CRUD via TableService

## Phase 3: UI - Restaurant Main Screen
- [x] Create `RestaurantScreen` class (table grid view)
  - [x] Dynamic grid based on table positions
  - [x] Each table button shows: name + current total
  - [x] Color coding: green=free, yellow=occupied
  - [x] Click table → open `TableOrderScreen`
- [x] Modify `POSApp` to check `STORE_CONFIG['store_type']` on startup
- [x] Route to `RestaurantScreen` or existing sales screen based on type

## Phase 4: UI - Table Order Screen
- [x] Create `TableOrderScreen` class
  - [x] Show table name/number at top
  - [x] Left panel: menu items (from inventory, with search)
  - [x] Right panel: current orders for this table
  - [x] Add item to order
  - [x] Remove order item
  - [x] Show running total
  - [x] Button: "Naplati" (print receipt & close table)
  - [x] Button: "Štampaj porudžbinu" (print order ticket for kitchen/bar)
  - [x] Button: "Nazad" (back to table grid, keep table open)
  - [ ] Add notes for kitchen (future)

## Phase 5: Order Tickets (Kitchen/Bar Printing)
- [ ] Add `item_type` to inventory (food/drink/other) for routing
- [ ] Create `OrderTicketPrinter` class in `receipt_printer.py`
  - [ ] Kitchen ticket format (food items only)
  - [ ] Bar ticket format (drink items only)
  - [ ] Include: table number, items, quantities, notes, timestamp
- [ ] `OrderTicketScreen` to display ticket before "printing"

## Phase 6: Table Management (Admin)
- [x] Create `TableManagementScreen` (admin only)
  - [x] Add/edit/delete tables
  - [x] Set table positions (row, col) for grid layout
  - [x] Set capacity (for future reservations)
  - [x] Activate/deactivate tables
- [x] Add F-key binding for table management (F8 - admin only)
- [x] Add F3 for inventory access from restaurant mode

## Phase 7: Reports Integration
- [ ] Extend daily reports for restaurant mode
  - [ ] Sales by table
  - [ ] Sales by waiter
  - [ ] Average table turnover time
  - [ ] Most popular items
- [ ] Table history view (past sessions)

## Bug Fixes & UI Consistency

### BUG-001: Table shows "occupied" (yellow) without orders
- **Issue**: Opening a table creates a session, marking it "occupied" even with zero orders
- **Current behavior**: `occupied = True` if `session_id` exists
- **Expected behavior**: `occupied = True` only if table has orders (total > 0)
- **Files**: `pos_business_logic.py` - `get_tables_with_status()`
- [ ] Fix: Check if `total > 0` instead of just checking `session_id`
- [ ] Consider: Auto-close empty sessions when user leaves TableOrderScreen

### BUG-002: Menu table missing click-to-add functionality
- **Issue**: In shop mode, clicking/Enter on inventory adds item to cart. In restaurant mode, must use button.
- **Shop mode**: `POSApp.on_data_table_row_selected()` handles Enter/click → adds to cart
- **Restaurant mode**: No `on_data_table_row_selected()` in `TableOrderScreen`
- **Files**: `pos_tui.py` - `TableOrderScreen`
- [ ] Add `on_data_table_row_selected()` to `TableOrderScreen` for menu-table

### BUG-003: Menu table missing zebra stripes
- **Issue**: Shop mode inventory table has `zebra_stripes=True`, restaurant menu table doesn't
- **Shop mode**: `DataTable(id="inventory-table", zebra_stripes=True)`
- **Restaurant mode**: `DataTable(id="menu-table")` - no zebra_stripes
- **Files**: `pos_tui.py` - `TableOrderScreen.compose()`
- [ ] Add `zebra_stripes=True` to menu-table

### CODE-001: Consider unifying inventory/menu display component
- **Issue**: Shop and restaurant modes duplicate similar inventory browsing logic
- **Consideration**: Could create a shared `InventoryBrowserWidget` or similar
- **Pros**: Less code duplication, consistent behavior
- **Cons**: Adds complexity, may have subtle behavior differences
- [ ] Evaluate if unification is worth the complexity (decision: later)

## Phase 8: Additional Features (Future)
- [ ] Split bill (divide table total among guests)
- [ ] Transfer items between tables
- [ ] Reservations system
- [ ] Categories/menu sections (Appetizers, Main, Drinks, Desserts)
- [ ] Item modifiers (e.g., "no onions", "extra cheese")
- [ ] Table merge (combine tables for large groups)

---

## Key Considerations

### Order Status Flow
```
ordered → preparing → served → paid
```

### Table Session Flow
```
free → occupied (session open) → bill printed → paid → free
```

### What stays the same
- Inventory management (items are items)
- User authentication
- Payment processing (cash/card/split)
- Receipt generation (final bill)
- Fiscal compliance

### What's different
- No immediate checkout - orders accumulate
- Multiple orders per "transaction" (table session)
- Kitchen/bar communication
- Table state management
