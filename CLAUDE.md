# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Minimal POS v2 is a Python-based Point-of-Sale system using Textual TUI framework with SQLite backend. It provides inventory management, sales processing, fiscal receipts (Serbian localization), invoices, reports, and refunds for small retail stores.

## Running the Application

```bash
# Main TUI application
python pos_tui.py

# CLI demo (for testing business logic)
python pos_cli_demo.py
```

Default login: `admin` / `admin123`

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Architecture

The codebase follows a three-layer architecture with strict separation of concerns:

### 1. Database Layer (`pos_db_layer.py`)
Repository pattern implementation with SQLite. Contains:
- `InventoryRepository`, `SalesRepository`, `PaymentRepository`, `ReceiptRepository`
- `UserRepository`, `InvoiceRepository`, `RefundRepository`, `CustomerRepository`, `CustomerInvoiceRepository`

All repositories use context managers for connection handling.

### 2. Business Logic Layer (`pos_business_logic.py`)
Pure business logic with no UI dependencies:
- `POSService`: Sales operations, cart management, barcode lookup
- `ReportService`: Inventory and sales reports
- `DailyReportService`: Daily summaries, VAT breakdown, payment reconciliation
- `UserService`: Authentication, user CRUD
- `RefundService`: Refund processing

Services receive repositories via constructor injection.

### 3. UI Layer (`pos_tui.py`)
Textual-based terminal interface with 30+ Screen classes. Key screens:
- `LoginScreen`, `POSApp` (main menu)
- `InventoryManagementScreen`, `AddItemScreen`, `UpdateItemScreen`
- `SalesScreen`, `PaymentScreen`, `ReceiptViewerScreen`
- `ReportsScreen`, `RefundsScreen`, `UserManagementScreen`
- `InvoiceManagementScreen`, `ImportInvoiceScreen`

### Supporting Modules
- `config.py`: Store configuration (name, address, PIB, VAT rates, system settings)
- `receipt_printer.py`: Fiscal receipt generation with QR codes
- `pdf_utils.py`: PDF generation with Serbian font support

## Key Patterns

- **Dependency Injection**: Services instantiated with repository dependencies
- **Dataclasses**: `PaymentInfo`, `SaleResult`, `InvoiceItem` for structured data
- **Type Hints**: Extensive use of `Optional`, `List`, `Dict`, `Tuple`
- **Textual Screens**: Each major feature is a separate Screen subclass

## Database Schema

SQLite tables: `users`, `inventory`, `sold_items`, `payments`, `receipts`, `invoices`, `refunds`, `customers`

## Branch Structure

- `main`: Stable releases
- `claude`: Active development branch
- `cursor`: Alternative development branch

## Coding Conventions (from CONTRIBUTING.md)

- Follow PEP 8 style guidelines
- Use type hints for function parameters and return values
- Use docstrings for classes and functions
- Commit messages: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `test:`, `chore:`
- Branch naming: `feature/<description>`, `bugfix/<description>`, `hotfix/<description>`
