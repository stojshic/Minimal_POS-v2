# Restaurant Mode - Implementation Checklist

## Phase 0: Preparation
- [x] Create new branch `restaurant-mode` from `claude`
- [x] Add `store_type` field to `STORE_CONFIG` in `config.py` (default: `"shop"`)

## Phase 1: Database Changes
- [ ] Create `tables` table (id, name, capacity, position_row, position_col, is_active)
- [ ] Create `table_sessions` table (id, table_id, opened_at, closed_at, status, waiter_id)
- [ ] Create `table_orders` table (id, session_id, item_id, quantity, price, notes, status, created_at)
- [ ] Add `TableRepository` to `pos_db_layer.py`
- [ ] Add `TableSessionRepository` to `pos_db_layer.py`
- [ ] Add `TableOrderRepository` to `pos_db_layer.py`
- [ ] Create migration/init for default tables (6 tables in 3x2 grid)

## Phase 2: Business Logic
- [ ] Create `TableService` in `pos_business_logic.py`
  - [ ] `open_table(table_id, waiter_id)` - start new session
  - [ ] `close_table(session_id)` - finalize and close
  - [ ] `add_order(session_id, item_id, quantity, notes)`
  - [ ] `remove_order(order_id)`
  - [ ] `get_table_orders(session_id)`
  - [ ] `get_table_total(session_id)`
  - [ ] `get_all_tables_status()` - for grid display

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
- [ ] Create `TableManagementScreen` (admin only)
  - [ ] Add/edit/delete tables
  - [ ] Set table positions (row, col) for grid layout
  - [ ] Set capacity (optional, for future reservations)
  - [ ] Activate/deactivate tables
- [ ] Add F-key binding for table management (admin only)

## Phase 7: Reports Integration
- [ ] Extend daily reports for restaurant mode
  - [ ] Sales by table
  - [ ] Sales by waiter
  - [ ] Average table turnover time
  - [ ] Most popular items
- [ ] Table history view (past sessions)

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
