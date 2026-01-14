# Minimal POS (v2)

A small, minimal point-of-sale (POS) system implemented in Python. This project provides:
- A Textual-based TUI (terminal UI) for day-to-day cashier usage.
- A simple CLI demo for scripting or quick testing.
- A clean separation of database layer, business logic, and receipt generation.
- Local SQLite storage (data.db) and simple fiscal receipt emulation with ASCII QR codes.

The app was designed as a minimal, easy-to-extend POS for small stores and as a starting point for building production-grade POS systems.

---

## Features

- Inventory management (add/update quantity and price)
- Sales (single items, multi-item cart, split payments)
- Cash/Card/Split payment handling and basic change calculation
- Invoice import (add invoice and populate inventory)
- Sales, daily and inventory reports
- Receipt generation with VAT breakdown and ASCII QR for terminal display
- User management with roles (`cashier`, `admin`) and default admin account

---

## Contents / Important files

- `pos_tui.py` — Full Textual TUI application (recommended for daily use).
- `pos_cli_demo.py` — Simple CLI demo that exercises the backend.
- `pos_business_logic.py` — Core business logic and services (POSService, reports, user service).
- `pos_db_layer.py` — SQLite database layer and repositories (inventory, sales, payments, receipts, users).
- `receipt_printer.py` — Fiscal receipt generator (ASCII receipt + QR).
- `config.py` — Store configuration (store name, address, PIB, PFR number, cashier).
- `LICENSE` — Repository license file.

---

## Requirements

- Python 3.10+ (3.8+ should work, but some modern features expect 3.10+)
- Suggested Python packages:
  - textual
  - pandas
  - qrcode
  - pillow (dependency for qrcode)
- (Optional) virtualenv or venv for isolated install.

Install dependencies (example):

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.\.venv\Scripts\activate       # Windows

pip install textual pandas qrcode pillow
```

If you prefer, create a `requirements.txt` containing:
```
textual
pandas
qrcode
pillow
```
then run `pip install -r requirements.txt`.

---

## Configuration

Edit `config.py` to set store-specific information:

```python
STORE_CONFIG = {
    "name": "Moja Prodavnica",
    "address": "Dejana Brankova 26, Bela Crkva",
    "pib": "123123123",
    "pfr_number": "PFR-001",
    "cashier": "Kasir 1",
}
```

- `pfr_number` is used in the fiscal receipt header.
- VAT rates are defined in `VAT_RATES` inside `config.py` (default: standard 20%, reduced 10%, zero 0%).

---

## Database / First run

- The application uses a local SQLite database file `data.db` created automatically on first run.
- The DB initialization creates necessary tables and inserts a default admin user.

Default admin credentials (change immediately after first login):
- Username: `admin`
- Password: `admin123`

(These default credentials are created by the DB layer for convenience in development.)

---

## Running

CLI demo
```bash
python pos_cli_demo.py
```

Textual TUI (recommended)
```bash
python pos_tui.py
```

On first run the app will initialize `data.db` and present the login screen (TUI) or start the CLI demo.

---

## Quick TUI usage & keybindings

- Login with admin or a created cashier user.
- Main keybindings (TUI):
  - F1 — Help
  - F2 — Sales (placeholder)
  - F3 — Inventory (admin-only)
  - F4 — Reports
  - F5 — Checkout
  - F8 — User management (admin)
  - F9 — Logout
  - Enter — Add selected inventory item to cart
  - C — Clear cart
  - - (minus) — Remove selected cart item
  - E — Edit cart item quantity

Barcode scan:
- Enter or paste barcode into the search field; if barcode matches an inventory item, it will be added to the cart.

Receipt viewing:
- After a successful checkout, the app shows a receipt viewer that displays the generated fiscal receipt with VAT breakdown and an ASCII QR.

---

## CLI demo highlights

`pos_cli_demo.py` shows:
- Searching inventory
- Selling single items by ID or barcode
- Payment flows (cash, card, split)
- Creating invoices (input items and add to inventory)
- Generating simple reports
- Reprinting receipts

The CLI is a simple demonstration and a helpful debug tool for the backend.

---

## Developer notes

- Business logic is isolated in `pos_business_logic.py` (POSService, ReportService, DailyReportService, UserService), so adding a different UI (web or desktop) is straightforward.
- Repositories in `pos_db_layer.py` encapsulate all persistence; tests can stub these repositories for unit tests.
- Receipt generation (including QR creation) is in `receipt_printer.py`; for production integration with a fiscal printer, replace or extend the `print_receipt` method.
- Receipt counter is stored in memory (`FiscalReceipt.receipt_counter`) — for production it must be persisted (DB or external fiscal device).

---

## Extending & Contributing

Ideas for improvements:
- Persist receipt counter and fiscal device numbering in DB.
- Add REST API or web UI on top of the business logic.
- Integrate with an actual fiscal printer / fiscalization API (region-specific).
- Add tests and CI (unit tests for services and repos).
- Improve authentication (password hashing is SHA-256 — consider PBKDF2/Bcrypt/Argon2).

If you'd like a CONTRIBUTING.md or help adding tests, let me know what style (pytest, unittest) you prefer and I can draft examples.

---

## Troubleshooting

- If `textual` UI fails to start, ensure you installed `textual` and are using a compatible terminal.
- If you get DB permission issues, delete `data.db` and restart (development only — don't do this in production).
- To change default admin password: either log in and use the user management screens, or edit the DB directly (not recommended) or change `default_password` logic in `pos_db_layer.py` before first initialization.

---

## License

This repository includes a `LICENSE` file. Check it for permitted usage and distribution.

---
