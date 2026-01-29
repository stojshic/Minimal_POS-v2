"""
Textual TUI for POS System
Beautiful terminal interface
"""
from typing import Optional
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Button, DataTable, Input, Label, Static, Select
from textual.binding import Binding
from textual.screen import Screen 
from time import time
from pos_db_layer import (
    Database, InventoryRepository, SalesRepository,
    InvoiceRepository, UserRepository, RefundRepository,
    CustomerRepository, UnifiedSalesRepository,
    TableRepository, TableSessionRepository, TableOrderRepository,
    CategoryRepository
)
from pos_business_logic import (
        POSService, ReportService, PaymentInfo, DailyReportService,
        UserService, RefundService, TableService, CategoryService
)
from config import STORE_CONFIG, CONFIG
from receipt_printer import OrderTicketPrinter


USER = ""


class LoginScreen(Screen):
    """Login screen - first screen shown"""

    CSS = """
    LoginScreen {
        align: center middle;
        background: $primary;
    }

    #login-container {
        width: 50;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 2;
    }

    #login-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        padding: 1;
    }

    .input-label {
        padding: 1 0;
        color: $text;
    }

    Input {
        margin-bottom: 1;
    }

    #login-button {
        width: 100%;
        margin-top: 1;
    }

    #error-message {
        color: $error;
        text-align: center;
        padding: 1;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("enter", "login", "Login"),
    ]

    def __init__(self, user_service):
        super().__init__()
        self.user_service = user_service

    def compose(self) -> ComposeResult:
        with Vertical(id="login-container"):
            yield Static("🔐 POS SISTEM - PRIJAVA", id="login-title")

            yield Label("Korisničko ime:", classes="input-label")
            yield Input(placeholder="Unesite korisničko ime...", id="username-input")

            yield Label("Lozinka:", classes="input-label")
            yield Input(
                placeholder="Unesite lozinku...",
                password=True,
                id="password-input"
            )

            yield Static("", id="error-message")

            yield Button("Prijavi se \\[Enter]", id="login-button", variant="success")

    def on_mount(self) -> None:
        """Focus username input"""
        self.query_one("#username-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "login-button":
            self.action_login()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in any input field"""
        self.action_login()

    def action_login(self) -> None:
        """Attempt login"""
        username = self.query_one("#username-input", Input).value.strip()
        password = self.query_one("#password-input", Input).value

        success, user, message = self.user_service.login(username, password)

        if success:
            # Login successful - dismiss with user data
            self.dismiss(user)
        else:
            # Show error
            error_msg = self.query_one("#error-message", Static)
            error_msg.update(f"❌ {message}")

            # Clear password field
            self.query_one("#password-input", Input).value = ""
            self.query_one("#password-input", Input).focus()


class RestaurantScreen(Screen):
    """Restaurant mode - table grid view"""

    CSS = """
    RestaurantScreen {
        background: $surface;
    }

    #restaurant-container {
        height: 100%;
        padding: 1;
    }

    #restaurant-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        padding: 1;
        dock: top;
    }

    #tables-grid {
        height: 1fr;
        padding: 1;
        align: center middle;
    }

    .table-row {
        height: auto;
        width: 100%;
        align: center middle;
        padding: 1;
    }

    .table-btn {
        width: 24;
        height: 7;
        margin: 1;
    }

    .table-free {
        background: $success;
    }

    .table-occupied {
        background: $warning;
    }

    .table-placeholder {
        width: 24;
        height: 7;
        margin: 1;
    }
    """

    BINDINGS = [
        Binding("f3", "inventory", "Inventar", show=True),
        Binding("f4", "reports", "Izveštaji", show=True),
        Binding("f6", "table_history", "Istorija", show=True),
        Binding("f7", "sales_history", "Računi", show=True),
        Binding("f8", "manage_tables", "Stolovi", show=True),
        Binding("f9", "back", "Odjava", show=True),
        Binding("f11", "manage_categories", "Kategorije", show=True),
        Binding("r", "refresh", "Osveži"),
    ]

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Control binding visibility based on user role"""
        admin_only = {"manage_tables", "inventory", "manage_categories"}
        if action in admin_only:
            return self.app.is_admin()
        return True

    def action_reports(self) -> None:
        """F4 - Show restaurant reports"""
        self.app.push_screen(
            RestaurantReportScreen(
                self.app.daily_reports,
                self.app.table_service.sessions
            )
        )

    def action_table_history(self) -> None:
        """F6 - Show table session history"""
        self.app.push_screen(
            TableHistoryScreen(self.app.table_service.sessions)
        )

    def action_sales_history(self) -> None:
        """F7 - Show sales history"""
        self.app.action_sales_history()

    def action_manage_categories(self) -> None:
        """F11 - Manage item categories"""
        self.app.push_screen(CategoryManagementScreen(self.app.category_service))

    def __init__(self):
        super().__init__()
        self.tables = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="restaurant-container"):
            yield Static("🍽️  RESTORAN - STOLOVI", id="restaurant-title")
            yield Vertical(id="tables-grid")
        yield Footer()

    def on_mount(self) -> None:
        """Load tables from database"""
        self.load_tables()

    def load_tables(self) -> None:
        """Load tables from database and update display"""
        # Get tables with status from database
        self.tables = self.app.table_service.get_tables_with_status()

        # Convert DB format to display format
        for table in self.tables:
            table['row'] = table.get('position_row', 0)
            table['col'] = table.get('position_col', 0)

        # Clear and rebuild the grid
        grid = self.query_one("#tables-grid", Vertical)
        grid.remove_children()

        if not self.tables:
            return

        # Build a position map: (row, col) -> table
        table_map = {}
        for table in self.tables:
            table_map[(table['row'], table['col'])] = table

        # Find grid dimensions - only consider rows that have tables
        rows_with_tables = sorted(set(t['row'] for t in self.tables))
        max_col = max(t['col'] for t in self.tables)

        # Create rows (only rows that have at least one table)
        for row_num in rows_with_tables:
            row_container = Horizontal(classes="table-row")
            grid.mount(row_container)

            # Render all columns (0 to max_col), with placeholders for empty spots
            for col_num in range(max_col + 1):
                table = table_map.get((row_num, col_num))

                if table:
                    # Render table button
                    btn_class = "table-btn table-occupied" if table.get("occupied") else "table-btn table-free"
                    total_text = f"\n{table.get('total', 0):.0f} RSD" if table.get("total", 0) > 0 else "\nSlobodan"
                    btn = Button(
                        f"{table['name']}{total_text}",
                        id=f"table-{table['id']}",
                        classes=btn_class
                    )
                    row_container.mount(btn)
                else:
                    # Render empty placeholder (same size as table button)
                    placeholder = Static("", classes="table-placeholder")
                    row_container.mount(placeholder)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle table button clicks"""
        btn_id = event.button.id

        if btn_id and btn_id.startswith("table-"):
            table_id = int(btn_id.split("-")[1])
            table = next((t for t in self.tables if t["id"] == table_id), None)
            if table:
                self.app.push_screen(
                    TableOrderScreen(table, self.app.table_service, self.app.category_service),
                    self.handle_table_closed
                )

    def handle_table_closed(self, result: dict) -> None:
        """Handle when table order screen is closed"""
        # Always refresh from database
        self.load_tables()

    def refresh_tables(self) -> None:
        """Refresh table display from database"""
        self.load_tables()

    def action_back(self) -> None:
        """Go back - for restaurant this logs out"""
        self.app.action_logout()

    def action_manage_tables(self) -> None:
        """Open table management (admin only)"""
        if self.app.require_admin("Upravljanje stolovima"):
            self.app.push_screen(
                TableManagementScreen(self.app.table_service),
                self.handle_tables_updated
            )

    def action_inventory(self) -> None:
        """Open inventory management (admin only)"""
        if self.app.require_admin("Inventar"):
            self.app.push_screen(InventoryManagementScreen(self.app.pos, self.app.category_service))

    def action_refresh(self) -> None:
        """Refresh table display"""
        self.load_tables()
        self.notify("Osveženo!", severity="information")

    def handle_tables_updated(self, result) -> None:
        """Handle when tables are updated from management screen"""
        # Always refresh from database
        self.load_tables()


class RestaurantReportScreen(Screen):
    """Restaurant-specific reports screen"""

    CSS = """
    RestaurantReportScreen {
        background: $surface;
    }

    #report-container {
        height: 100%;
        padding: 1;
    }

    #report-header {
        dock: top;
        height: 3;
        padding: 1;
        background: $primary;
        text-align: center;
    }

    #report-content {
        height: 1fr;
        padding: 1;
        overflow-y: auto;
    }

    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }

    .section-title {
        text-style: bold;
        color: $accent;
        padding: 1 0;
    }

    DataTable {
        height: auto;
        max-height: 15;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Nazad"),
        Binding("left", "prev_day", "Prethodni dan"),
        Binding("right", "next_day", "Sledeći dan"),
        Binding("t", "today", "Danas"),
    ]

    def __init__(self, daily_reports, session_repo):
        super().__init__()
        self.daily_reports = daily_reports
        self.session_repo = session_repo
        self.current_date = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="report-container"):
            yield Static("📊 IZVEŠTAJ RESTORANA", id="report-header")

            with Vertical(id="report-content"):
                yield Input(placeholder="Datum (YYYY-MM-DD)", id="date-input")

                yield Label("📋 REZIME", classes="section-title")
                yield Static("", id="summary-content")

                yield Label("🍽️ PRODAJA PO STOLOVIMA", classes="section-title")
                yield DataTable(id="table-sales", zebra_stripes=True)

                yield Label("👤 PRODAJA PO KONOBARIMA", classes="section-title")
                yield DataTable(id="waiter-sales", zebra_stripes=True)

                yield Label("⏱️ PROMET PO SATIMA", classes="section-title")
                yield DataTable(id="hourly-sales", zebra_stripes=True)

            with Horizontal(id="controls"):
                yield Button("◀ Prethodni", id="prev-btn", variant="default")
                yield Button("Danas", id="today-btn", variant="primary")
                yield Button("Sledeći ▶", id="next-btn", variant="default")
                yield Button("Zatvori [Esc]", id="close-btn", variant="error")

        yield Footer()

    def on_mount(self) -> None:
        """Setup tables and load today's report"""
        from datetime import datetime
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.query_one("#date-input", Input).value = self.current_date

        # Setup data tables
        table_sales = self.query_one("#table-sales", DataTable)
        table_sales.add_columns("Sto", "Sesija", "Promet", "Prosek (min)")

        waiter_sales = self.query_one("#waiter-sales", DataTable)
        waiter_sales.add_columns("Konobar", "Sesija", "Promet", "Prosečan račun")

        hourly_sales = self.query_one("#hourly-sales", DataTable)
        hourly_sales.add_columns("Sat", "Broj", "Promet")

        self.load_report(self.current_date)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle date input"""
        if event.input.id == "date-input":
            self.current_date = event.value.strip()
            self.load_report(self.current_date)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "prev-btn":
            self.action_prev_day()
        elif event.button.id == "next-btn":
            self.action_next_day()
        elif event.button.id == "today-btn":
            self.action_today()
        elif event.button.id == "close-btn":
            self.action_close()

    def action_prev_day(self) -> None:
        """Go to previous day"""
        from datetime import datetime, timedelta
        current = datetime.strptime(self.current_date, "%Y-%m-%d")
        self.current_date = (current - timedelta(days=1)).strftime("%Y-%m-%d")
        self.query_one("#date-input", Input).value = self.current_date
        self.load_report(self.current_date)

    def action_next_day(self) -> None:
        """Go to next day"""
        from datetime import datetime, timedelta
        current = datetime.strptime(self.current_date, "%Y-%m-%d")
        self.current_date = (current + timedelta(days=1)).strftime("%Y-%m-%d")
        self.query_one("#date-input", Input).value = self.current_date
        self.load_report(self.current_date)

    def action_today(self) -> None:
        """Go to today"""
        from datetime import datetime
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.query_one("#date-input", Input).value = self.current_date
        self.load_report(self.current_date)

    def action_close(self) -> None:
        """Close screen"""
        self.dismiss()

    def load_report(self, date: str) -> None:
        """Load and display restaurant report"""
        report = self.daily_reports.generate_restaurant_report(date, self.session_repo)

        # Update summary
        summary = self.query_one("#summary-content", Static)
        if not report.get('has_data'):
            summary.update(f"\n  {report.get('message', 'Nema podataka')}\n")
            self._clear_tables()
            return

        s = report['summary']
        summary_text = f"""
  Ukupan promet:     {s['total_revenue']:>12.2f} RSD
  Broj sesija:       {s['total_sessions']:>12}
  Prosečan račun:    {s['avg_ticket']:>12.2f} RSD
  Prosečno trajanje: {s['avg_duration_minutes']:>12.1f} min
  Min trajanje:      {s['min_duration_minutes']:>12.1f} min
  Max trajanje:      {s['max_duration_minutes']:>12.1f} min
"""
        summary.update(summary_text)

        # Update table sales
        table_sales = self.query_one("#table-sales", DataTable)
        table_sales.clear()
        for row in report.get('sales_by_table', []):
            if row['session_count'] > 0:
                table_sales.add_row(
                    row['table_name'],
                    str(row['session_count']),
                    f"{row['total_revenue']:.2f}",
                    f"{row['avg_duration_minutes'] or 0:.1f}"
                )

        # Update waiter sales
        waiter_sales = self.query_one("#waiter-sales", DataTable)
        waiter_sales.clear()
        for row in report.get('sales_by_waiter', []):
            waiter_sales.add_row(
                row['waiter_name'] or 'Nepoznat',
                str(row['session_count']),
                f"{row['total_revenue']:.2f}",
                f"{row['avg_ticket'] or 0:.2f}"
            )

        # Update hourly sales
        hourly_sales = self.query_one("#hourly-sales", DataTable)
        hourly_sales.clear()
        for hour, data in report.get('hourly_sessions', []):
            hourly_sales.add_row(
                f"{hour}:00",
                str(data['count']),
                f"{data['revenue']:.2f}"
            )

    def _clear_tables(self) -> None:
        """Clear all data tables"""
        self.query_one("#table-sales", DataTable).clear()
        self.query_one("#waiter-sales", DataTable).clear()
        self.query_one("#hourly-sales", DataTable).clear()


class TableHistoryScreen(Screen):
    """Screen for viewing past table sessions"""

    CSS = """
    TableHistoryScreen {
        background: $surface;
    }

    #history-container {
        height: 100%;
        padding: 1;
    }

    #history-header {
        dock: top;
        height: 3;
        padding: 1;
        background: $primary;
        text-align: center;
    }

    #session-details {
        height: auto;
        max-height: 10;
        padding: 1;
        background: $panel;
        margin-bottom: 1;
    }

    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }

    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Nazad"),
        Binding("enter", "view_details", "Detalji"),
    ]

    def __init__(self, session_repo, table_id: int = None):
        super().__init__()
        self.session_repo = session_repo
        self.table_id = table_id  # Optional filter by table
        self.sessions = []

    def compose(self) -> ComposeResult:
        title = "📜 ISTORIJA SESIJA"
        if self.table_id:
            title += f" (Sto #{self.table_id})"

        yield Header()
        with Vertical(id="history-container"):
            yield Static(title, id="history-header")
            yield Static("Izaberite sesiju za detalje", id="session-details")
            yield DataTable(id="sessions-table", zebra_stripes=True)
            with Horizontal(id="controls"):
                yield Button("Detalji [Enter]", id="details-btn", variant="primary")
                yield Button("Zatvori [Esc]", id="close-btn", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        """Setup table and load data"""
        table = self.query_one("#sessions-table", DataTable)
        table.add_columns("ID", "Sto", "Konobar", "Početak", "Kraj", "Trajanje", "Iznos", "Plaćanje")
        table.cursor_type = "row"
        self.load_sessions()

    def load_sessions(self) -> None:
        """Load session history from database"""
        self.sessions = self.session_repo.get_session_history(limit=100, table_id=self.table_id)

        table = self.query_one("#sessions-table", DataTable)
        table.clear()

        for session in self.sessions:
            # Calculate duration
            duration = ""
            if session.get('opened_at') and session.get('closed_at'):
                try:
                    from datetime import datetime
                    # Handle ISO format with T separator
                    opened = session['opened_at'].replace('T', ' ')
                    closed = session['closed_at'].replace('T', ' ')
                    start = datetime.strptime(opened[:19], "%Y-%m-%d %H:%M:%S")
                    end = datetime.strptime(closed[:19], "%Y-%m-%d %H:%M:%S")
                    mins = int((end - start).total_seconds() / 60)
                    duration = f"{mins} min"
                except:
                    duration = "-"

            # Format timestamps for display
            opened_display = session.get('opened_at', '')[:16].replace('T', ' ')
            closed_display = session.get('closed_at', '')[:16].replace('T', ' ') if session.get('closed_at') else '-'

            table.add_row(
                str(session['id']),
                session.get('table_name', '-'),
                session.get('waiter_name', '-') or '-',
                opened_display,
                closed_display,
                duration,
                f"{session.get('total_amount', 0) or 0:.2f}",
                session.get('payment_type', '-') or '-'
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "details-btn":
            self.action_view_details()
        elif event.button.id == "close-btn":
            self.action_close()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Show session details when row selected"""
        self.show_session_details(event.cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update details when cursor moves"""
        if event.cursor_row is not None and event.cursor_row < len(self.sessions):
            self.show_session_details(event.cursor_row)

    def show_session_details(self, row_index: int) -> None:
        """Show details for selected session"""
        if row_index >= len(self.sessions):
            return

        session = self.sessions[row_index]
        details = self.query_one("#session-details", Static)

        detail_text = f"""
  Sesija #{session['id']} - {session.get('table_name', '-')}
  Konobar: {session.get('waiter_name', '-') or 'Nepoznat'}
  Status: {session.get('status', '-')}
  Ukupno: {session.get('total_amount', 0) or 0:.2f} RSD
  Plaćanje: {session.get('payment_type', '-') or '-'}
"""
        details.update(detail_text)

    def action_view_details(self) -> None:
        """View full details of selected session"""
        table = self.query_one("#sessions-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.sessions):
            self.show_session_details(table.cursor_row)

    def action_close(self) -> None:
        """Close screen"""
        self.dismiss()


class TableManagementScreen(Screen):
    """Admin screen for managing restaurant tables"""

    CSS = """
    TableManagementScreen {
        background: $surface;
    }

    #table-mgmt-container {
        height: 100%;
        padding: 1;
    }

    #table-mgmt-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        padding: 1;
        dock: top;
    }

    #tables-list {
        height: 1fr;
        border: solid $primary;
        margin: 1 0;
    }

    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Zatvori"),
        Binding("n", "new_table", "Novi sto"),
        Binding("e", "edit_table", "Izmeni"),
        Binding("d", "delete_table", "Obriši"),
        Binding("a", "toggle_active", "Aktiviraj/Deaktiviraj"),
    ]

    def __init__(self, table_service):
        super().__init__()
        self.table_service = table_service
        self.tables = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="table-mgmt-container"):
            yield Static("🪑 UPRAVLJANJE STOLOVIMA", id="table-mgmt-title")
            yield DataTable(id="tables-list")

            with Horizontal(id="controls"):
                yield Button("Novi sto [N]", id="new-btn", variant="success")
                yield Button("Izmeni [E]", id="edit-btn", variant="primary")
                yield Button("Aktiviraj/Deakt. [A]", id="toggle-btn", variant="warning")
                yield Button("Obriši [D]", id="delete-btn", variant="error")
                yield Button("Zatvori [Esc]", id="close-btn", variant="default")

        yield Footer()

    def on_mount(self) -> None:
        """Setup table"""
        table = self.query_one("#tables-list", DataTable)
        table.add_columns("ID", "Naziv", "Red", "Kolona", "Kapacitet", "Aktivan")
        table.cursor_type = "row"
        self.load_tables()

    def load_tables(self) -> None:
        """Load tables from database"""
        table = self.query_one("#tables-list", DataTable)
        table.clear()

        # Get tables from database
        self.tables = self.table_service.get_all_tables()

        # Sort by row, then column
        sorted_tables = sorted(self.tables, key=lambda t: (t.get("position_row", 0), t.get("position_col", 0)))

        for t in sorted_tables:
            table.add_row(
                str(t["id"]),
                t["name"],
                str(t.get("position_row", 0)),
                str(t.get("position_col", 0)),
                str(t.get("capacity", 4)),
                "DA" if t.get("is_active", True) else "NE"
            )

    def get_selected_table(self) -> Optional[dict]:
        """Get currently selected table"""
        table = self.query_one("#tables-list", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            table_id = int(row[0])
            return next((t for t in self.tables if t["id"] == table_id), None)
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        btn_id = event.button.id

        if btn_id == "new-btn":
            self.action_new_table()
        elif btn_id == "edit-btn":
            self.action_edit_table()
        elif btn_id == "toggle-btn":
            self.action_toggle_active()
        elif btn_id == "delete-btn":
            self.action_delete_table()
        elif btn_id == "close-btn":
            self.action_close()

    def action_new_table(self) -> None:
        """Add new table"""
        # Find next table number for default name
        max_num = len(self.tables) + 1
        new_table = {
            "id": 0,  # Will be assigned by database
            "name": f"Sto {max_num}",
            "position_row": 0,
            "position_col": 0,
            "capacity": 4,
            "is_active": True
        }
        self.app.push_screen(
            AddEditTableScreen(new_table, self.table_service, is_new=True),
            self.handle_table_saved
        )

    def action_edit_table(self) -> None:
        """Edit selected table"""
        table = self.get_selected_table()
        if table:
            self.app.push_screen(
                AddEditTableScreen(table.copy(), self.table_service, is_new=False),
                self.handle_table_saved
            )
        else:
            self.notify("Izaberite sto!", severity="warning")

    def handle_table_saved(self, result: dict) -> None:
        """Handle saved table from AddEditTableScreen"""
        if result and result.get("saved"):
            self.load_tables()
            self.notify("Sto sačuvan!", severity="success")

    def action_toggle_active(self) -> None:
        """Toggle table active status"""
        table = self.get_selected_table()
        if table:
            success, msg = self.table_service.toggle_table_active(table["id"])
            if success:
                self.load_tables()
                self.notify(msg, severity="success")
            else:
                self.notify(msg, severity="error")
        else:
            self.notify("Izaberite sto!", severity="warning")

    def action_delete_table(self) -> None:
        """Delete selected table"""
        table = self.get_selected_table()
        if table:
            success, msg = self.table_service.delete_table(table["id"])
            if success:
                self.load_tables()
                self.notify(msg, severity="warning")
            else:
                self.notify(msg, severity="error")
        else:
            self.notify("Izaberite sto!", severity="warning")

    def action_close(self) -> None:
        """Close screen"""
        self.dismiss({"updated": True})


class AddEditTableScreen(Screen):
    """Screen for adding or editing a table"""

    CSS = """
    AddEditTableScreen {
        align: center middle;
        background: $surface-darken-1;
    }

    #form-container {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 2;
    }

    #form-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        padding: 1;
    }

    .form-label {
        padding: 1 0 0 0;
        color: $text;
    }

    Input {
        margin-bottom: 1;
    }

    #form-row {
        height: auto;
        width: 100%;
    }

    .half-input {
        width: 1fr;
        margin: 0 1;
    }

    #buttons {
        height: auto;
        layout: horizontal;
        padding: 1 0;
    }

    #buttons Button {
        width: 1fr;
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Odustani"),
    ]

    def __init__(self, table: dict, table_service, is_new: bool = False):
        super().__init__()
        self.table = table
        self.table_service = table_service
        self.is_new = is_new

    def compose(self) -> ComposeResult:
        title = "NOVI STO" if self.is_new else f"IZMENI - {self.table['name']}"

        with Vertical(id="form-container"):
            yield Static(f"🪑 {title}", id="form-title")

            yield Label("Naziv stola:", classes="form-label")
            yield Input(value=self.table.get("name", ""), id="name-input")

            with Horizontal(id="form-row"):
                with Vertical(classes="half-input"):
                    yield Label("Red (0-9):", classes="form-label")
                    yield Input(value=str(self.table.get("position_row", 0)), id="row-input", type="integer")

                with Vertical(classes="half-input"):
                    yield Label("Kolona (0-9):", classes="form-label")
                    yield Input(value=str(self.table.get("position_col", 0)), id="col-input", type="integer")

            yield Label("Kapacitet (broj mesta):", classes="form-label")
            yield Input(value=str(self.table.get("capacity", 4)), id="capacity-input", type="integer")

            with Horizontal(id="buttons"):
                yield Button("Sačuvaj", id="save-btn", variant="success")
                yield Button("Odustani", id="cancel-btn", variant="default")

    def on_mount(self) -> None:
        """Focus first input"""
        self.query_one("#name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_save(self) -> None:
        """Save table to database"""
        name = self.query_one("#name-input", Input).value.strip()
        row_str = self.query_one("#row-input", Input).value.strip()
        col_str = self.query_one("#col-input", Input).value.strip()
        capacity_str = self.query_one("#capacity-input", Input).value.strip()

        # Validate
        if not name:
            self.notify("Unesite naziv stola!", severity="error")
            return

        try:
            row = int(row_str) if row_str else 0
            col = int(col_str) if col_str else 0
            capacity = int(capacity_str) if capacity_str else 4

            if row < 0 or row > 9 or col < 0 or col > 9:
                self.notify("Red i kolona moraju biti 0-9!", severity="error")
                return

            if capacity < 1:
                self.notify("Kapacitet mora biti bar 1!", severity="error")
                return

        except ValueError:
            self.notify("Unesite ispravne brojeve!", severity="error")
            return

        # Save to database
        if self.is_new:
            success, msg, table_id = self.table_service.create_table(name, row, col, capacity)
        else:
            success, msg = self.table_service.update_table(self.table["id"], name, row, col, capacity)

        if success:
            self.dismiss({"saved": True})
        else:
            self.notify(msg, severity="error")

    def action_cancel(self) -> None:
        """Cancel without saving"""
        self.dismiss({"saved": False})


class TableOrderScreen(Screen):
    """Screen for managing orders at a single table"""

    CSS = """
    TableOrderScreen {
        background: $surface;
    }

    #table-order-container {
        height: 100%;
        padding: 1;
    }

    #table-header {
        dock: top;
        height: auto;
        padding: 1;
        background: $primary;
        text-align: center;
    }

    #main-content {
        height: 1fr;
    }

    #menu-panel {
        width: 3fr;
        border: solid $primary;
        padding: 1;
    }

    #order-panel {
        width: 2fr;
        border: solid $accent;
        padding: 1;
    }

    #order-total {
        padding: 1;
        text-style: bold;
        background: $success;
        color: $text;
        text-align: center;
    }

    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }

    .panel-label {
        padding: 1 0;
        text-style: bold;
        color: $accent;
    }

    DataTable {
        height: 1fr;
    }

    #search-input {
        margin-bottom: 1;
    }

    #category-tabs {
        height: auto;
        margin-bottom: 1;
        overflow-x: auto;
    }

    .category-tab {
        min-width: 10;
        margin-right: 1;
    }

    .category-tab-active {
        background: $accent;
    }
    """

    BINDINGS = [
        Binding("escape", "back", "Nazad"),
        Binding("enter", "add_item", "Dodaj"),
        Binding("-", "remove_item", "Ukloni"),
        Binding("q", "change_quantity", "Količina"),
        Binding("c", "clear_orders", "Očisti"),
        Binding("f4", "reports", "Izveštaji"),
        Binding("f5", "print_bill", "Račun"),
        Binding("f7", "sales_history", "Prethodni"),
        Binding("p", "print_order", "Štampaj"),
        Binding("r", "reprint_order", "Ponovi"),
    ]

    def __init__(self, table: dict, table_service, category_service=None):
        super().__init__()
        self.table = table
        self.table_service = table_service
        self.category_service = category_service
        self.session_id = None
        self.orders = []
        self.selected_category_id = None  # None means "all categories"
        self.categories = []
        # Note: last_printed_ticket is now stored in session (database) for persistence

    def compose(self) -> ComposeResult:
        # Load categories for tabs
        if self.category_service:
            self.categories = self.category_service.get_all_categories()

        yield Header()
        with Vertical(id="table-order-container"):
            yield Static(f"🍽️  {self.table['name'].upper()}", id="table-header")

            with Horizontal(id="main-content"):
                # Left panel - Menu items
                with Vertical(id="menu-panel"):
                    yield Label("📋 MENI", classes="panel-label")

                    # Category filter tabs
                    with Horizontal(id="category-tabs"):
                        yield Button("Sve", id="cat-all", variant="primary", classes="category-tab category-tab-active")
                        for cat in self.categories:
                            label = f"{cat['icon']} {cat['name']}" if cat['icon'] else cat['name']
                            yield Button(label, id=f"cat-{cat['id']}", variant="default", classes="category-tab")

                    yield Input(placeholder="Pretraga artikala...", id="search-input")
                    yield DataTable(id="menu-table", zebra_stripes=True)

                # Right panel - Current orders
                with Vertical(id="order-panel"):
                    yield Label("📝 PORUDŽBINA", classes="panel-label")
                    yield DataTable(id="order-table", zebra_stripes=True)
                    yield Static(f"UKUPNO: {self.calculate_total():.2f} RSD", id="order-total")

            with Horizontal(id="controls"):
                yield Button("Dodaj [Enter]", id="add-btn", variant="primary")
                yield Button("Ukloni [-]", id="remove-btn", variant="error")
                yield Button("Štampaj [P]", id="print-order-btn", variant="default")
                yield Button("Naplati [F5]", id="print-bill-btn", variant="success")
                yield Button("Nazad [Esc]", id="back-btn", variant="default")

        yield Footer()

    def on_mount(self) -> None:
        """Setup tables and open/get session"""
        # Get or create session for this table
        waiter_id = self.app.current_user.get('id') if self.app.current_user else None
        success, msg, session_id = self.table_service.open_table(self.table['id'], waiter_id)
        self.session_id = session_id

        # Restore last selected category from app
        if hasattr(self.app, 'last_category_id') and self.app.last_category_id is not None:
            self.selected_category_id = self.app.last_category_id

        # Setup menu table
        menu_table = self.query_one("#menu-table", DataTable)
        menu_table.add_columns("ID", "Artikal", "Cena")
        menu_table.cursor_type = "row"
        self.load_menu()

        # Update category tabs to reflect restored selection
        self.update_category_tabs()

        # Setup order table
        order_table = self.query_one("#order-table", DataTable)
        order_table.add_columns("ID", "Artikal", "Kol.", "Cena", "Ukupno")
        order_table.cursor_type = "row"
        self.load_orders()

        # Focus search input for quick item entry
        self.query_one("#search-input", Input).focus()

    def load_menu(self, search: str = "") -> None:
        """Load menu items from inventory, optionally filtered by category"""
        menu_table = self.query_one("#menu-table", DataTable)
        menu_table.clear()

        # Use category filtering if category_service is available
        if self.category_service and self.selected_category_id is not None:
            items = self.category_service.get_items_by_category(
                self.selected_category_id, search
            )
        else:
            # No category filter - show all items (filtered by search if provided)
            items = self.table_service.inventory.get_by_category(None, search)

        for item in items:
            menu_table.add_row(
                str(item["id"]),
                item["item"],
                f"{item['price']:.2f}"
            )

    def update_category_tabs(self) -> None:
        """Update category tab button appearances"""
        # Reset all tabs to default
        all_btn = self.query_one("#cat-all", Button)
        all_btn.variant = "primary" if self.selected_category_id is None else "default"
        all_btn.remove_class("category-tab-active")
        if self.selected_category_id is None:
            all_btn.add_class("category-tab-active")

        for cat in self.categories:
            try:
                btn = self.query_one(f"#cat-{cat['id']}", Button)
                is_selected = self.selected_category_id == cat['id']
                btn.variant = "primary" if is_selected else "default"
                btn.remove_class("category-tab-active")
                if is_selected:
                    btn.add_class("category-tab-active")
            except Exception:
                pass  # Button might not exist

    def load_orders(self) -> None:
        """Load current orders from database"""
        order_table = self.query_one("#order-table", DataTable)
        order_table.clear()

        if self.session_id:
            self.orders = self.table_service.get_table_orders(self.session_id)

        for order in self.orders:
            order_table.add_row(
                str(order["id"]),
                order["item_name"],
                str(order["quantity"]),
                f"{order['unit_price']:.2f}",
                f"{order['total_price']:.2f}"
            )

        self.update_total()

    def calculate_total(self) -> float:
        """Calculate total for all orders"""
        if self.session_id:
            return self.table_service.get_table_total(self.session_id)
        return 0.0

    def update_total(self) -> None:
        """Update total display"""
        total = self.calculate_total()
        self.query_one("#order-total", Static).update(f"UKUPNO: {total:.2f} RSD")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input"""
        if event.input.id == "search-input":
            self.load_menu(event.value)

    def handle_category_click(self, category_id: Optional[int]) -> None:
        """Handle category tab selection"""
        self.selected_category_id = category_id
        self.update_category_tabs()
        # Reload menu with current search term
        search_input = self.query_one("#search-input", Input)
        self.load_menu(search_input.value)

        # Save to app for persistence across table switches
        if hasattr(self.app, 'last_category_id'):
            self.app.last_category_id = category_id

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter/double-click on menu table to add item"""
        if event.data_table.id == "menu-table":
            self.action_add_item()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        btn_id = event.button.id

        # Handle category tab clicks
        if btn_id == "cat-all":
            self.handle_category_click(None)
            return
        elif btn_id.startswith("cat-"):
            try:
                category_id = int(btn_id.replace("cat-", ""))
                self.handle_category_click(category_id)
                return
            except ValueError:
                pass

        if btn_id == "add-btn":
            self.action_add_item()
        elif btn_id == "remove-btn":
            self.action_remove_item()
        elif btn_id == "print-order-btn":
            self.action_print_order()
        elif btn_id == "print-bill-btn":
            self.action_print_bill()
        elif btn_id == "back-btn":
            self.action_back()

    def action_add_item(self) -> None:
        """Add selected menu item to order"""
        if not self.session_id:
            self.notify("Greška: sesija nije otvorena!", severity="error")
            return

        menu_table = self.query_one("#menu-table", DataTable)
        if menu_table.cursor_row is not None:
            row = menu_table.get_row_at(menu_table.cursor_row)
            item_id = int(row[0])
            item_name = row[1]

            # Add to database
            success, msg = self.table_service.add_order(self.session_id, item_id)

            if success:
                self.load_orders()
                self.notify(msg, severity="information")
            else:
                self.notify(msg, severity="error")

    def action_remove_item(self) -> None:
        """Remove selected item from order"""
        order_table = self.query_one("#order-table", DataTable)
        if order_table.cursor_row is not None and self.orders:
            if order_table.cursor_row < len(self.orders):
                order = self.orders[order_table.cursor_row]
                order_id = order['id']

                # Remove from database
                success, msg = self.table_service.remove_order(order_id)

                if success:
                    self.load_orders()
                    self.notify(msg, severity="warning")
                else:
                    self.notify(msg, severity="error")

    def action_change_quantity(self) -> None:
        """Change quantity of selected order item"""
        order_table = self.query_one("#order-table", DataTable)
        if order_table.cursor_row is not None and self.orders:
            if order_table.cursor_row < len(self.orders):
                order = self.orders[order_table.cursor_row]

                # Get item info for the screen
                item_info = {
                    'item': order['item_name'],
                    'quantity': order['quantity'],
                    'price': order['unit_price']
                }

                def handle_quantity(new_qty):
                    if new_qty is not None and new_qty > 0:
                        success, msg = self.table_service.update_order_quantity(
                            order['id'], new_qty
                        )
                        if success:
                            self.load_orders()
                            self.notify(msg, severity="information")
                        else:
                            self.notify(msg, severity="error")
                    elif new_qty == 0:
                        # Remove item if quantity is 0
                        self.table_service.remove_order(order['id'])
                        self.load_orders()
                        self.notify(f"Uklonjeno: {order['item_name']}", severity="warning")

                self.app.push_screen(QuantityInputScreen(item_info), handle_quantity)
        else:
            self.notify("Izaberite stavku za izmenu!", severity="warning")

    def action_clear_orders(self) -> None:
        """Clear all orders from this table"""
        if not self.orders:
            self.notify("Nema porudžbina za brisanje!", severity="warning")
            return

        def confirm_clear(confirmed):
            if confirmed:
                # Remove all orders
                for order in self.orders:
                    self.table_service.remove_order(order['id'])
                self.load_orders()
                self.notify("Sve porudžbine obrisane!", severity="warning")

        self.app.push_screen(
            ConfirmDialog(
                "Da li ste sigurni da želite obrisati sve porudžbine?",
                "Brisanje porudžbina"
            ),
            confirm_clear
        )

    def action_print_order(self) -> None:
        """Print order ticket for kitchen/bar"""
        # Get new orders (status='ordered')
        new_orders = [o for o in self.orders if o.get('status') == 'ordered']
        if not new_orders:
            # No new orders - hint about re-print if there's a previous ticket
            last_ticket = self.table_service.get_last_ticket(self.session_id)
            if last_ticket:
                self.notify("Nema novih porudžbina. Pritisnite R za ponovnu štampu.", severity="warning")
            else:
                self.notify("Nema porudžbina za štampu!", severity="warning")
            return

        # Get waiter name
        waiter_name = self.app.current_user.get('full_name') if self.app.current_user else None

        # Generate tickets using OrderTicketPrinter
        ticket_printer = OrderTicketPrinter()
        ticket_text = ticket_printer.generate_combined_ticket(
            table_name=self.table['name'],
            orders=new_orders,
            waiter_name=waiter_name
        )

        if not ticket_text:
            self.notify("Nema stavki za štampu!", severity="warning")
            return

        # Store ticket in session for re-printing (persists across screen exits)
        self.table_service.save_last_ticket(self.session_id, ticket_text)

        # Show ticket screen
        def handle_ticket_result(result):
            if result and result.get('printed'):
                # Mark orders as 'preparing'
                for order in new_orders:
                    self.table_service.update_order_status(order['id'], 'preparing')
                self.load_orders()
                # Note: OrderTicketScreen already shows "Porudžbina poslata na štampanje!"

        self.app.push_screen(OrderTicketScreen(ticket_text), handle_ticket_result)

    def action_reprint_order(self) -> None:
        """Re-print the last order ticket"""
        # Get ticket from session (persists across screen exits)
        last_ticket = self.table_service.get_last_ticket(self.session_id)
        if not last_ticket:
            self.notify("Nema prethodne porudžbine za štampu!", severity="warning")
            return

        # Show ticket screen for re-print (OrderTicketScreen handles the notification)
        self.app.push_screen(OrderTicketScreen(last_ticket))

    def action_print_bill(self) -> None:
        """Print bill and close table - opens payment screen"""
        if not self.orders:
            self.notify("Nema porudžbina za naplatu!", severity="warning")
            return

        # Calculate total
        total = self.calculate_total()

        # Open payment screen
        self.app.push_screen(
            PaymentScreen(total, self.app.customer_repo),
            self.handle_payment_result
        )

    def handle_payment_result(self, payment_info: PaymentInfo) -> None:
        """Handle completed payment from PaymentScreen"""
        if not payment_info:
            self.notify("Plaćanje otkazano", severity="warning")
            return

        # Store payment info for after_payment_complete
        self.last_payment_info = payment_info

        # Convert orders to sale items format
        sale_items = []
        for order in self.orders:
            sale_items.append({
                'id': order['item_id'],
                'quantity': order['quantity']
            })

        # Process the sale using POSService
        try:
            result = self.app.pos.sell_items(
                items=sale_items,
                payment_info=payment_info,
                allow_oversell=CONFIG["allow_oversell"]
            )

            if not result.success:
                self.notify(f"Greška: {result.message}", severity="error")
                return

            # Get the receipt
            last_sale_id = result.sale_id
            if last_sale_id:
                sale_record = self.app.unified_sales.get_by_id(last_sale_id)

                if sale_record and sale_record.get('receipt_text'):
                    # Prepare sale_data for receipt viewer
                    from datetime import datetime
                    sale_data = {
                        'items': result.sale_items,
                        'customer_info': result.customer_info,
                        'payment_info': {
                            'payment_type': payment_info.payment_type,
                            'cash_amount': payment_info.cash_amount,
                            'card_amount': payment_info.card_amount,
                            'amount_tendered': payment_info.amount_tendered,
                            'change_given': payment_info.change_given,
                        },
                        'timestamp': datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                    }

                    # Add table info to receipt
                    table_header = f"\n{'=' * 40}\n"
                    table_header += f"{self.table['name']}".center(40) + "\n"
                    table_header += f"{'=' * 40}\n"
                    receipt_text = table_header + sale_record['receipt_text']

                    # Show receipt viewer
                    self.app.push_screen(
                        ReceiptViewerScreen(receipt_text, last_sale_id, sale_data),
                        self.after_payment_complete
                    )
                else:
                    self.after_payment_complete()
            else:
                self.after_payment_complete()

        except Exception as e:
            self.notify(f"Greška pri prodaji: {str(e)}", severity="error")

    def after_payment_complete(self, result=None) -> None:
        """Called after receipt is shown - close the table"""
        # Get payment type from stored payment info
        payment_type = getattr(self, 'last_payment_info', None)
        payment_type = payment_type.payment_type if payment_type else 'cash'

        # Close session
        success, msg = self.table_service.close_table(self.session_id, payment_type)

        if success:
            self.notify(f"✅ {self.table['name']} zatvoreno!", severity="success")
            self.dismiss({"closed": True})
        else:
            self.notify(msg, severity="error")

    def action_reports(self) -> None:
        """F4 - Show restaurant reports"""
        self.app.push_screen(
            RestaurantReportScreen(
                self.app.daily_reports,
                self.table_service.sessions
            )
        )

    def action_sales_history(self) -> None:
        """F7 - Show sales history"""
        self.app.action_sales_history()

    def action_back(self) -> None:
        """Go back to table grid"""
        # If no orders, close the empty session to keep table "free"
        if not self.orders and self.session_id:
            self.table_service.close_table(self.session_id)
        self.dismiss({"closed": False})


class OrderTicketScreen(Screen):
    """Screen for displaying and printing order tickets for kitchen/bar"""

    CSS = """
    OrderTicketScreen {
        align: center middle;
    }

    #ticket-dialog {
        width: 50;
        height: auto;
        max-height: 90%;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }

    #ticket-header {
        text-align: center;
        padding: 1;
        text-style: bold;
        color: $warning;
    }

    #ticket-content {
        height: auto;
        max-height: 60%;
        overflow-y: auto;
        padding: 1;
        background: $panel;
        border: solid $primary;
    }

    #ticket-content Static {
        width: 100%;
    }

    #ticket-buttons {
        layout: horizontal;
        height: auto;
        padding: 1;
        align: center middle;
    }

    #ticket-buttons Button {
        margin: 0 1;
    }

    .ticket-type-label {
        text-align: center;
        padding: 0 0 1 0;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Zatvori"),
        Binding("p", "print", "Štampaj"),
    ]

    def __init__(self, ticket_text: str, ticket_type: str = "all"):
        """
        Initialize ticket screen

        Args:
            ticket_text: The formatted ticket text to display
            ticket_type: Type of ticket ("kitchen", "bar", "all")
        """
        super().__init__()
        self.ticket_text = ticket_text
        self.ticket_type = ticket_type

    def compose(self) -> ComposeResult:
        type_labels = {
            "kitchen": "KUHINJA",
            "bar": "ŠANK",
            "all": "SVE PORUDŽBINE"
        }
        type_label = type_labels.get(self.ticket_type, "PORUDŽBINA")

        with Vertical(id="ticket-dialog"):
            yield Static(f"PORUDŽBINA ZA: {type_label}", id="ticket-header")
            with Vertical(id="ticket-content"):
                yield Static(self.ticket_text, markup=False)
            with Horizontal(id="ticket-buttons"):
                yield Button("Štampaj [P]", id="print-btn", variant="success")
                yield Button("Zatvori [ESC]", id="close-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "print-btn":
            self.action_print()
        elif event.button.id == "close-btn":
            self.action_close()

    def action_print(self) -> None:
        """Print the ticket"""
        # In production, this would send to actual printer
        # For now, we just show a confirmation
        self.notify("Porudžbina poslata na štampanje!", severity="success")
        self.dismiss({"printed": True})

    def action_close(self) -> None:
        """Close without printing"""
        self.dismiss({"printed": False})


class CustomerManagementScreen(Screen):
    """Screen for managing customers"""
    
    CSS = """
    CustomerManagementScreen {
        background: $surface;
    }
    
    #customer-container {
        height: 100%;
        padding: 1;
    }
    
    #search-section {
        height: auto;
        margin-bottom: 1;
    }
    
    #customers-table {
        height: 1fr;
        border: solid $primary;
        margin-bottom: 1;
    }
    
    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        background: $panel;
        padding: 1;
    }
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f2", "close", "Main", show=True),
        Binding("n", "new_customer", "New Customer"),
        Binding("e", "edit_customer", "Edit Customer"),
        Binding("d", "delete_customer", "Delete"),
        Binding("i", "create_invoice", "Create Invoice"),
    ]

    def __init__(self, customer_repo):
        super().__init__()
        self.customer_repo = customer_repo

    def compose(self) -> ComposeResult:
        with Vertical(id="customer-container"):
            yield Label("👥 UPRAVLJANJE KUPCIMA", classes="label")

            with Horizontal(id="search-section"):
                yield Input(placeholder="Pretraga kupaca...", id="search-input")

            yield DataTable(id="customers-table")

            with Horizontal(id="controls"):
                yield Button("Novi kupac \\[N]", id="new-btn", variant="success")
                yield Button("Izmeni \\[E]", id="edit-btn", variant="primary")
                yield Button("Kreiraj fakturu \\[I]", id="invoice-btn", variant="warning")
                yield Button("Obriši \\[D]", id="delete-btn", variant="error")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        """Setup table and load customers"""
        table = self.query_one("#customers-table", DataTable)
        table.add_columns("ID", "Ime/Kompanija", "PIB", "Telefon", "Email", "Grad")
        table.cursor_type = "row"
        
        self.load_customers()
        self.query_one("#search-input", Input).focus()
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Live search"""
        if event.input.id == "search-input":
            search_term = event.value.strip()
            self.load_customers(search_term)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-btn":
            self.action_new_customer()
        elif event.button.id == "edit-btn":
            self.action_edit_customer()
        elif event.button.id == "invoice-btn":
            self.action_create_invoice()
        elif event.button.id == "delete-btn":
            self.action_delete_customer()
        elif event.button.id == "close-btn":
            self.action_close()
    
    def load_customers(self, search_term: str = "") -> None:
        """Load customers into table"""
        table = self.query_one("#customers-table", DataTable)
        table.clear()
        
        if search_term:
            customers = self.customer_repo.search(search_term)
        else:
            customers = self.customer_repo.get_all()
        
        for customer in customers:
            display_name = customer['company_name'] if customer['company_name'] else customer['name']
            
            table.add_row(
                str(customer['id']),
                display_name,
                customer['pib'] or "",
                customer['phone'] or "",
                customer['email'] or "",
                customer['city'] or ""
            )
    
    def get_selected_customer(self) -> Optional[dict]:
        """Get currently selected customer"""
        table = self.query_one("#customers-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            customer_id = int(row[0])
            return self.customer_repo.get_by_id(customer_id)
        return None
    
    def action_new_customer(self) -> None:
        """Create new customer"""
        self.app.push_screen(
            AddEditCustomerScreen(self.customer_repo),
            self.handle_customer_changed
        )
    
    def action_edit_customer(self) -> None:
        """Edit selected customer"""
        customer = self.get_selected_customer()
        if customer:
            self.app.push_screen(
                AddEditCustomerScreen(self.customer_repo, customer),
                self.handle_customer_changed
            )
        else:
            self.notify("Izaberite kupca!", severity="warning")
    
    def action_delete_customer(self) -> None:
        """Delete customer (with confirmation)"""
        customer = self.get_selected_customer()
        if customer:
            display_name = customer['company_name'] if customer['company_name'] else customer['name']
            self.app.push_screen(
                ConfirmDialog(
                    f"Da li ste sigurni da želite obrisati '{display_name}'?",
                    "BRISANJE KUPCA"
                ),
                lambda confirmed: self.handle_delete(customer['id']) if confirmed else None
            )
        else:
            self.notify("Izaberite kupca!", severity="warning")
    
    def handle_delete(self, customer_id: int) -> None:
        """Actually delete customer"""
        if self.customer_repo.delete(customer_id):
            self.notify("Kupac obrisan!", severity="success")
            self.load_customers()
        else:
            self.notify("Greška pri brisanju!", severity="error")
    
    def action_create_invoice(self) -> None:
        """Create invoice for selected customer"""
        customer = self.get_selected_customer()
        if customer:
            self.notify("Kreiranje fakture - sledeći korak!", severity="information")
            # We'll implement this after PDF setup
        else:
            self.notify("Izaberite kupca!", severity="warning")
    
    def action_close(self) -> None:
        self.dismiss()
    
    def handle_customer_changed(self, result) -> None:
        """Callback after customer add/edit"""
        if result:
            self.load_customers()


class AddEditCustomerScreen(Screen):
    """Screen for adding or editing customer"""

    CSS = """
    AddEditCustomerScreen {
        align: center middle;
    }

    #customer-dialog {
        width: 70;
        height: 90%;
        border: thick $success;
        background: $surface;
        padding: 2;
        overflow-y: scroll;
    }

    .input-label {
        padding: 1 0 0 0;
    }

    Input {
        margin-bottom: 1;
    }

    #customer-type {
        layout: horizontal;
        height: auto;
        margin: 1 0;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }

    #company-section {
        height: auto;
    }

    #company-section.hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, customer_repo, customer: Optional[dict] = None):
        super().__init__()
        self.customer_repo = customer_repo
        self.customer = customer
        self.is_edit_mode = customer is not None
        self.is_company = customer['is_company'] if customer else False

    def compose(self) -> ComposeResult:
        title = "✏️  IZMENA KUPCA" if self.is_edit_mode else "➕ NOVI KUPAC"

        # Determine initial tax ID value based on customer type
        if self.customer:
            if self.is_company:
                tax_id_value = self.customer.get('pib', '')
            else:
                tax_id_value = self.customer.get('jmbg', '')
        else:
            tax_id_value = ""

        with Vertical(id="customer-dialog"):
            yield Label(title, classes="label")

            yield Label("Tip kupca:", classes="input-label")
            with Horizontal(id="customer-type"):
                yield Button("Fizičko lice", id="person-btn", variant="primary" if not self.is_company else "default")
                yield Button("Pravno lice", id="company-btn", variant="primary" if self.is_company else "default")

            yield Label("Ime i prezime / Kontakt osoba:", classes="input-label")
            yield Input(
                placeholder="Puno ime...",
                id="name-input",
                value=self.customer['name'] if self.customer else ""
            )

            # Company name section (only visible for companies)
            with Vertical(id="company-section", classes="" if self.is_company else "hidden"):
                yield Label("Naziv kompanije:", classes="input-label")
                yield Input(
                    placeholder="Naziv firme...",
                    id="company-input",
                    value=self.customer['company_name'] if self.customer else ""
                )

            # Single tax ID field - label changes based on type
            tax_label = "PIB:" if self.is_company else "JMBG:"
            tax_placeholder = "PIB broj..." if self.is_company else "JMBG broj..."
            yield Label(tax_label, id="tax-id-label", classes="input-label")
            yield Input(
                placeholder=tax_placeholder,
                id="tax-id-input",
                value=tax_id_value
            )

            yield Label("Adresa:", classes="input-label")
            yield Input(
                placeholder="Ulica i broj...",
                id="address-input",
                value=self.customer['address'] if self.customer else ""
            )

            yield Label("Grad:", classes="input-label")
            yield Input(
                placeholder="Grad...",
                id="city-input",
                value=self.customer['city'] if self.customer else ""
            )

            yield Label("Poštanski broj:", classes="input-label")
            yield Input(
                placeholder="Poštanski broj...",
                id="postal-input",
                value=self.customer['postal_code'] if self.customer else ""
            )

            yield Label("Telefon:", classes="input-label")
            yield Input(
                placeholder="Broj telefona...",
                id="phone-input",
                value=self.customer['phone'] if self.customer else ""
            )

            yield Label("Email:", classes="input-label")
            yield Input(
                placeholder="Email adresa...",
                id="email-input",
                value=self.customer['email'] if self.customer else ""
            )

            yield Label("Napomene:", classes="input-label")
            yield Input(
                placeholder="Dodatne napomene...",
                id="notes-input",
                value=self.customer['notes'] if self.customer else ""
            )

            with Horizontal(id="buttons"):
                yield Button("Sačuvaj", id="save-btn", variant="success")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "person-btn":
            self.is_company = False
            event.button.variant = "primary"
            self.query_one("#company-btn", Button).variant = "default"
            self._update_tax_id_field()

        elif event.button.id == "company-btn":
            self.is_company = True
            event.button.variant = "primary"
            self.query_one("#person-btn", Button).variant = "default"
            self._update_tax_id_field()

        elif event.button.id == "save-btn":
            self.save_customer()

        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def _update_tax_id_field(self) -> None:
        """Update tax ID field label and placeholder based on customer type"""
        tax_label = self.query_one("#tax-id-label", Label)
        tax_input = self.query_one("#tax-id-input", Input)
        company_section = self.query_one("#company-section", Vertical)

        if self.is_company:
            tax_label.update("PIB:")
            tax_input.placeholder = "PIB broj..."
            company_section.remove_class("hidden")
        else:
            tax_label.update("JMBG:")
            tax_input.placeholder = "JMBG broj..."
            company_section.add_class("hidden")

    def save_customer(self) -> None:
        """Save customer"""
        name = self.query_one("#name-input", Input).value.strip()
        company_name = self.query_one("#company-input", Input).value.strip() if self.is_company else ""
        tax_id = self.query_one("#tax-id-input", Input).value.strip()
        address = self.query_one("#address-input", Input).value.strip()
        city = self.query_one("#city-input", Input).value.strip()
        postal_code = self.query_one("#postal-input", Input).value.strip()
        phone = self.query_one("#phone-input", Input).value.strip()
        email = self.query_one("#email-input", Input).value.strip()
        notes = self.query_one("#notes-input", Input).value.strip()

        # Set PIB or JMBG based on customer type
        if self.is_company:
            pib = tax_id
            jmbg = ""
        else:
            pib = ""
            jmbg = tax_id

        # Validation
        if not name:
            self.notify("Ime je obavezno!", severity="error")
            return

        if self.is_company and not company_name:
            self.notify("Naziv kompanije je obavezan za pravno lice!", severity="error")
            return

        try:
            if self.is_edit_mode:
                # Update existing
                success = self.customer_repo.update(
                    customer_id=self.customer['id'],
                    name=name,
                    company_name=company_name,
                    pib=pib,
                    jmbg=jmbg,
                    address=address,
                    city=city,
                    postal_code=postal_code,
                    phone=phone,
                    email=email,
                    is_company=self.is_company,
                    notes=notes
                )

                if success:
                    self.notify("✅ Kupac ažuriran!", severity="success")
                    self.dismiss(True)
                else:
                    self.notify("❌ Greška pri ažuriranju!", severity="error")
            else:
                # Create new
                customer_id = self.customer_repo.create(
                    name=name,
                    company_name=company_name,
                    pib=pib,
                    jmbg=jmbg,
                    address=address,
                    city=city,
                    postal_code=postal_code,
                    phone=phone,
                    email=email,
                    is_company=self.is_company,
                    notes=notes
                )

                self.notify("✅ Kupac kreiran!", severity="success")
                self.dismiss(True)

        except Exception as e:
            self.notify(f"❌ Greška: {str(e)}", severity="error")


class CategoryManagementScreen(Screen):
    """Screen for managing item categories"""

    CSS = """
    CategoryManagementScreen {
        background: $surface;
    }

    #category-container {
        height: 100%;
        padding: 1;
    }

    #search-section {
        height: auto;
        margin-bottom: 1;
    }

    #categories-table {
        height: 1fr;
        border: solid $primary;
        margin-bottom: 1;
    }

    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        background: $panel;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("n", "new_category", "Nova kategorija"),
        Binding("e", "edit_category", "Izmeni"),
        Binding("t", "toggle_active", "Aktiviraj/Deaktiviraj"),
        Binding("d", "delete_category", "Obriši"),
    ]

    def __init__(self, category_service):
        super().__init__()
        self.category_service = category_service

    def compose(self) -> ComposeResult:
        with Vertical(id="category-container"):
            yield Label("📂 UPRAVLJANJE KATEGORIJAMA", classes="label")

            yield DataTable(id="categories-table")

            with Horizontal(id="controls"):
                yield Button("Nova [N]", id="new-btn", variant="success")
                yield Button("Izmeni [E]", id="edit-btn", variant="primary")
                yield Button("Aktiviraj [T]", id="toggle-btn", variant="warning")
                yield Button("Obriši [D]", id="delete-btn", variant="error")
                yield Button("Zatvori [ESC]", id="close-btn", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        """Setup table and load categories"""
        table = self.query_one("#categories-table", DataTable)
        table.add_columns("ID", "Ikona", "Naziv", "Redosled", "Artikala", "Status")
        table.cursor_type = "row"

        self.load_categories()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-btn":
            self.action_new_category()
        elif event.button.id == "edit-btn":
            self.action_edit_category()
        elif event.button.id == "toggle-btn":
            self.action_toggle_active()
        elif event.button.id == "delete-btn":
            self.action_delete_category()
        elif event.button.id == "close-btn":
            self.action_close()

    def load_categories(self) -> None:
        """Load categories into table"""
        table = self.query_one("#categories-table", DataTable)
        table.clear()

        categories = self.category_service.get_all_categories(include_inactive=True)

        for cat in categories:
            item_count = self.category_service.categories.get_item_count(cat['id'])
            status = "Aktivna" if cat['is_active'] else "Neaktivna"
            status_display = f"{'✓':^8}" if cat['is_active'] else f"{'✗':^8}"

            table.add_row(
                str(cat['id']),
                cat['icon'] or "",
                cat['name'],
                str(cat['display_order']),
                str(item_count),
                status_display
            )

    def get_selected_category(self) -> Optional[dict]:
        """Get currently selected category"""
        table = self.query_one("#categories-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            category_id = int(row[0])
            return self.category_service.get_category(category_id)
        return None

    def action_new_category(self) -> None:
        """Create new category"""
        self.app.push_screen(
            AddEditCategoryScreen(self.category_service),
            self.handle_category_changed
        )

    def action_edit_category(self) -> None:
        """Edit selected category"""
        category = self.get_selected_category()
        if category:
            self.app.push_screen(
                AddEditCategoryScreen(self.category_service, category),
                self.handle_category_changed
            )
        else:
            self.notify("Izaberite kategoriju!", severity="warning")

    def action_toggle_active(self) -> None:
        """Toggle category active status"""
        category = self.get_selected_category()
        if category:
            success, msg = self.category_service.toggle_category_active(category['id'])
            if success:
                self.notify(msg, severity="success")
                self.load_categories()
            else:
                self.notify(msg, severity="error")
        else:
            self.notify("Izaberite kategoriju!", severity="warning")

    def action_delete_category(self) -> None:
        """Delete category (with confirmation)"""
        category = self.get_selected_category()
        if category:
            if category['id'] == 1:
                self.notify("Ne možete obrisati kategoriju 'Bez kategorije'!", severity="error")
                return

            self.app.push_screen(
                ConfirmDialog(
                    f"Da li ste sigurni da želite obrisati kategoriju '{category['name']}'?",
                    "BRISANJE KATEGORIJE"
                ),
                lambda confirmed: self.handle_delete(category['id']) if confirmed else None
            )
        else:
            self.notify("Izaberite kategoriju!", severity="warning")

    def handle_delete(self, category_id: int) -> None:
        """Actually delete category"""
        success, msg = self.category_service.delete_category(category_id)
        if success:
            self.notify(msg, severity="success")
            self.load_categories()
        else:
            self.notify(msg, severity="error")

    def action_close(self) -> None:
        self.dismiss()

    def handle_category_changed(self, result) -> None:
        """Callback after category add/edit"""
        if result:
            self.load_categories()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter/double-click on table"""
        if event.data_table.id == "categories-table":
            event.stop()
            self.action_edit_category()


class AddEditCategoryScreen(Screen):
    """Screen for adding or editing a category"""

    CSS = """
    AddEditCategoryScreen {
        align: center middle;
    }

    #category-dialog {
        width: 60;
        height: auto;
        border: thick $success;
        background: $surface;
        padding: 2;
    }

    .input-label {
        padding: 1 0 0 0;
    }

    Input {
        margin-bottom: 1;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, category_service, category: Optional[dict] = None):
        super().__init__()
        self.category_service = category_service
        self.category = category
        self.is_edit_mode = category is not None

    def compose(self) -> ComposeResult:
        title = "✏️  IZMENA KATEGORIJE" if self.is_edit_mode else "➕ NOVA KATEGORIJA"

        with Vertical(id="category-dialog"):
            yield Label(title, classes="label")

            yield Label("Naziv kategorije:", classes="input-label")
            yield Input(
                placeholder="Npr. Pivo, Roštilj, Deserti...",
                id="name-input",
                value=self.category['name'] if self.category else ""
            )

            yield Label("Ikona (emoji):", classes="input-label")
            yield Input(
                placeholder="Npr. 🍺, 🍽️, 🍰...",
                id="icon-input",
                value=self.category.get('icon', '') if self.category else ""
            )

            yield Label("Redosled prikaza:", classes="input-label")
            yield Input(
                placeholder="0-99 (manji broj = ranije)",
                id="order-input",
                type="integer",
                value=str(self.category['display_order']) if self.category else "0"
            )

            with Horizontal(id="buttons"):
                yield Button("Sačuvaj", id="save-btn", variant="success")
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Focus name input"""
        self.query_one("#name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "save-btn":
            self.save_category()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def save_category(self) -> None:
        """Save the category"""
        name = self.query_one("#name-input", Input).value.strip()
        icon = self.query_one("#icon-input", Input).value.strip()
        order_str = self.query_one("#order-input", Input).value.strip()

        # Validation
        if not name:
            self.notify("Naziv je obavezan!", severity="error")
            return

        try:
            display_order = int(order_str) if order_str else 0
        except ValueError:
            self.notify("Redosled mora biti broj!", severity="error")
            return

        try:
            if self.is_edit_mode:
                success, msg = self.category_service.update_category(
                    self.category['id'], name, display_order, icon
                )
                if success:
                    self.notify(f"✅ {msg}", severity="success")
                    self.dismiss(True)
                else:
                    self.notify(f"❌ {msg}", severity="error")
            else:
                success, msg, category_id = self.category_service.create_category(
                    name, display_order, icon
                )
                if success:
                    self.notify(f"✅ {msg}", severity="success")
                    self.dismiss(True)
                else:
                    self.notify(f"❌ {msg}", severity="error")

        except Exception as e:
            self.notify(f"❌ Greška: {str(e)}", severity="error")

    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)


class CustomerSelectScreen(Screen):
    """Screen for selecting a customer during checkout"""

    CSS = """
    CustomerSelectScreen {
        align: center middle;
    }

    #select-dialog {
        width: 90;
        height: 85%;
        border: thick $accent;
        background: $surface;
        padding: 2;
    }

    #search-section {
        height: auto;
        margin-bottom: 1;
    }

    #customers-table {
        height: 1fr;
        border: solid $primary;
        margin-bottom: 1;
    }

    #controls {
        height: auto;
        layout: horizontal;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select", "Select"),
    ]

    def __init__(self, customer_repo):
        super().__init__()
        self.customer_repo = customer_repo
        self.customers_data = []  # Store customer data for lookup

    def compose(self) -> ComposeResult:
        with Vertical(id="select-dialog"):
            yield Label("👤 IZABERI KUPCA ZA FAKTURU", classes="label")

            with Horizontal(id="search-section"):
                yield Input(placeholder="Pretraga kupaca...", id="search-input")

            yield DataTable(id="customers-table")

            with Horizontal(id="controls"):
                yield Button("Izaberi \\[Enter]", id="select-btn", variant="success")
                yield Button("Ukloni kupca", id="remove-btn", variant="warning")
                yield Button("Otkazi \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Setup table and load customers"""
        table = self.query_one("#customers-table", DataTable)
        table.add_columns("ID", "Ime/Kompanija", "Tip", "ID broj", "Grad")
        table.cursor_type = "row"

        self.load_customers()
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Live search"""
        if event.input.id == "search-input":
            search_term = event.value.strip()
            self.load_customers(search_term)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in search input - select current row"""
        if event.input.id == "search-input":
            self.action_select()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter/double-click on table row"""
        self.action_select()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-btn":
            self.action_select()
        elif event.button.id == "remove-btn":
            # Return signal to remove previously selected customer
            self.dismiss({'action': 'remove'})
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def load_customers(self, search_term: str = "") -> None:
        """Load customers into table"""
        table = self.query_one("#customers-table", DataTable)
        table.clear()

        if search_term:
            self.customers_data = self.customer_repo.search(search_term)
        else:
            self.customers_data = self.customer_repo.get_all()

        for customer in self.customers_data:
            display_name = customer['company_name'] if customer['company_name'] else customer['name']
            is_company = customer.get('is_company', False)

            # Show type and appropriate ID
            customer_type = "Pravno" if is_company else "Fizičko"
            tax_id = customer.get('pib', '') if is_company else customer.get('jmbg', '')

            table.add_row(
                str(customer['id']),
                display_name,
                customer_type,
                tax_id or "-",
                customer.get('city') or ""
            )

    def action_select(self) -> None:
        """Select current customer"""
        table = self.query_one("#customers-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.customers_data):
            customer = self.customers_data[table.cursor_row]
            customer_id = customer['id']

            # Automatically determine tax_id_type based on customer type
            is_company = customer.get('is_company', False)
            tax_id_type = "pib" if is_company else "jmbg"

            # Return customer_id and tax_id_type
            self.dismiss({
                'customer_id': customer_id,
                'tax_id_type': tax_id_type
            })
        else:
            self.notify("Izaberite kupca iz liste!", severity="warning")

    def action_cancel(self) -> None:
        """Cancel selection"""
        self.dismiss(None)


class UserManagementScreen(Screen):
    """Admin screen for managing users"""

    CSS = """
    UserManagementScreen {
        background: $surface;
    }

    #user-container {
        height: 100%;
        padding: 1;
    }

    #user-table {
        height: 1fr;
        border: solid $primary;
    }

    #user-controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        background: $panel;
        padding: 1;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f2", "close", "Main", show=True),
        Binding("n", "new_user", "New User"),
        Binding("p", "change_password", "Change Password"),
        Binding("d", "toggle_active", "Toggle Active"),
        Binding("delete", "delete_user", "Delete User"),
    ]

    def __init__(self, user_service):
        super().__init__()
        self.user_service = user_service

    def compose(self) -> ComposeResult:
        with Vertical(id="user-container"):
            yield Label("👥 UPRAVLJANJE KORISNICIMA", classes="label")
            yield DataTable(id="user-table")

            with Horizontal(id="user-controls"):
                yield Button("Novi korisnik \\[N]", id="new-user-btn", variant="success")
                yield Button("Promeni lozinku \\[P]", id="password-btn", variant="primary")
                yield Button("Aktiviraj/Deaktiviraj \\[D]", id="toggle-btn", variant="warning")
                yield Button("Obriši \\[Del]", id="delete-btn", variant="error")
                yield Button("Zatvori \\[Esc]", id="close-btn", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        """Setup table and load users"""
        table = self.query_one("#user-table", DataTable)
        table.add_columns("ID", "Korisničko ime", "Puno ime", "Uloga", "Aktivan", "Poslednja prijava")
        table.cursor_type = "row"

        self.load_users()

    def load_users(self) -> None:
        """Load all users into table"""
        table = self.query_one("#user-table", DataTable)
        table.clear()

        users = self.user_service.get_all_users()

        for user in users:
            table.add_row(
                str(user['id']),
                user['username'],
                user['full_name'],
                user['role'].upper(),
                "DA" if user['is_active'] else "NE",
                user['last_login'] or "Nikad"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "new-user-btn":
            self.action_new_user()
        elif event.button.id == "password-btn":
            self.action_change_password()
        elif event.button.id == "toggle-btn":
            self.action_toggle_active()
        elif event.button.id == "close-btn":
            self.action_close()
        elif event.button.id == "delete-btn":
            self.action_delete_user()

    def action_new_user(self) -> None:
        """Create new user"""
        self.app.push_screen(CreateUserScreen(self.user_service), self.handle_user_created)

    def action_change_password(self) -> None:
        """Change password for selected user"""
        table = self.query_one("#user-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            user_id = int(row[0])
            username = row[1]

            self.app.push_screen(
                ChangePasswordScreen(self.user_service, user_id, username),
                self.handle_password_changed
            )
        else:
            self.notify("Izaberite korisnika!", severity="warning")

    def action_toggle_active(self) -> None:
        """Toggle user active status"""
        table = self.query_one("#user-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            user_id = int(row[0])
            is_active = row[4] == "DA"

            if is_active:
                success = self.user_service.users.de_activate_user(user_id, 0)
                action = "deaktiviran"
            else:
                success = self.user_service.users.de_activate_user(user_id, 1)
                action = "aktiviran"

            if success:
                self.notify(f"Korisnik {action}!", severity="success")
                self.load_users()
            else:
                self.notify("Greška!", severity="error")
        else:
            self.notify("Izaberite korisnika!", severity="warning")

    def action_close(self) -> None:
        """Close screen"""
        self.dismiss()

    def handle_user_created(self, result) -> None:
        """Callback after creating user"""
        if result:
            self.load_users()

    def handle_password_changed(self, result) -> None:
        """Callback after password change"""
        if result:
            self.notify("Lozinka promenjena!", severity="success")

    def action_delete_user(self) -> None:
        """Delete user permanently"""
        table = self.query_one("#user-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            user_id = int(row[0])
            username = row[1]

            self.app.push_screen(
                ConfirmDeleteScreen(self.user_service, user_id, username),
                self.handle_user_deleted
            )
        else:
            self.notify("Izaberite korisnika!", severity="warning")

    def handle_user_deleted(self, result) -> None:
        """Callback after user deletion"""
        if result:
            self.load_users()


class InventoryManagementScreen(Screen):
    """Admin screen for managing inventory"""

    CSS = """
    InventoryManagementScreen {
        background: $surface;
    }

    #inventory-container {
        height: 100%;
        padding: 1;
    }

    #inventory-table {
        height: 1fr;
        border: solid $primary;
    }

    #search-container {
        height: auto;
        margin-bottom: 1;
    }

    #inventory-controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        background: $panel;
        padding: 1;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f2", "close", "Main", show=True),
        Binding("n", "new_item", "New Item"),
        Binding("e", "edit_item", "Edit Item"),
        Binding("delete", "delete_item", "Delete Item"),
        Binding("p", "change_price", "Change Price"),
    ]

    def __init__(self, pos_service, category_service=None):
        super().__init__()
        self.pos_service = pos_service
        self.category_service = category_service

    def compose(self) -> ComposeResult:
        with Vertical(id="inventory-container"):
            yield Label("📦 UPRAVLJANJE INVENTAROM", classes="label")

            with Horizontal(id="search-container"):
                yield Input(placeholder="Pretraga artikala...", id="search-input")

            yield DataTable(id="inventory-table")

            with Horizontal(id="inventory-controls"):
                yield Button("Novi artikal \\[N]", id="new-item-btn", variant="success")
                yield Button("Izmeni \\[E]", id="edit-item-btn", variant="primary")
                yield Button("Promeni cenu \\[P]", id="price-btn", variant="warning")
                yield Button("Obriši \\[Del]", id="delete-item-btn", variant="error")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        """Setup table and load inventory"""
        table = self.query_one("#inventory-table", DataTable)
        table.add_columns("ID", "Artikal", "Kategorija", "Barkod", "Cena", "Količina", "PDV %")
        table.cursor_type = "row"

        self.load_inventory()

        # Focus search
        self.query_one("#search-input", Input).focus()

    def load_inventory(self, search_term: str = "") -> None:
        """Load inventory into table"""
        table = self.query_one("#inventory-table", DataTable)
        table.clear()

        items = self.pos_service.search_inventory(search_term)

        for item in items:
            vat_percent = int(item.get('vat_rate', 0.20) * 100)
            stock_display = f"{item['quantity']:.2f}"
            if item['quantity'] <= 0:
                stock_display = f"{stock_display:<10}{'⛔':>2}"
            elif item['quantity'] < CONFIG['low_stock_threshold']:
                stock_display = f"{stock_display:<10}{'🟡':>2}"
            # Get category display
            cat_icon = item.get('category_icon') or ""
            cat_name = item.get('category_name') or "Bez kategorije"
            category_display = f"{cat_icon} {cat_name}".strip()
            table.add_row(
                str(item['id']),
                item['item'],
                category_display,
                item.get('barcode') or "",
                f"{item['price']:.2f}",
                stock_display,
                f"{vat_percent}%"
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Live search"""
        if event.input.id == "search-input":
            self.load_inventory(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "new-item-btn":
            self.action_new_item()
        elif event.button.id == "edit-item-btn":
            self.action_edit_item()
        elif event.button.id == "price-btn":
            self.action_change_price()
        elif event.button.id == "delete-item-btn":
            self.action_delete_item()
        elif event.button.id == "close-btn":
            self.action_close()

    def get_selected_item(self) -> Optional[dict]:
        """Get currently selected item"""
        table = self.query_one("#inventory-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            item_id = int(row[0])
            return self.pos_service.get_inventory_item(item_id)
        return None

    def action_new_item(self) -> None:
        """Create new inventory item"""
        self.app.push_screen(
            AddEditItemScreen(self.pos_service, category_service=self.category_service),
            self.handle_item_changed
        )

    def action_edit_item(self) -> None:
        """Edit selected item"""
        item = self.get_selected_item()
        if item:
            self.app.push_screen(
                AddEditItemScreen(self.pos_service, item, category_service=self.category_service),
                self.handle_item_changed
            )
        else:
            self.notify("Izaberite artikal!", severity="warning")

    def action_change_price(self) -> None:
        """Quick price change"""
        item = self.get_selected_item()
        if item:
            self.app.push_screen(
                ChangePriceScreen(self.pos_service, item),
                self.handle_item_changed
            )
        else:
            self.notify("Izaberite artikal!", severity="warning")

    def action_delete_item(self) -> None:
        """Delete item (with confirmation)"""
        item = self.get_selected_item()
        if item:
            self.app.push_screen(
                ConfirmDialog(
                    f"Da li ste sigurni da želite obrisati '{item['item']}'?",
                    "BRISANJE ARTIKLA"
                ),
                lambda confirmed: self.handle_delete(item['id']) if confirmed else None
            )
        else:
            self.notify("Izaberite artikal!", severity="warning")

    def handle_delete(self, item_id: int) -> None:
        """Actually delete the item"""
        # We need to add delete method to inventory repository
        try:
            # For now, just set quantity to 0 (soft delete)
            self.pos_service.inventory.update_quantity(item_id, -999999)
            self.notify("Artikal obrisan!", severity="success")
            self.load_inventory()
        except Exception as e:
            self.notify(f"Greška: {str(e)}", severity="error")

    def action_close(self) -> None:
        """Close screen"""
        self.dismiss()

    def handle_item_changed(self, result) -> None:
        """Callback after item add/edit"""
        if result:
            self.load_inventory()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter key (immediate) or double-click (mouse) on inventory table"""
        if event.data_table.id == "inventory-table":
            # For keyboard (Enter), activate immediately
            # For mouse clicks, require double-click
            # We can't distinguish perfectly, but Enter is more common, so just activate
            event.stop()
            self.action_edit_item()

class AddEditItemScreen(Screen):
    """Screen for adding or editing inventory item"""

    CSS = """
    AddEditItemScreen {
        align: center middle;
    }

    #item-dialog {
        width: 60;
        height: auto;
        border: thick $success;
        background: $surface;
        padding: 2;
    }

    .input-label {
        padding: 1 0 0 0;
    }

    Input {
        margin-bottom: 1;
    }

    Select {
        margin-bottom: 1;
    }

    #vat-selection {
        layout: horizontal;
        height: auto;
        margin: 1 0;
    }

    #type-selection {
        layout: horizontal;
        height: auto;
        margin: 1 0;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, pos_service, item: Optional[dict] = None, category_service=None):
        super().__init__()
        self.pos_service = pos_service
        self.category_service = category_service
        self.item = item  # None for new item, dict for editing
        self.is_edit_mode = item is not None
        self.selected_vat = item.get('vat_rate', 0.20) if item else 0.20
        self.selected_item_type = item.get('item_type', 'other') if item else 'other'
        self.selected_category_id = item.get('category_id', 1) if item else 1

    def compose(self) -> ComposeResult:
        title = "✏️  IZMENA ARTIKLA" if self.is_edit_mode else "➕ NOVI ARTIKAL"

        # Get categories for dropdown
        category_options = [(1, "Bez kategorije")]
        if self.category_service:
            categories = self.category_service.get_all_categories()
            category_options = [
                (cat['id'], f"{cat['icon']} {cat['name']}" if cat['icon'] else cat['name'])
                for cat in categories
            ]

        with Vertical(id="item-dialog"):
            yield Label(title, classes="label")

            yield Label("Naziv artikla:", classes="input-label")
            yield Input(
                placeholder="Pun naziv artikla...",
                id="name-input",
                value=self.item['item'] if self.item else ""
            )

            yield Label("Barkod (opciono):", classes="input-label")
            yield Input(
                placeholder="Skenirajte ili unesite barkod...",
                id="barcode-input",
                value=self.item.get('barcode') or "" if self.item else ""
            )

            yield Label("Cena (RSD):", classes="input-label")
            yield Input(
                placeholder="Cena po komadu...",
                id="price-input",
                type="number",
                value=str(self.item['price']) if self.item else ""
            )

            yield Label("Količina:", classes="input-label")
            yield Input(
                placeholder="Trenutna količina na stanju...",
                id="quantity-input",
                type="number",
                value=str(self.item['quantity']) if self.item else ""
            )

            yield Label("Kategorija:", classes="input-label")
            yield Select(
                [(label, value) for value, label in category_options],
                id="category-select",
                value=self.selected_category_id,
                allow_blank=False
            )

            yield Label("PDV stopa:", classes="input-label")
            with Horizontal(id="vat-selection"):
                yield Button("0%", id="vat-0", variant="default")
                yield Button("10%", id="vat-10", variant="default")
                yield Button("20%", id="vat-20", variant="primary")

            yield Label("Tip artikla (za restoran):", classes="input-label")
            with Horizontal(id="type-selection"):
                yield Button("Hrana", id="type-food", variant="default")
                yield Button("Piće", id="type-drink", variant="default")
                yield Button("Ostalo", id="type-other", variant="primary")

            with Horizontal(id="buttons"):
                yield Button("Sačuvaj", id="save-btn", variant="success")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Focus name input and set VAT button states"""
        self.query_one("#name-input", Input).focus()

        # Highlight correct VAT button
        self.update_vat_buttons()
        self.update_type_buttons()

    def update_vat_buttons(self) -> None:
        """Update VAT button appearances"""
        vat_buttons = {
            0.0: self.query_one("#vat-0", Button),
            0.10: self.query_one("#vat-10", Button),
            0.20: self.query_one("#vat-20", Button),
        }

        for rate, button in vat_buttons.items():
            button.variant = "primary" if rate == self.selected_vat else "default"

    def update_type_buttons(self) -> None:
        """Update item type button appearances"""
        type_buttons = {
            'food': self.query_one("#type-food", Button),
            'drink': self.query_one("#type-drink", Button),
            'other': self.query_one("#type-other", Button),
        }

        for item_type, button in type_buttons.items():
            button.variant = "primary" if item_type == self.selected_item_type else "default"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "vat-0":
            self.selected_vat = 0.0
            self.update_vat_buttons()
        elif event.button.id == "vat-10":
            self.selected_vat = 0.10
            self.update_vat_buttons()
        elif event.button.id == "vat-20":
            self.selected_vat = 0.20
            self.update_vat_buttons()
        elif event.button.id == "type-food":
            self.selected_item_type = 'food'
            self.update_type_buttons()
        elif event.button.id == "type-drink":
            self.selected_item_type = 'drink'
            self.update_type_buttons()
        elif event.button.id == "type-other":
            self.selected_item_type = 'other'
            self.update_type_buttons()
        elif event.button.id == "save-btn":
            self.save_item()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle category selection change"""
        if event.select.id == "category-select":
            self.selected_category_id = event.value

    def save_item(self) -> None:
        """Save the item"""
        name = self.query_one("#name-input", Input).value.strip()
        barcode = self.query_one("#barcode-input", Input).value.strip() or None
        price_str = self.query_one("#price-input", Input).value.strip()
        quantity_str = self.query_one("#quantity-input", Input).value.strip()

        # Get selected category from Select widget
        category_select = self.query_one("#category-select", Select)
        category_id = category_select.value if category_select.value != Select.BLANK else 1

        # Validation
        if not name:
            self.notify("Naziv je obavezan!", severity="error")
            return

        try:
            price = float(price_str)
            quantity = float(quantity_str)
        except ValueError:
            self.notify("Cena i količina moraju biti brojevi!", severity="error")
            return

        if price < 0 or quantity < 0:
            self.notify("Cena i količina ne mogu biti negativne!", severity="error")
            return

        try:
            if self.is_edit_mode:
                # Update existing item - all fields including name, barcode, VAT, item_type, category
                item_id = self.item['id']
                self.pos_service.inventory.update_item(
                    item_id, name, barcode, price, quantity, self.selected_vat,
                    self.selected_item_type, category_id
                )
                self.notify(f"✅ Artikal '{name}' ažuriran!", severity="success")
            else:
                # Add new item with VAT rate, item_type, and category
                item_id = self.pos_service.inventory.add(
                    name, price, quantity, barcode, self.selected_vat,
                    self.selected_item_type, category_id
                )
                self.notify(f"✅ Artikal '{name}' dodat!", severity="success")

            self.dismiss(True)

        except Exception as e:
            self.notify(f"❌ Greška: {str(e)}", severity="error")

    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)


class OtpremniceScreen(Screen):
    """Screen for managing otpremnice (delivery notes / invoices for receiving goods)"""

    CSS = """
    OtpremniceScreen {
        background: $surface;
    }

    #otpremnice-container {
        height: 100%;
        padding: 1;
    }

    #main-panels {
        layout: horizontal;
        height: 1fr;
    }

    #left-panel {
        width: 2fr;
        border: solid $primary;
        padding: 1;
        margin-right: 1;
    }

    #right-panel {
        width: 3fr;
        border: solid $accent;
        padding: 1;
    }

    #otpremnice-list {
        height: 1fr;
    }

    #items-table {
        height: 1fr;
        margin-top: 1;
    }

    #right-header {
        layout: horizontal;
        height: auto;
    }

    #invoice-number-input {
        width: 1fr;
        margin-right: 1;
    }

    #right-controls {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }

    .label {
        padding: 1 0;
        text-style: bold;
        color: $accent;
    }

    .section-label {
        padding: 0 0 1 0;
        text-style: bold;
    }

    #total-label {
        padding: 1;
        text-style: bold;
        background: $success;
        color: $text;
        text-align: center;
        margin-top: 1;
    }

    Button {
        margin: 0 1;
    }

    #main-action-btn {
        min-width: 20;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f2", "close", "Main", show=True),
        Binding("n", "main_action", "Nova/Dodaj"),
        Binding("d", "remove_item", "Ukloni"),
        Binding("s", "save_otpremnica", "Sačuvaj"),
    ]

    def __init__(self, pos_service, invoice_repo):
        super().__init__()
        self.pos_service = pos_service
        self.invoice_repo = invoice_repo
        self.invoice_items = []  # Items for new otpremnica
        self.editing_mode = False  # True when creating new otpremnica
        self.selected_otpremnica_id = None  # Currently selected from list

    def compose(self) -> ComposeResult:
        with Vertical(id="otpremnice-container"):
            yield Label("📄 OTPREMNICE - PRIJEM ROBE", classes="label")

            with Horizontal(id="main-panels"):
                # Left panel - List of previous otpremnice
                with Vertical(id="left-panel"):
                    yield Label("Prethodne otpremnice:", classes="section-label")
                    yield DataTable(id="otpremnice-list", zebra_stripes=True)

                # Right panel - Items for selected/new otpremnica
                with Vertical(id="right-panel"):
                    yield Label("Stavke otpremnice:", classes="section-label")
                    with Horizontal(id="right-header"):
                        yield Input(
                            placeholder="Broj otpremnice...",
                            id="invoice-number-input",
                            disabled=True
                        )
                        yield Button("+ Nova otpremnica \\[N]", id="main-action-btn", variant="success")
                    yield DataTable(id="items-table", zebra_stripes=True)
                    yield Static("UKUPNO: 0.00 RSD", id="total-label")

                    with Horizontal(id="right-controls"):
                        yield Button("Sačuvaj \\[S]", id="save-btn", variant="success", disabled=True)
                        yield Button("Ukloni stavku \\[D]", id="remove-item-btn", variant="error", disabled=True)
                        yield Button("Otkaži", id="cancel-btn", variant="warning", disabled=True)
                        yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        """Setup tables"""
        # Setup otpremnice list table
        list_table = self.query_one("#otpremnice-list", DataTable)
        list_table.add_columns("ID", "Broj", "Datum", "Vreme", "Ukupno")
        list_table.cursor_type = "row"

        # Setup items table
        items_table = self.query_one("#items-table", DataTable)
        items_table.add_columns("Naziv", "Barkod", "Cena", "Količina", "Ukupno")
        items_table.cursor_type = "row"

        # Load existing otpremnice
        self.load_otpremnice_list()

    def load_otpremnice_list(self) -> None:
        """Load all otpremnice into left table"""
        table = self.query_one("#otpremnice-list", DataTable)
        table.clear()

        invoices = self.invoice_repo.get_all_invoices()
        for inv in invoices:
            # Get total for this invoice
            details = self.invoice_repo.get_invoice_details(inv['id'])
            total = details['total'] if details else 0

            table.add_row(
                str(inv['id']),
                inv['invoice'],
                inv.get('date', ''),
                inv.get('time', ''),
                f"{total:.2f}"
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in otpremnice list"""
        if event.data_table.id == "otpremnice-list" and not self.editing_mode:
            # Get selected otpremnica ID
            row = event.data_table.get_row(event.row_key)
            otpremnica_id = int(row[0])
            self.selected_otpremnica_id = otpremnica_id
            self.show_otpremnica_items(otpremnica_id)

    def show_otpremnica_items(self, otpremnica_id: int) -> None:
        """Display items for selected otpremnica"""
        details = self.invoice_repo.get_invoice_details(otpremnica_id)
        if not details:
            return

        # Update invoice number display
        invoice_input = self.query_one("#invoice-number-input", Input)
        invoice_input.value = details['header']['invoice']

        # Update items table
        items_table = self.query_one("#items-table", DataTable)
        items_table.clear()

        for item in details['items']:
            items_table.add_row(
                item['item'],
                "",  # Barcode not stored in invoice_data
                f"{item['price']:.2f}",
                f"{item['quantity']:.2f}",
                f"{item['total']:.2f}"
            )

        # Update total
        self.update_total_label(details['total'])

    def update_total_label(self, total: float) -> None:
        """Update the total label"""
        label = self.query_one("#total-label", Static)
        label.update(f"UKUPNO: {total:.2f} RSD")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "main-action-btn":
            self.action_main_action()
        elif event.button.id == "remove-item-btn":
            self.action_remove_item()
        elif event.button.id == "save-btn":
            self.action_save_otpremnica()
        elif event.button.id == "cancel-btn":
            self.action_cancel_edit()
        elif event.button.id == "close-btn":
            self.action_close()

    def action_main_action(self) -> None:
        """Handle main action button - either start new or add item"""
        if not self.editing_mode:
            # Start new otpremnica
            self.start_new_otpremnica()
        else:
            # Add item to current otpremnica
            self.add_item()

    def start_new_otpremnica(self) -> None:
        """Start creating new otpremnica"""
        self.editing_mode = True
        self.invoice_items = []
        self.selected_otpremnica_id = None

        # Change button to "Dodaj stavku" mode
        main_btn = self.query_one("#main-action-btn", Button)
        main_btn.label = "Dodaj stavku \\[N]"
        main_btn.variant = "primary"

        # Enable editing controls
        self.query_one("#invoice-number-input", Input).disabled = False
        self.query_one("#invoice-number-input", Input).value = ""
        self.query_one("#invoice-number-input", Input).focus()
        self.query_one("#save-btn", Button).disabled = False
        self.query_one("#remove-item-btn", Button).disabled = False
        self.query_one("#cancel-btn", Button).disabled = False

        # Clear items table
        items_table = self.query_one("#items-table", DataTable)
        items_table.clear()
        self.update_total_label(0)

        self.notify("Nova otpremnica - unesite broj i dodajte stavke", severity="information")

    def add_item(self) -> None:
        """Add item to new otpremnica"""
        self.app.push_screen(
            AddInvoiceItemScreen(self.pos_service),
            self.handle_item_added
        )

    def action_cancel_edit(self) -> None:
        """Cancel creating new otpremnica"""
        self.editing_mode = False
        self.invoice_items = []

        # Change button back to "Nova otpremnica" mode
        main_btn = self.query_one("#main-action-btn", Button)
        main_btn.label = "+ Nova otpremnica \\[N]"
        main_btn.variant = "success"

        # Disable editing controls
        self.query_one("#invoice-number-input", Input).disabled = True
        self.query_one("#invoice-number-input", Input).value = ""
        self.query_one("#save-btn", Button).disabled = True
        self.query_one("#remove-item-btn", Button).disabled = True
        self.query_one("#cancel-btn", Button).disabled = True

        # Clear items table
        items_table = self.query_one("#items-table", DataTable)
        items_table.clear()
        self.update_total_label(0)

        self.notify("Otkazano", severity="warning")

    def action_remove_item(self) -> None:
        """Remove selected item from new otpremnica"""
        if not self.editing_mode:
            return

        table = self.query_one("#items-table", DataTable)
        if table.cursor_row is not None and self.invoice_items:
            del self.invoice_items[table.cursor_row]
            self.update_items_display()
            self.notify("Stavka uklonjena", severity="warning")

    def action_save_otpremnica(self) -> None:
        """Save new otpremnica"""
        if not self.editing_mode:
            return

        invoice_number = self.query_one("#invoice-number-input", Input).value.strip()

        if not invoice_number:
            self.notify("Unesite broj otpremnice!", severity="error")
            return

        if not self.invoice_items:
            self.notify("Dodajte barem jednu stavku!", severity="error")
            return

        # Convert to InvoiceItem format
        from pos_business_logic import InvoiceItem

        items = [
            InvoiceItem(
                item_name=item['name'],
                price=item['price'],
                quantity=item['quantity'],
                barcode=item.get('barcode')
            )
            for item in self.invoice_items
        ]

        success, message, invoice_id = self.pos_service.create_invoice_from_items(
            invoice_number,
            items
        )

        if success:
            self.notify(f"✅ {message}", severity="success")
            self.editing_mode = False

            # Change button back to "Nova otpremnica" mode
            main_btn = self.query_one("#main-action-btn", Button)
            main_btn.label = "+ Nova otpremnica \\[N]"
            main_btn.variant = "success"

            # Disable editing controls
            self.query_one("#invoice-number-input", Input).disabled = True
            self.query_one("#save-btn", Button).disabled = True
            self.query_one("#remove-item-btn", Button).disabled = True
            self.query_one("#cancel-btn", Button).disabled = True

            # Reload list
            self.load_otpremnice_list()
            self.invoice_items = []
        else:
            self.notify(f"❌ {message}", severity="error")

    def action_close(self) -> None:
        """Close screen"""
        self.dismiss(None)

    def handle_item_added(self, item_data) -> None:
        """Callback when item is added"""
        if item_data:
            self.invoice_items.append(item_data)
            self.update_items_display()

    def update_items_display(self) -> None:
        """Refresh items table for new otpremnica"""
        table = self.query_one("#items-table", DataTable)
        table.clear()

        total = 0
        for item in self.invoice_items:
            item_total = item['price'] * item['quantity']
            total += item_total
            table.add_row(
                item['name'],
                item.get('barcode') or "",
                f"{item['price']:.2f}",
                f"{item['quantity']:.2f}",
                f"{item_total:.2f}"
            )

        self.update_total_label(total)
            

class ReportsScreen(Screen):
    """Screen for viewing reports"""
    
    CSS = """
    ReportsScreen {
        align: center middle;
    }
    
    #reports-dialog {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 2;
    }
    
    
    .menu-button {
        width: 100%;
        margin: 1 0;
    }
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f2", "close", "Main", show=True),
        Binding("1", "daily_report", "Daily Report"),
        Binding("2", "cash_reconciliation", "Cash Count"),
        Binding("3", "low_stock", "Low Stock"),
    ]

    def __init__(self, daily_reports, reports, is_admin: bool):
        super().__init__()
        self.daily_reports = daily_reports
        self.reports = reports
        self.is_admin = is_admin

    def compose(self) -> ComposeResult:
        with Vertical(id="reports-dialog"):
            yield Label("📊 IZVEŠTAJI", classes="label")

            # with Vertical(id="report-menu"):
            yield Button("1. Dnevni izveštaj", id="daily-btn", variant="primary", classes="menu-button")
            yield Button("2. Zatvaranje kase", id="cash-btn", variant="success", classes="menu-button")
            yield Button("3. Nisko stanje zaliha", id="stock-btn", variant="warning", classes="menu-button")

            if self.is_admin:
                yield Button("4. Nedeljni izveštaj", id="weekly-btn", variant="default", classes="menu-button")
                yield Button("5. Mesečni izveštaj", id="monthly-btn", variant="default", classes="menu-button")
                yield Button("6. Top artikli", id="top-btn", variant="default", classes="menu-button")

            yield Button("Zatvori \\[ESC]", id="close-btn", variant="error", classes="menu-button")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "daily-btn":
            self.action_daily_report()
        elif event.button.id == "cash-btn":
            self.action_cash_reconciliation()
        elif event.button.id == "stock-btn":
            self.action_low_stock()
        elif event.button.id == "weekly-btn" and self.is_admin:
            self.action_weekly_report()
        elif event.button.id == "monthly-btn" and self.is_admin:
            self.action_monthly_report()
        elif event.button.id == "top-btn" and self.is_admin:
            self.show_top_items()
        elif event.button.id == "close-btn":
            self.action_close()

    def action_weekly_report(self) -> None:
        """Show weekly report"""
        self.app.push_screen(WeeklyReportScreen(self.daily_reports))

    def action_monthly_report(self) -> None:
        """Show monthly report"""
        self.app.push_screen(MonthlyReportScreen(self.daily_reports))
    
    def action_daily_report(self) -> None:
        """Show daily report"""
        self.app.push_screen(DailyReportScreen(self.daily_reports))
    
    def action_cash_reconciliation(self) -> None:
        """Cash count screen"""
        self.app.push_screen(CashReconciliationScreen(self.daily_reports))
    
    def action_low_stock(self) -> None:
        """Low stock warning"""
        self.app.push_screen(LowStockScreen(self.reports))
    
    def show_top_items(self) -> None:
        """Show top selling items"""
        self.app.push_screen(TopItemsScreen(self.reports))
    
    def action_close(self) -> None:
        """Close reports"""
        self.dismiss()


class DailyReportScreen(Screen):
    """Display daily sales report"""
    
    CSS = """
    DailyReportScreen {
        align: center middle;
    }
    
    #daily-dialog {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 2;
    }
    
    #report-content {
        height: 1fr;
        border: solid $primary;
        padding: 2;
        overflow-y: scroll;
    }
    
    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f2", "close", "Main", show=True),
    ]

    def __init__(self, daily_reports):
        super().__init__()
        self.daily_reports = daily_reports
    
    def compose(self) -> ComposeResult:
        with Vertical(id="daily-dialog"):
            yield Label("📊 DNEVNI IZVEŠTAJ", classes="label")
            
            yield Input(
                placeholder="Datum (YYYY-MM-DD) ili Enter za danas",
                id="date-input"
            )
            
            yield Static("", id="report-content")

            with Horizontal(id="controls"):
                yield Button("Prikaži", id="show-btn", variant="primary")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        """Load today's report by default"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        self.query_one("#date-input", Input).value = today
        self.load_report(today)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "show-btn":
            date = self.query_one("#date-input", Input).value.strip()
            self.load_report(date)
        elif event.button.id == "close-btn":
            self.action_close()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in date input"""
        if event.input.id == "date-input":
            self.load_report(event.value.strip())
    
    def load_report(self, date: str) -> None:
        """Load and display report"""
        from datetime import datetime

        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        report = self.daily_reports.generate_daily_report(date)

        if not report['has_sales']:
            self.query_one("#report-content", Static).update(
                f"\n{report['message']}"
            )
            return

        # Get column widths from config
        L = CONFIG['left_side']      # Left column (labels, item names)
        M = CONFIG['middle_side']    # Middle column (quantities)
        R = CONFIG['right_side']     # Right column (amounts)
        W = L + M + R                # Total width

        # Format report
        content = []
        content.append("=" * W)
        content.append(f"DNEVNI IZVEŠTAJ ZA {date}".center(W))
        content.append("=" * W)

        summary = report['summary']
        content.append(f"\n{'OSNOVNI PODACI:':^{W}}")
        content.append(f"{'Ukupan prihod:':<{L+M}}{summary['total_revenue']:>{R-4}.2f} RSD")
        content.append(f"{'Broj transakcija:':<{L+M}}{summary['total_transactions']:>{R}}")
        content.append(f"{'Prodato artikala:':<{L+M}}{summary['total_items_sold']:>{R}.2f}")
        content.append(f"{'Prosečna transakcija:':<{L+M}}{summary['avg_transaction']:>{R-4}.2f} RSD")

        payments = report['payments']
        content.append(f"\n{'NAČIN PLAĆANJA:':^{W}}")
        content.append(f"{'Gotovina:':<{L+M}}{payments['cash']:>{R-4}.2f} RSD")
        content.append(f"{'Kartica:':<{L+M}}{payments['card']:>{R-4}.2f} RSD")
        content.append(f"{'─' * R:>{W}}")
        content.append(f"{'UKUPNO:':<{L+M}}{payments['total']:>{R-4}.2f} RSD")

        content.append(f"\n{'PDV REKAPITULACIJA:':^{W}}")

        for vat_rate, data in report['vat_breakdown'].items():
            vat_percent = int(vat_rate * 100)
            content.append(f"Stopa {vat_percent}%:")
            content.append(f"{'  Osnovica:':<{L+M}}{data['base']:>{R-4}.2f} RSD")
            content.append(f"{'  PDV:':<{L+M}}{data['vat']:>{R-4}.2f} RSD")
            content.append(f"{'  Ukupno:':<{L+M}}{data['total']:>{R-4}.2f} RSD")

        content.append(f"\n{'TOP 10 ARTIKALA:':^{W}}")
        for i, (item_name, data) in enumerate(report['top_items'], 1):
            # Truncate item name if too long (leave space for number prefix)
            max_name_len = L - 4  # Account for "XX. " prefix
            name = item_name[:max_name_len] if len(item_name) > max_name_len else item_name
            content.append(f"{i:2}. {name:<{max_name_len}}{data['quantity']:>{M-4}.0f} kom{data['revenue']:>{R-4}.0f} RSD")

        content.append(f"\n{'PRODAJA PO SATIMA:':^{W}}")
        for hour, data in report['hourly_sales']:
            bar_length = int(data['revenue'] / 500)
            bar = '█' * min(bar_length, W-27)
            content.append(f"{hour}:00 {data['transactions']:>{5}} tr {bar:<{W-27}} {data['revenue']:>{7}.0f} RSD")

        # Show refunds if any
        if 'refunds' in report and report['refunds']:
            content.append(f"\n{'POVRAĆAJI:':^{W}}")
            total_refunds = sum(r['refund_amount'] for r in report['refunds'])
            content.append(f"{'Broj povraćaja:':<{L+M}}{len(report['refunds']):>{R}}")
            content.append(f"{'Ukupan iznos:':<{L+M}}{total_refunds:>{R-4}.2f} RSD")

            for refund in report['refunds'][:10]:  # Show first 10
                reason = refund['reason'] or 'Bez razloga'
                max_item_len = L - 2
                item = refund['item'][:max_item_len] if len(refund['item']) > max_item_len else refund['item']
                content.append(f"• {item:<{L-3}} {refund['quantity']:<{M-5}.0f} kom {refund['refund_amount']:>{R-4}.2f} RSD")
                content.append(f"  {reason}")

        content.append("\n" + "=" * W)

        self.query_one("#report-content", Static).update("\n".join(content))
    
    def action_close(self) -> None:
        self.dismiss()


class WeeklyReportScreen(Screen):
    """Display weekly sales report"""

    CSS = """
    WeeklyReportScreen {
        align: center middle;
    }

    #weekly-dialog {
        width: 80;
        height: auto;
        max-height: 90%;
        border: thick $accent;
        background: $surface;
        padding: 2;
    }

    #report-content {
        height: 1fr;
        min-height: 20;
        border: solid $primary;
        padding: 2;
        overflow-y: scroll;
    }

    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }

    #week-selector {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }

    #week-selector Input {
        width: 1fr;
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f2", "close", "Main", show=True),
    ]

    def __init__(self, daily_reports):
        super().__init__()
        self.daily_reports = daily_reports

    def compose(self) -> ComposeResult:
        with Vertical(id="weekly-dialog"):
            yield Label("📊 NEDELJNI IZVEŠTAJ", classes="label")

            with Horizontal(id="week-selector"):
                yield Input(placeholder="Godina (YYYY)", id="year-input", type="integer")
                yield Input(placeholder="Nedelja (1-53)", id="week-input", type="integer")
                yield Button("Prikaži", id="show-btn", variant="primary")

            yield Static("", id="report-content")

            with Horizontal(id="controls"):
                yield Button("Prethodna nedelja", id="prev-btn", variant="default")
                yield Button("Sledeća nedelja", id="next-btn", variant="default")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        """Load current week's report by default"""
        from datetime import datetime
        today = datetime.now()
        year, week, _ = today.isocalendar()

        self.query_one("#year-input", Input).value = str(year)
        self.query_one("#week-input", Input).value = str(week)
        self.load_report(year, week)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "show-btn":
            self.show_current_selection()
        elif event.button.id == "prev-btn":
            self.navigate_week(-1)
        elif event.button.id == "next-btn":
            self.navigate_week(1)
        elif event.button.id == "close-btn":
            self.action_close()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.show_current_selection()

    def show_current_selection(self) -> None:
        try:
            year = int(self.query_one("#year-input", Input).value)
            week = int(self.query_one("#week-input", Input).value)
            if 1 <= week <= 53:
                self.load_report(year, week)
            else:
                self.notify("Nedelja mora biti između 1 i 53", severity="error")
        except ValueError:
            self.notify("Unesite validnu godinu i nedelju", severity="error")

    def navigate_week(self, delta: int) -> None:
        try:
            year = int(self.query_one("#year-input", Input).value)
            week = int(self.query_one("#week-input", Input).value)

            week += delta
            if week < 1:
                year -= 1
                week = 52
            elif week > 52:
                year += 1
                week = 1

            self.query_one("#year-input", Input).value = str(year)
            self.query_one("#week-input", Input).value = str(week)
            self.load_report(year, week)
        except ValueError:
            pass

    def load_report(self, year: int, week: int) -> None:
        """Load and display weekly report"""
        report = self.daily_reports.generate_weekly_report(year, week)

        if not report['has_sales']:
            self.query_one("#report-content", Static).update(
                f"\n{report.get('message', 'Nema podataka')}"
            )
            return

        L = CONFIG['left_side']
        M = CONFIG['middle_side']
        R = CONFIG['right_side']
        W = L + M + R

        content = []
        content.append("=" * W)
        content.append(f"NEDELJNI IZVEŠTAJ: {report['period']}".center(W))
        content.append(f"({report['start_date']} - {report['end_date']})".center(W))
        content.append("=" * W)

        summary = report['summary']
        content.append(f"\n{'OSNOVNI PODACI:':^{W}}")
        content.append("─" * W)
        content.append(f"{'Ukupan promet:':<{L+M}}{summary['total_revenue']:>{R}.2f} RSD")
        content.append(f"{'Broj transakcija:':<{L+M}}{summary['total_transactions']:>{R}}")
        content.append(f"{'Prodato artikala:':<{L+M}}{summary['total_items_sold']:>{R}.0f}")
        content.append(f"{'Prosečna transakcija:':<{L+M}}{summary['avg_transaction']:>{R}.2f} RSD")
        content.append(f"{'Prosečan dnevni promet:':<{L+M}}{summary['avg_daily_revenue']:>{R}.2f} RSD")
        content.append(f"{'Dana sa prodajom:':<{L+M}}{summary['days_with_sales']:>{R}}")

        if summary['refund_count'] > 0:
            content.append(f"{'Povraćaji:':<{L+M}}{summary['total_refunds']:>{R}.2f} RSD ({summary['refund_count']})")

        # Payment breakdown
        payments = report['payments']
        content.append(f"\n{'NAČIN PLAĆANJA:':^{W}}")
        content.append("─" * W)
        content.append(f"{'Gotovina:':<{L+M}}{payments['cash']:>{R}.2f} RSD")
        content.append(f"{'Kartica:':<{L+M}}{payments['card']:>{R}.2f} RSD")

        # Daily breakdown
        if report['daily_totals']:
            content.append(f"\n{'DNEVNI PREGLED:':^{W}}")
            content.append("─" * W)
            for day in report['daily_totals']:
                date_str = day['date']
                content.append(f"{date_str:<{L}}{day['transaction_count']:>{M}} tr.{day['total_revenue']:>{R}.2f} RSD")

        # Top items
        if report['top_items']:
            content.append(f"\n{'TOP 10 ARTIKALA:':^{W}}")
            content.append("─" * W)
            for i, (item_name, data) in enumerate(report['top_items'], 1):
                name = item_name[:L-3] if len(item_name) > L-3 else item_name
                content.append(f"{i}. {name:<{L-3}}{data['quantity']:>{M}.0f}{data['revenue']:>{R}.2f}")

        # VAT breakdown
        if report['vat_breakdown']:
            content.append(f"\n{'PDV PREGLED:':^{W}}")
            content.append("─" * W)
            for rate, data in report['vat_breakdown'].items():
                rate_pct = int(rate * 100)
                content.append(f"PDV {rate_pct}%: Osnovica {data['base']:.2f}, PDV {data['vat']:.2f}, Ukupno {data['total']:.2f}")

        content.append("\n" + "=" * W)

        self.query_one("#report-content", Static).update("\n".join(content))

    def action_close(self) -> None:
        self.dismiss()


class MonthlyReportScreen(Screen):
    """Display monthly sales report"""

    CSS = """
    MonthlyReportScreen {
        align: center middle;
    }

    #monthly-dialog {
        width: 80;
        height: auto;
        max-height: 90%;
        border: thick $accent;
        background: $surface;
        padding: 2;
    }

    #report-content {
        height: 1fr;
        min-height: 20;
        border: solid $primary;
        padding: 2;
        overflow-y: scroll;
    }

    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }

    #month-selector {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }

    #month-selector Input {
        width: 1fr;
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f2", "close", "Main", show=True),
    ]

    def __init__(self, daily_reports):
        super().__init__()
        self.daily_reports = daily_reports

    def compose(self) -> ComposeResult:
        with Vertical(id="monthly-dialog"):
            yield Label("📊 MESEČNI IZVEŠTAJ", classes="label")

            with Horizontal(id="month-selector"):
                yield Input(placeholder="Godina (YYYY)", id="year-input", type="integer")
                yield Input(placeholder="Mesec (1-12)", id="month-input", type="integer")
                yield Button("Prikaži", id="show-btn", variant="primary")

            yield Static("", id="report-content")

            with Horizontal(id="controls"):
                yield Button("Prethodni mesec", id="prev-btn", variant="default")
                yield Button("Sledeći mesec", id="next-btn", variant="default")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        """Load current month's report by default"""
        from datetime import datetime
        today = datetime.now()

        self.query_one("#year-input", Input).value = str(today.year)
        self.query_one("#month-input", Input).value = str(today.month)
        self.load_report(today.year, today.month)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "show-btn":
            self.show_current_selection()
        elif event.button.id == "prev-btn":
            self.navigate_month(-1)
        elif event.button.id == "next-btn":
            self.navigate_month(1)
        elif event.button.id == "close-btn":
            self.action_close()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.show_current_selection()

    def show_current_selection(self) -> None:
        try:
            year = int(self.query_one("#year-input", Input).value)
            month = int(self.query_one("#month-input", Input).value)
            if 1 <= month <= 12:
                self.load_report(year, month)
            else:
                self.notify("Mesec mora biti između 1 i 12", severity="error")
        except ValueError:
            self.notify("Unesite validnu godinu i mesec", severity="error")

    def navigate_month(self, delta: int) -> None:
        try:
            year = int(self.query_one("#year-input", Input).value)
            month = int(self.query_one("#month-input", Input).value)

            month += delta
            if month < 1:
                year -= 1
                month = 12
            elif month > 12:
                year += 1
                month = 1

            self.query_one("#year-input", Input).value = str(year)
            self.query_one("#month-input", Input).value = str(month)
            self.load_report(year, month)
        except ValueError:
            pass

    def load_report(self, year: int, month: int) -> None:
        """Load and display monthly report"""
        report = self.daily_reports.generate_monthly_report(year, month)

        if not report['has_sales']:
            self.query_one("#report-content", Static).update(
                f"\n{report.get('message', 'Nema podataka')}"
            )
            return

        L = CONFIG['left_side']
        M = CONFIG['middle_side']
        R = CONFIG['right_side']
        W = L + M + R

        content = []
        content.append("=" * W)
        content.append(f"MESEČNI IZVEŠTAJ: {report['period']}".center(W))
        content.append(f"({report['start_date']} - {report['end_date']})".center(W))
        content.append("=" * W)

        summary = report['summary']
        content.append(f"\n{'OSNOVNI PODACI:':^{W}}")
        content.append("─" * W)
        content.append(f"{'Ukupan promet:':<{L+M}}{summary['total_revenue']:>{R}.2f} RSD")
        content.append(f"{'Broj transakcija:':<{L+M}}{summary['total_transactions']:>{R}}")
        content.append(f"{'Prodato artikala:':<{L+M}}{summary['total_items_sold']:>{R}.0f}")
        content.append(f"{'Prosečna transakcija:':<{L+M}}{summary['avg_transaction']:>{R}.2f} RSD")
        content.append(f"{'Prosečan dnevni promet:':<{L+M}}{summary['avg_daily_revenue']:>{R}.2f} RSD")
        content.append(f"{'Dana sa prodajom:':<{L+M}}{summary['days_with_sales']:>{R}}")

        if summary['refund_count'] > 0:
            content.append(f"{'Povraćaji:':<{L+M}}{summary['total_refunds']:>{R}.2f} RSD ({summary['refund_count']})")

        # Payment breakdown
        payments = report['payments']
        content.append(f"\n{'NAČIN PLAĆANJA:':^{W}}")
        content.append("─" * W)
        content.append(f"{'Gotovina:':<{L+M}}{payments['cash']:>{R}.2f} RSD")
        content.append(f"{'Kartica:':<{L+M}}{payments['card']:>{R}.2f} RSD")

        # Daily breakdown (abbreviated for monthly)
        if report['daily_totals']:
            content.append(f"\n{'DNEVNI PREGLED:':^{W}}")
            content.append("─" * W)
            for day in report['daily_totals']:
                date_str = day['date']
                content.append(f"{date_str:<{L}}{day['transaction_count']:>{M}} tr.{day['total_revenue']:>{R}.2f} RSD")

        # Top items
        if report['top_items']:
            content.append(f"\n{'TOP 10 ARTIKALA:':^{W}}")
            content.append("─" * W)
            for i, (item_name, data) in enumerate(report['top_items'], 1):
                name = item_name[:L-3] if len(item_name) > L-3 else item_name
                content.append(f"{i}. {name:<{L-3}}{data['quantity']:>{M}.0f}{data['revenue']:>{R}.2f}")

        # VAT breakdown
        if report['vat_breakdown']:
            content.append(f"\n{'PDV PREGLED:':^{W}}")
            content.append("─" * W)
            for rate, data in report['vat_breakdown'].items():
                rate_pct = int(rate * 100)
                content.append(f"PDV {rate_pct}%: Osnovica {data['base']:.2f}, PDV {data['vat']:.2f}, Ukupno {data['total']:.2f}")

        content.append("\n" + "=" * W)

        self.query_one("#report-content", Static).update("\n".join(content))

    def action_close(self) -> None:
        self.dismiss()


class CashReconciliationScreen(Screen):
    """Cash drawer reconciliation"""
    
    CSS = """
    CashReconciliationScreen {
        align: center middle;
    }
    
    #cash-dialog {
        width: 60;
        height: auto;
        border: thick $success;
        background: $surface;
        padding: 2;
    }
    
    #result {
        padding: 2;
        margin: 1 0;
        border: solid $accent;
    }
    
    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]
    
    def __init__(self, daily_reports):
        super().__init__()
        self.daily_reports = daily_reports
    
    def compose(self) -> ComposeResult:
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        
        with Vertical(id="cash-dialog"):
            yield Label("💰 ZATVARANJE KASE", classes="label")
            
            yield Label(f"Datum: {today}")
            yield Label("Prebrojana gotovina u kasi:")
            yield Input(placeholder="Iznos u dinarima...", id="cash-input", type="number")
            
            yield Static("", id="result")
            
            with Horizontal(id="buttons"):
                yield Button("Proveri \\[Enter]", id="check-btn", variant="primary")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
    
    def on_mount(self) -> None:
        self.query_one("#cash-input", Input).focus()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "check-btn":
            self.check_cash()
        elif event.button.id == "close-btn":
            self.action_close()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "cash-input":
            self.check_cash()
    
    def check_cash(self) -> None:
        """Check cash reconciliation"""
        from datetime import datetime
        
        cash_str = self.query_one("#cash-input", Input).value.strip()
        
        if not cash_str:
            self.notify("Unesite iznos!", severity="error")
            return
        
        try:
            actual_cash = float(cash_str)
            today = datetime.now().strftime("%Y-%m-%d")
            
            reconciliation = self.daily_reports.generate_cash_reconciliation(today, actual_cash)
            
            result = []
            result.append("=" * 48)
            result.append("ZATVARANJE KASE")
            result.append("=" * 48)
            result.append(f"\n'Datum: {reconciliation['date']}")
            result.append(f"\n{'Očekivana gotovina:':<32}{reconciliation['expected_cash']:>12.2f} RSD")
            result.append(f"{'Prebrojana gotovina:':<32}{actual_cash:>12.2f} RSD")
            result.append(f"{'Izdati kusur:':<32}{reconciliation['total_change_given']:>12.2f} RSD")
            result.append("─" * 48)
            
            diff = reconciliation['difference']
            if reconciliation['is_balanced']:
                result.append(f"Status: ✅ URAVNOTEŽENO")
            elif diff > 0:
                result.append(f"{'Status 🟡 VIŠAK:':<31}{diff:>12.2f} RSD")
            else:
                result.append(f"{'Status ❌ MANJAK:':<31}{abs(diff):>12.2f} RSD")
            
            result.append("=" * 48)
            
            self.query_one("#result", Static).update("\n".join(result))
            
        except ValueError:
            self.notify("Unesite ispravan iznos!", severity="error")
    
    def action_close(self) -> None:
        self.dismiss()


class LowStockScreen(Screen):
    """Low stock warning screen"""
    
    CSS = """
    LowStockScreen {
        background: $surface;
    }

    #stock-container {
        height: 100%;
        padding: 1;
    }

    #input-row {
        height: auto;
        width: 100%;
        padding: 0 1;
    }

    #input-row Label {
        padding: 1 1 1 0;
    }

    #threshold-input {
        width: 20;
    }

    #show-btn {
        margin-left: 1;
    }

    #stock-table {
        height: 1fr;
        border: solid $warning;
        margin: 1 0;
    }

    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]
    
    def __init__(self, reports):
        super().__init__()
        self.reports = reports
    
    def compose(self) -> ComposeResult:
        with Vertical(id="stock-container"):
            yield Label("🟡  NISKO STANJE ZALIHA", classes="label")
            
            with Horizontal(id="input-row"):
                yield Label("Minimalno stanje:")
                yield Input(value="10", id="threshold-input", type="number")
                yield Button("Prikaži", id="show-btn", variant="primary")
            
            yield DataTable(id="stock-table")
            
            with Horizontal(id="controls"):
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
    
    def on_mount(self) -> None:
        """Setup table and load default"""
        table = self.query_one("#stock-table", DataTable)
        table.add_columns("ID", "Artikal", "Trenutno stanje", "Barkod")
        table.cursor_type = "row"
        
        self.load_low_stock(10.0)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "show-btn":
            self.load_from_input()
        elif event.button.id == "close-btn":
            self.action_close()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "threshold-input":
            self.load_from_input()
    
    def load_from_input(self) -> None:
        """Load based on threshold input"""
        threshold_str = self.query_one("#threshold-input", Input).value.strip()
        
        try:
            threshold = float(threshold_str)
            self.load_low_stock(threshold)
        except ValueError:
            self.notify("Unesite ispravan broj!", severity="error")
    
    def load_low_stock(self, threshold: float) -> None:
        """Load items below threshold"""
        low_stock = self.reports.low_stock_report(threshold)
        
        table = self.query_one("#stock-table", DataTable)
        table.clear()
        
        if not low_stock:
            self.notify("✅ Svi artikli imaju dovoljno zaliha!", severity="success")
            return
        
        for item in low_stock:
            table.add_row(
                str(item['id']),
                item['item'],
                f"{item['quantity']:.2f}",
                item.get('barcode') or ""
            )
        
        self.notify(f"🟡  {len(low_stock)} artikala sa niskim stanjem", severity="warning")
    
    def action_close(self) -> None:
        self.dismiss()


class TopItemsScreen(Screen):
    """Top selling items report"""
    
    CSS = """
    TopItemsScreen {
        background: $surface;
    }
    
    #top-container {
        height: 100%;
        padding: 1;
    }
    
    #top-table {
        height: 1fr;
        border: solid $success;
    }
    
    #controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]
    
    def __init__(self, reports):
        super().__init__()
        self.reports = reports
    
    def compose(self) -> ComposeResult:
        with Vertical(id="top-container"):
            yield Label("🏆 TOP PRODAVANI ARTIKLI", classes="label")
            
            yield DataTable(id="top-table")
            
            with Horizontal(id="controls"):
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
    
    def on_mount(self) -> None:
        """Setup and load top items"""
        table = self.query_one("#top-table", DataTable)
        table.add_columns("Rank", "Artikal", "Prodato", "Prihod (RSD)")
        
        # Get sales summary and extract top items
        summary = self.reports.sales_summary(1000)  # Get more sales for better data
        
        # Aggregate by item
        from collections import defaultdict
        item_stats = defaultdict(lambda: {'quantity': 0, 'revenue': 0})
        
        for sale in summary['sales']:
            item_name = sale['item']
            item_stats[item_name]['quantity'] += sale['quantity']
            item_stats[item_name]['revenue'] += sale['total']
        
        # Sort by revenue
        top_items = sorted(
            item_stats.items(),
            key=lambda x: x[1]['revenue'],
            reverse=True
        )[:20]  # Top 20
        
        for i, (item_name, stats) in enumerate(top_items, 1):
            table.add_row(
                str(i),
                item_name,
                f"{stats['quantity']:.0f}",
                f"{stats['revenue']:.2f}"
            )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.action_close()
    
    def action_close(self) -> None:
        self.dismiss()


class AddInvoiceItemScreen(Screen):
    """Screen for adding item to invoice"""

    CSS = """
    AddInvoiceItemScreen {
        align: center middle;
    }

    #item-dialog {
        width: 60;
        height: auto;
        border: thick $success;
        background: $surface;
        padding: 2;
    }

    .input-label {
        padding: 1 0 0 0;
    }

    Input {
        margin-bottom: 1;
    }

    #search-results {
        height: 10;
        border: solid $accent;
        margin: 1 0;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, pos_service):
        super().__init__()
        self.pos_service = pos_service
        self.selected_item = None

    def compose(self) -> ComposeResult:
        with Vertical(id="item-dialog"):
            yield Label("➕ DODAJ STAVKU NA FAKTURU", classes="label")

            yield Label("Pretraga postojećih artikala:", classes="input-label")
            yield Input(placeholder="Ime ili barkod...", id="search-input")

            yield DataTable(id="search-results")

            yield Label("--- ILI unesi nove podatke ---", classes="input-label")

            yield Label("Naziv artikla:", classes="input-label")
            yield Input(placeholder="Pun naziv...", id="name-input")

            yield Label("Barkod (opciono):", classes="input-label")
            yield Input(placeholder="Skeniraj ili unesi...", id="barcode-input")

            yield Label("Cena:", classes="input-label")
            yield Input(placeholder="Cena po komadu...", id="price-input", type="number")

            yield Label("Količina:", classes="input-label")
            yield Input(placeholder="Količina...", id="quantity-input", type="number")

            with Horizontal(id="buttons"):
                yield Button("Dodaj \\[Enter]", id="add-btn", variant="success")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Setup search results table"""
        table = self.query_one("#search-results", DataTable)
        table.add_columns("ID", "Naziv", "Barkod", "Cena")
        table.cursor_type = "row"

        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Live search existing items"""
        if event.input.id == "search-input":
            search_term = event.value.strip()
            if search_term:
                # Try barcode first if it looks like a barcode (longer than 8 chars)
                items = []

                if len(search_term) > 8:
                    barcode_item = self.pos_service.find_item_by_barcode(search_term)
                    if barcode_item:
                        items = [barcode_item]

                # If not found by barcode, search by name
                if not items:
                    items = self.pos_service.search_inventory(search_term)

                table = self.query_one("#search-results", DataTable)
                table.clear()

                for item in items[:5]:  # Show top 5 matches
                    table.add_row(
                        str(item['id']),
                        item['item'],
                        item.get('barcode') or "",
                        f"{item['price']:.2f}"
                    )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in any input field"""
        event.stop()

        if event.input.id == "search-input":
            # Already handled above
            search_term = event.value.strip()

            if not search_term:
                return

            # Try barcode first
            item = self.pos_service.find_item_by_barcode(search_term)

            if item:
                # Barcode found - auto-select it and fill form
                self.select_item_for_invoice(item)
                # Clear search
                event.input.value = ""
            else:
                # Not a barcode - check if there's exactly one search result
                table = self.query_one("#search-results", DataTable)
                if table.row_count == 1:
                    # Auto-select the only result
                    row = table.get_row_at(0)
                    item_id = int(row[0])
                    item = self.pos_service.get_inventory_item(item_id)
                    if item:
                        self.select_item_for_invoice(item)
                        event.input.value = ""

        elif event.input.id in ["name-input", "barcode-input", "price-input", "quantity-input"]:
            self.add_item()

    def select_item_for_invoice(self, item: dict) -> None:
        """Pre-fill form with selected item"""
        self.query_one("#name-input", Input).value = item['item']
        self.query_one("#barcode-input", Input).value = item.get('barcode') or ""
        self.query_one("#price-input", Input).value = str(item['price'])

        # Focus quantity so user can immediately type quantity
        self.query_one("#quantity-input", Input).focus()

        self.notify(f"✓ {item['item']} - unesite količinu", severity="information")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """When selecting from search results"""
        if event.data_table.id == "search-results":
            event.stop()

            row = event.data_table.get_row_at(event.cursor_row)
            item_id = int(row[0])
            item = self.pos_service.get_inventory_item(item_id)

            if item:
                self.select_item_for_invoice(item)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-btn":
            self.add_item()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def add_item(self) -> None:
        """Add the item"""
        name = self.query_one("#name-input", Input).value.strip()
        barcode = self.query_one("#barcode-input", Input).value.strip() or None
        price_str = self.query_one("#price-input", Input).value.strip()
        quantity_str = self.query_one("#quantity-input", Input).value.strip()

        if not name or not price_str or not quantity_str:
            self.notify("Naziv, cena i količina su obavezni!", severity="error")
            return

        try:
            price = float(price_str)
            quantity = float(quantity_str)

            item_data = {
                'name': name,
                'barcode': barcode,
                'price': price,
                'quantity': quantity
            }

            self.dismiss(item_data)

        except ValueError:
            self.notify("Cena i količina moraju biti brojevi!", severity="error")

    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)

class ChangePriceScreen(Screen):
    """Quick screen for changing item price"""

    CSS = """
    ChangePriceScreen {
        align: center middle;
    }

    #price-dialog {
        width: 40;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 2;
    }

    .info-label {
        padding: 1;
        background: $panel;
        margin-bottom: 1;
    }

    Input {
        margin: 1 0;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, pos_service, item: dict):
        super().__init__()
        self.pos_service = pos_service
        self.item = item

    def compose(self) -> ComposeResult:
        with Vertical(id="price-dialog"):
            yield Label("💰 PROMENA CENE", classes="label")

            yield Label(
                f"Artikal: {self.item['item']}\nTrenutna cena: {self.item['price']:.2f} RSD",
                classes="info-label"
            )

            yield Label("Nova cena (RSD):")
            yield Input(
                placeholder="Unesite novu cenu...",
                id="new-price-input",
                type="number",
                value=str(self.item['price'])
            )

            with Horizontal(id="buttons"):
                yield Button("Promeni \\[Enter]", id="change-btn", variant="success")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Focus and select price input"""
        self.query_one("#new-price-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "change-btn":
            self.action_confirm()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter"""
        if event.input.id == "new-price-input":
            self.action_confirm()

    def action_confirm(self) -> None:
        """Change the price"""
        price_str = self.query_one("#new-price-input", Input).value.strip()

        try:
            new_price = float(price_str)
            if new_price < 0:
                self.notify("Cena ne može biti negativna!", severity="error")
                return

            success = self.pos_service.inventory.update_price(self.item['id'], new_price)

            if success:
                self.notify(
                    f"Cena promenjena: {self.item['price']:.2f} → {new_price:.2f} RSD",
                    severity="success"
                )
                self.dismiss(True)
            else:
                self.notify("Greška pri promeni cene!", severity="error")

        except ValueError:
            self.notify("Unesite ispravnu cenu!", severity="error")

    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)


class ConfirmDialog(Screen):
    """Generic confirmation dialog"""

    CSS = """
    ConfirmDialog {
        align: center middle;
    }

    #confirm-dialog {
        width: 50;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 2;
    }

    #message {
        padding: 2;
        text-align: center;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
        align: center middle;
    }
    """

    BINDINGS = [
        Binding("d", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, message: str, title: str = "POTVRDA"):
        super().__init__()
        self.message = message
        self.title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"🟡  {self.title}", classes="label")
            yield Static(self.message, id="message")

            with Horizontal(id="buttons"):
                yield Button("Da \\[D]", id="yes-btn", variant="error")
                yield Button("Ne \\[N]", id="no-btn", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes-btn":
            self.action_confirm()
        elif event.button.id == "no-btn":
            self.action_cancel()

    def action_confirm(self) -> None:
        """User confirmed"""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """User cancelled"""
        self.dismiss(False)


class CreateUserScreen(Screen):
    """Screen for creating new user"""

    CSS = """
    CreateUserScreen {
        align: center middle;
    }

    #create-user-dialog {
        width: 50;
        height: auto;
        border: thick $success;
        background: $surface;
        padding: 2;
    }

    .input-label {
        padding: 1 0 0 0;
    }

    Input {
        margin-bottom: 1;
    }

    #role-selection {
        layout: horizontal;
        height: auto;
        margin: 1 0;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, user_service):
        super().__init__()
        self.user_service = user_service
        self.selected_role = "cashier"

    def compose(self) -> ComposeResult:
        with Vertical(id="create-user-dialog"):
            yield Label("➕ NOVI KORISNIK", classes="label")

            yield Label("Korisničko ime:", classes="input-label")
            yield Input(placeholder="Jedinstveno korisničko ime...", id="username-input")

            yield Label("Lozinka:", classes="input-label")
            yield Input(placeholder="Minimum 6 karaktera...", password=True, id="password-input")

            yield Label("Puno ime:", classes="input-label")
            yield Input(placeholder="Ime i prezime...", id="fullname-input")

            yield Label("Uloga:", classes="input-label")
            with Horizontal(id="role-selection"):
                yield Button("Kasir", id="role-cashier", variant="primary")
                yield Button("Administrator", id="role-admin", variant="warning")

            with Horizontal(id="buttons"):
                yield Button("Kreiraj", id="create-btn", variant="success")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Focus username input"""
        self.query_one("#username-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "role-cashier":
            self.selected_role = "cashier"
            event.button.variant = "primary"
            self.query_one("#role-admin", Button).variant = "default"

        elif event.button.id == "role-admin":
            self.selected_role = "admin"
            event.button.variant = "primary"
            self.query_one("#role-cashier", Button).variant = "default"

        elif event.button.id == "create-btn":
            self.create_user()

        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def create_user(self) -> None:
        """Create the user"""
        username = self.query_one("#username-input", Input).value.strip()
        password = self.query_one("#password-input", Input).value
        fullname = self.query_one("#fullname-input", Input).value.strip()

        if not username or not password or not fullname:
            self.notify("Sva polja su obavezna!", severity="error")
            return

        if len(password) < 6:
            self.notify("Lozinka mora imati najmanje 6 karaktera!", severity="error")
            return

        # Create user directly with selected role
        try:
            user_id = self.user_service.users.create_user(
                username,
                password,
                fullname,
                self.selected_role  # Use the selected role (cashier or admin)
            )
            self.notify(f"✅ Korisnik {username} kreiran!", severity="success")
            self.dismiss(True)
        except Exception as e:
            # Handle duplicate username error
            error_msg = str(e)
            if "UNIQUE constraint failed" in error_msg:
                self.notify("❌ Korisničko ime već postoji!", severity="error")
            else:
                self.notify(f"❌ Greška: {error_msg}", severity="error")

class ChangePasswordScreen(Screen):
    """Screen for changing user password"""

    CSS = """
    ChangePasswordScreen {
        align: center middle;
    }

    #password-dialog {
        width: 40;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    .input-label {
        padding: 1 0 0 0;
    }

    Input {
        margin-bottom: 1;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, user_service, user_id: int, username: str):
        super().__init__()
        self.user_service = user_service
        self.user_id = user_id
        self.username = username

    def compose(self) -> ComposeResult:
        with Vertical(id="password-dialog"):
            yield Label(f"🔑 PROMENA LOZINKE: {self.username}", classes="label")

            yield Label("Nova lozinka:", classes="input-label")
            yield Input(placeholder="Minimum 6 karaktera...", password=True, id="new-password-input")

            yield Label("Potvrda lozinke:", classes="input-label")
            yield Input(placeholder="Ponovite lozinku...", password=True, id="confirm-password-input")

            with Horizontal(id="buttons"):
                yield Button("Promeni \\[Enter]", id="change-btn", variant="success")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Focus password input"""
        self.query_one("#new-password-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "change-btn":
            self.action_confirm()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in input"""
        self.action_confirm()

    def action_confirm(self) -> None:
        """Change password"""
        new_password = self.query_one("#new-password-input", Input).value
        confirm_password = self.query_one("#confirm-password-input", Input).value

        if len(new_password) < 6:
            self.notify("Lozinka mora imati najmanje 6 karaktera!", severity="error")
            return

        if new_password != confirm_password:
            self.notify("Lozinke se ne poklapaju!", severity="error")
            return

        success = self.user_service.users.update_password(self.user_id, new_password)

        if success:
            self.dismiss(True)
        else:
            self.notify("Greška pri promeni lozinke!", severity="error")

    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)


class PaymentScreen(Screen):
    """Modal screen for payment processing"""

    CSS = """
    PaymentScreen {
        align: center middle;
    }

    #payment-dialog {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 2;
    }

    #payment-info {
        padding: 1;
        background: $panel;
        margin-bottom: 1;
    }

    #customer-info {
        padding: 1;
        background: $success-darken-3;
        margin-bottom: 1;
    }

    #customer-info.no-customer {
        background: $panel;
    }

    #payment-buttons, #action-buttons {
        layout: horizontal;
        height: auto;
        align: left middle;
        padding-top: 1;
    }

    #cash-btn, #card-btn, #split-btn, #customer-btn, #cancel-btn {
        width: 17;
    }

    .payment-option {
        width: 1fr;
        margin: 0 1;
    }

    Input {
        margin: 1 0;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("1", "cash", "Cash"),
        Binding("2", "card", "Card"),
        Binding("3", "split", "Split"),
        Binding("4", "select_customer", "Customer"),
    ]

    def __init__(self, cart_total: float, customer_repo=None):
        super().__init__()
        self.cart_total = cart_total
        self.customer_repo = customer_repo
        self.payment_info = None
        self.selected_customer_id = None
        self.selected_tax_id_type = None

    def compose(self) -> ComposeResult:
        with Vertical(id="payment-dialog"):
            yield Label(f"💰 UKUPNO ZA NAPLATU: {self.cart_total:.2f} RSD", id="payment-info")

            yield Static("👤 Kupac: Nije izabran", id="customer-info", classes="no-customer")

            yield Label("Izaberite način plaćanja:", classes="label")

            with Horizontal(id="payment-buttons"):
                yield Button("Gotovina \\[1]", id="cash-btn", variant="success", classes="payment-option")
                yield Button("Kartica \\[2]", id="card-btn", variant="primary", classes="payment-option")
                yield Button("Kombinovano \\[3]", id="split-btn", variant="warning", classes="payment-option")

            with Horizontal(id="action-buttons"):
                yield Button("Kupac \\[4]", id="customer-btn", variant="default")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle payment method selection"""
        if event.button.id == "cash-btn":
            self.action_cash()
        elif event.button.id == "card-btn":
            self.action_card()
        elif event.button.id == "split-btn":
            self.action_split()
        elif event.button.id == "customer-btn":
            self.action_select_customer()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_select_customer(self) -> None:
        """Open customer selection screen"""
        if self.customer_repo:
            self.app.push_screen(
                CustomerSelectScreen(self.customer_repo),
                self.handle_customer_selected
            )
        else:
            self.notify("Upravljanje kupcima nije dostupno", severity="error")

    def handle_customer_selected(self, result) -> None:
        """Handle customer selection result"""
        if result:
            # Check if this is a remove action
            if result.get('action') == 'remove':
                self.selected_customer_id = None
                self.selected_tax_id_type = None
                customer_info = self.query_one("#customer-info", Static)
                customer_info.update("👤 Kupac: Nije izabran")
                customer_info.add_class("no-customer")
                return

            self.selected_customer_id = result['customer_id']
            self.selected_tax_id_type = result['tax_id_type']

            # Get customer name for display
            customer = self.customer_repo.get_by_id(self.selected_customer_id)
            if customer:
                display_name = customer['company_name'] if customer['company_name'] else customer['name']
                tax_label = "PIB" if self.selected_tax_id_type == "pib" else "JMBG"
                tax_value = customer.get(self.selected_tax_id_type) or "N/A"

                customer_info = self.query_one("#customer-info", Static)
                customer_info.update(f"👤 Kupac: {display_name} ({tax_label}: {tax_value})")
                customer_info.remove_class("no-customer")

    def action_cash(self) -> None:
        """Cash payment"""
        self.app.push_screen(CashPaymentScreen(self.cart_total), self.handle_payment_result)

    def action_card(self) -> None:
        """Card payment"""
        payment_info = PaymentInfo(
            payment_type='card',
            card_amount=self.cart_total,
            customer_id=self.selected_customer_id,
            customer_tax_id_type=self.selected_tax_id_type
        )
        self.dismiss(payment_info)

    def action_split(self) -> None:
        """Split payment"""
        self.app.push_screen(SplitPaymentScreen(self.cart_total), self.handle_payment_result)

    def action_cancel(self) -> None:
        """Cancel payment"""
        self.dismiss(None)

    def handle_payment_result(self, payment_info: PaymentInfo) -> None:
        """Handle result from sub-screens"""
        if payment_info:
            # Add customer info to payment
            payment_info.customer_id = self.selected_customer_id
            payment_info.customer_tax_id_type = self.selected_tax_id_type
            self.dismiss(payment_info)


class CashPaymentScreen(Screen):
    """Screen for cash payment with change calculation"""

    CSS = """
    CashPaymentScreen {
        align: center middle;
    }

    #cash-dialog {
        width: 50;
        height: auto;
        border: thick $success;
        background: $surface;
        padding: 2;
    }

    #amount-info {
        padding: 1;
        background: $panel;
        margin-bottom: 1;
    }

    .change-display {
        padding: 1;
        background: $success;
        color: $text;
        text-align: center;
        text-style: bold;
        margin: 1 0;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, total: float):
        super().__init__()
        self.total = total
        self.tendered = 0.0
        self.change = 0.0

    def compose(self) -> ComposeResult:
        with Vertical(id="cash-dialog"):
            yield Label(f"💵 GOTOVINA", classes="label")
            yield Label(f"Ukupno za naplatu: {self.total:.2f} RSD", id="amount-info")
            yield Input(placeholder="Primljeno novca...", id="tendered-input", type="number")
            yield Static("Kusur: 0.00 RSD", id="change-display", classes="change-display")

            with Horizontal(id="buttons"):
                yield Button("Potvrdi \\[Enter]", id="confirm-btn", variant="success")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Focus input when screen opens"""
        self.query_one("#tendered-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in tendered input"""
        if event.input.id == "tendered-input":
            self.action_confirm()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update change calculation as user types"""
        if event.input.id == "tendered-input":
            try:
                self.tendered = float(event.value) if event.value else 0.0
                self.change = self.tendered - self.total

                change_display = self.query_one("#change-display", Static)
                if self.change >= 0:
                    change_display.update(f"Kusur: {self.change:.2f} RSD")
                    change_display.styles.background = "$success"
                else:
                    change_display.update(f"Nedostaje: {abs(self.change):.2f} RSD")
                    change_display.styles.background = "$error"
            except ValueError:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.action_confirm()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_confirm(self) -> None:
        """Confirm cash payment"""
        tendered_input = self.query_one("#tendered-input", Input)

        # If input is empty, treat as exact amount (no change)
        if not tendered_input.value or tendered_input.value.strip() == "":
            payment_info = PaymentInfo(
                payment_type='cash',
                cash_amount=self.total,
                amount_tendered=self.total,  # Exact amount
                change_given=0.0
            )
            self.dismiss(payment_info)
            return

        # Otherwise validate the entered amount
        if self.change < 0:
            self.notify("Nedovoljno novca!", severity="error")
            return

        payment_info = PaymentInfo(
            payment_type='cash',
            cash_amount=self.total,
            amount_tendered=self.tendered,
            change_given=self.change
        )
        self.dismiss(payment_info)

    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)


class SplitPaymentScreen(Screen):
    """Screen for split payment (cash + card)"""

    CSS = """
    SplitPaymentScreen {
        align: center middle;
    }

    #split-dialog {
        width: 50;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 2;
    }

    .info-display {
        padding: 1;
        background: $panel;
        margin: 1 0;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, total: float):
        super().__init__()
        self.total = total
        self.cash_amount = 0.0
        self.card_amount = 0.0

    def compose(self) -> ComposeResult:
        with Vertical(id="split-dialog"):
            yield Label("💵💳 KOMBINOVANO PLAĆANJE", classes="label")
            yield Label(f"Ukupno: {self.total:.2f} RSD", classes="info-display")

            yield Label("Gotovina:")
            yield Input(placeholder="Iznos gotovine...", id="cash-input", type="number")

            yield Static(f"Kartica: 0.00 RSD", id="card-display", classes="info-display")

            with Horizontal(id="buttons"):
                yield Button("Potvrdi \\[Enter]", id="confirm-btn", variant="success")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Focus cash input"""
        self.query_one("#cash-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in cash input"""
        if event.input.id == "cash-input":
            self.action_confirm()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Auto-calculate card amount"""
        if event.input.id == "cash-input":
            try:
                self.cash_amount = float(event.value) if event.value else 0.0
                self.card_amount = max(0, self.total - self.cash_amount)

                card_display = self.query_one("#card-display", Static)
                card_display.update(f"Kartica: {self.card_amount:.2f} RSD")
            except ValueError:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.action_confirm()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_confirm(self) -> None:
        """Confirm split payment"""
        if self.cash_amount + self.card_amount < self.total:
            self.notify("Iznos ne pokriva račun!", severity="error")
            return

        payment_info = PaymentInfo(
            payment_type='split',
            cash_amount=self.cash_amount,
            card_amount=self.card_amount,
            change_given=0.0  # No change in split payment for simplicity
        )
        self.dismiss(payment_info)

    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)


class ReceiptViewerScreen(Screen):
    """Screen to display fiscal receipt"""

    CSS = """
    ReceiptViewerScreen {
        align: center middle;
    }

    #receipt-container {
        width: 80;
        height: 90%;
        border: thick $success;
        background: $surface;
        padding: 1;
    }

    #receipt-display {
        width: 100%;
        height: 1fr;
        border: solid $primary;
        background: black;
        color: white;
        padding: 1;
        overflow-y: scroll;
    }

    #close-button-container {
        height: auto;
        align: center middle;
        padding-top: 1;
        layout: horizontal;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close"),
        Binding("p", "print", "Print Again"),
        Binding("f", "generate_pdf", "PDF Invoice"),
    ]

    def __init__(self, receipt_text: str, sale_id: int, sale_data: dict = None):
        super().__init__()
        self.receipt_text = receipt_text
        self.sale_id = sale_id
        self.sale_data = sale_data  # Contains items, customer_info, payment_info

    def compose(self) -> ComposeResult:
        with Vertical(id="receipt-container"):
            yield Label("🧾 FISKALNI RAČUN", classes="label")
            yield Static(self.receipt_text, id="receipt-display")

            with Horizontal(id="close-button-container"):
                yield Button("Zatvori \\[Enter/ESC]", id="close-btn", variant="success")
                yield Button("Štampaj ponovo \\[P]", id="print-btn", variant="primary")
                yield Button("PDF Faktura \\[F]", id="pdf-btn", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.action_close()
        elif event.button.id == "print-btn":
            self.action_print()
        elif event.button.id == "pdf-btn":
            self.action_generate_pdf()

    def action_close(self) -> None:
        """Close receipt viewer"""
        self.dismiss()

    def action_print(self) -> None:
        """Print receipt again (future: send to printer)"""
        self.notify("Račun bi bio odštampan (u izradi)", severity="information")

    def action_generate_pdf(self) -> None:
        """Generate PDF invoice"""
        if not self.sale_data:
            self.notify("Podaci o prodaji nisu dostupni za PDF", severity="error")
            return

        items = self.sale_data.get('items')
        customer_info = self.sale_data.get('customer_info')
        payment_info = self.sale_data.get('payment_info')

        if not items:
            self.notify("Nema artikala za fakturu", severity="error")
            return

        try:
            from pdf_invoice import PDFInvoiceGenerator

            generator = PDFInvoiceGenerator()
            filepath = generator.generate_invoice(
                sale_id=self.sale_id,
                items=items,
                payment_info=payment_info or {},
                customer_info=customer_info,
                timestamp=self.sale_data.get('timestamp')
            )

            # Open the generated PDF
            generator.open_pdf(filepath)

            self.notify(f"PDF faktura kreirana: {filepath}", severity="success")

        except ImportError:
            self.notify("Modul za PDF nije instaliran (reportlab)", severity="error")
        except Exception as e:
            self.notify(f"Greška pri generisanju PDF-a: {str(e)}", severity="error")


class QuantityInputScreen(Screen):
    """Screen to input quantity for adding items to cart"""

    CSS = """
    QuantityInputScreen {
        align: center middle;
    }

    #quantity-dialog {
        width: 40;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    #item-info {
        padding: 1;
        background: $panel;
        margin-bottom: 1;
    }

    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
        # Binding("delete", "delete_item", "Delete")
    ]

    def __init__(self, item: dict, current_quantity: float = 1.0, edit_mode: bool = False):
        super().__init__()
        self.item = item
        self.quantity = current_quantity
        self.edit_mode = edit_mode

    def compose(self) -> ComposeResult:
        with Vertical(id="quantity-dialog"):
            # Different title based on mode
            if self.edit_mode:
                yield Label("✏️  IZMENA KOLIČINE", classes="label")
            else:
                yield Label("📦 KOLIČINA", classes="label")
            yield Label(
                f"Artikal: {self.item['item']}\nCena: {self.item['price']:.2f} RSD",
                id="item-info"
            )
            yield Input(
                placeholder="Količina...",
                id="quantity-input",
                type="number",
                value=str(self.quantity) # Pre-fill with current quantity
            )

            with Horizontal(id="buttons"):
                yield Button("Potvrdi \\[Enter]", id="confirm-btn", variant="success")
                # if self.edit_mode:
                #  yield Button("Obriši [Del]", id="delete-btn", variant="error")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Focus and select the input"""
        qty_input = self.query_one("#quantity-input", Input)
        qty_input.focus()
        # Select all text so user can just start typing

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.action_confirm()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input field"""
        if event.input.id == "quantity-input":
            self.action_confirm()

    def action_confirm(self) -> None:
        """Confirm quantity"""
        qty_input = self.query_one("#quantity-input", Input)
        try:
            quantity = float(qty_input.value)
            if quantity <= 0:
                self.notify("Količina mora biti veća od 0!", severity="error")
                return

            self.dismiss(quantity)
        except ValueError:
            self.notify("Unesite ispravnu količinu!", severity="error")

    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)


class POSApp(App):
    """Main POS Application"""

    CSS = """
    Screen {
        background: $surface;
    }

    Header {
        background: $primary;
    }
    
    #user-info {
        dock: top;
        height: 1;
        background: $accent;
        color: $text;
        content-align: right middle;
        padding: 0 2;
    }

    #low-stock-banner {
        dock: top;
        height: 1;
        background: $accent;
        width: 140;
        color: $text;
        content-align: right middle;
        padding: 0 2;
    }

    #low-stock-banner.hidden {
        display: none;
    }

    #main-container {
        layout: horizontal;
        height: 1fr;
    }

    #inventory-panel {
        width: 3fr;
        border: solid $primary;
        padding: 1;
    }

    #cart-panel {
        width: 2fr;
        border: solid $accent;
        padding: 1;
    }

    #controls {
        dock: bottom;
        height: auto;
        background: $panel;
        padding: 1;
        layout: horizontal;
    }

    Button {
        margin: 0 1;
    }

    DataTable {
        height: 1fr;
    }

    Input {
        margin-bottom: 1;
    }

    .label {
        padding: 1 0;
        text-style: bold;
        color: $accent;
    }

    #total-label {
        padding: 1;
        text-style: bold;
        background: $success;
        color: $text;
        text-align: center;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f1", "show_help", "Pomoć", show=True),
        Binding("f2", "sales", "Prodaja", show=True),
        Binding("f3", "inventory", "Inventar", show=True),
        Binding("f4", "reports", "Izveštaji", show=True),
        Binding("f5", "checkout", "Naplati", show=True),
        Binding("f6", "otpremnice", "Otpremnice", show=True),
        Binding("f7", "sales_history", "Prethodni računi", show=True),
        Binding("f8", "user_management", "Korisnici", show=True),
        Binding("f9", "logout", "Izlaz", show=True),
        Binding("f10", "customers", "Kupci", show=True),
        Binding("c", "clear_cart", "Očisti korpu"),
        Binding("enter", "add_selected", "Ubaci u korpu"),
        Binding("-", "remove_selected", "Izbaci artikal"),
        Binding("e", "edit_quantity", "Izmeni količinu"),
        Binding("l", "last_sale", "Poslednja prodaja"),
        Binding("d", "duplicate_sale", "Ponovi prodaju"),
    ]

    def __init__(self):
        super().__init__()

        # Initialize backend
        db = Database("data.db")
        inv_repo = InventoryRepository(db)
        sales_repo = SalesRepository(db)
        user_repo = UserRepository(db)
        refund_repo = RefundRepository(db)
        customer_repo = CustomerRepository(db)
        unified_sales_repo = UnifiedSalesRepository(db)
        invoice_repo = InvoiceRepository(db)

        # Restaurant mode repositories
        table_repo = TableRepository(db)
        session_repo = TableSessionRepository(db)
        order_repo = TableOrderRepository(db)

        # Category repository
        category_repo = CategoryRepository(db)

        self.pos = POSService(
            inv_repo,
            sales_repo,
            invoice_repo,
            customer_repo,
            unified_sales_repo
        )

        self.reports = ReportService(inv_repo, sales_repo)
        self.daily_reports = DailyReportService(
            sales_repo, None, inv_repo, unified_sales_repo
        )
        self.user_service = UserService(user_repo)
        self.refund_service = RefundService(sales_repo, inv_repo, refund_repo)
        self.customer_repo = customer_repo
        self.unified_sales = unified_sales_repo  # Store for direct access if needed
        self.invoice_repo = invoice_repo  # Store for otpremnice screen

        # Restaurant mode service
        self.table_service = TableService(table_repo, session_repo, order_repo, inv_repo)

        # Category service
        self.category_service = CategoryService(category_repo, inv_repo)

        # Current logged in user
        self.current_user = None

        # Shopping cart
        self.cart = []
        self.cart_total = 0.0

        # Store last cart for duplicate sale feature
        self.last_cart = []

        # Store last selected category for restaurant mode
        self.last_category_id = None

        # Store mode flag (set after login based on config)
        self.is_shop_mode = False

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Static("", id="user-info")  # Shows logged-in user
        yield Static("", id="low-stock-banner")

        # Main container with horizontal layout
        with Horizontal(id="main-container"):
            # Left panel - Inventory
            with Vertical(id="inventory-panel"):
                yield Label("📦 INVENTAR", classes="label")
                yield Input(placeholder="Pretraga ili skeniranje...", id="search-input")
                yield DataTable(id="inventory-table", zebra_stripes=True)

            # Right panel - Shopping Cart
            with Vertical(id="cart-panel"):
                yield Label("🛒 KORPA (0)", classes="label", id="cart-label")
                yield DataTable(id="cart-table", zebra_stripes=True, cursor_type="row")
                yield Static("UKUPNO: 0.00 RSD", id="total-label")

        # Bottom controls
        with Horizontal(id="controls"):
            yield Button("Dodaj u korpu \\[Enter]", id="add-to-cart", variant="primary")
            yield Button("Ukloni \\[-]", id="remove-from-cart", variant="error")
            yield Button("Naplati \\[F5]", id="checkout", variant="success")
            yield Button("Očisti \\[C]", id="clear-cart")

        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts"""
        # Show login screen first
        self.push_screen(LoginScreen(self.user_service), self.handle_login)

    def update_user_info_bar(self) -> None:
        """Update user info bar with today's sales total"""
        if not self.current_user:
            return

        user_info = self.query_one("#user-info", Static)

        # Get today's sales total directly from DB
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        today_total = 0.0

        try:
            # Get today's sales directly
            today_sales = self.unified_sales.get_sales_by_date(today)
            today_total = sum(s.get('total_amount', 0) for s in today_sales)
        except Exception:
            pass  # If query fails, just show 0

        user_info.update(
            f"👤 {self.current_user['full_name']} ({self.current_user['role'].upper()}) | "
            f"💰 Danas: {today_total:,.0f} RSD | F9: Odjava"
        )

    def update_low_stock_banner(self) -> None:
        """Update low stock warning banner"""
        if CONFIG['show_low_stock_banner']:
            low_stock_items = self.reports.low_stock_report(CONFIG["low_stock_threshold"])

            banner = self.query_one("#low-stock-banner", Static)

            if low_stock_items:
                count = len(low_stock_items)
                # Show first 3 items
                items_preview = ", ".join([item['item'] for item in low_stock_items[:3]])
                if count > 3:
                    items_preview += f" (+{count - 3} više)"

                banner.update(f"🟡  NISKO STANJE ({count}): {items_preview}")
                banner.remove_class("hidden")
            else:
                banner.add_class("hidden")

    def open_main_screen(self, screen, callback=None) -> None:
        """Open a main screen, dismissing any existing main screen first.

        This prevents main screens from stacking on top of each other.
        Only the POS (sales) screen and ONE main screen should ever be on the stack.
        """
        # Dismiss all screens except the base screen (POS sales screen)
        # The screen stack looks like: [base_screen, possibly_main_screen, possibly_sub_screens...]
        # We want to get back to just [base_screen] before pushing the new main screen
        while len(self.screen_stack) > 1:
            self.pop_screen()

        # Now push the new main screen
        if callback:
            self.push_screen(screen, callback)
        else:
            self.push_screen(screen)

    def action_user_management(self) -> None:
        """F8 - User Management (admin only)"""
        if not self.require_admin("Upravljanje korisnicima"):
            return

        screen = UserManagementScreen(self.user_service)
        if self.is_shop_mode:
            self.open_main_screen(screen)
        else:
            self.push_screen(screen)

    def action_customers(self) -> None:
        """F10 - Customer management (admin only)"""
        if not self.require_admin("Upravljanje kupcima"):
            return

        screen = CustomerManagementScreen(self.customer_repo)
        if self.is_shop_mode:
            self.open_main_screen(screen)
        else:
            self.push_screen(screen)

    def action_sales_history(self):
        """F7 - Sales history view"""
        if self.is_shop_mode:
            self.open_main_screen(
                SalesHistoryScreen(self.unified_sales, self.refund_service, self.current_user)
            )
        else:
            # In restaurant mode, just push on top of current screen
            self.push_screen(
                SalesHistoryScreen(self.unified_sales, self.refund_service, self.current_user)
            )

    def action_otpremnice(self) -> None:
        """F6 - Otpremnice management (admin only)"""
        if not self.require_admin("Otpremnice"):
            return

        screen = OtpremniceScreen(self.pos, self.invoice_repo)
        if self.is_shop_mode:
            self.open_main_screen(screen)
        else:
            self.push_screen(screen)

    def handle_login(self, user: dict) -> None:
        """Handle successful login"""
        if user:
            self.current_user = user

            # Refresh footer to show role-appropriate bindings
            self.refresh_bindings()

            # Update user info bar with today's sales
            self.update_user_info_bar()

            # Update header or show welcome message
            self.notify(
                f"✅ Prijavljeni kao: {user['full_name']} ({user['role']})",
                severity="information",
                timeout=5
            )

            # Route based on store type
            store_type = STORE_CONFIG.get("store_type", "shop")

            if store_type == "restaurant":
                # Restaurant mode - show table grid
                self.is_shop_mode = False
                self.push_screen(RestaurantScreen())
            else:
                # Shop mode - setup sales interface
                self.is_shop_mode = True
                self._setup_shop_mode()
        else:
            # Login failed or cancelled - quit app
            self.exit()

    def _setup_shop_mode(self) -> None:
        """Setup shop mode interface after login"""
        # Setup tables
        inv_table = self.query_one("#inventory-table", DataTable)
        inv_table.add_columns("ID", "Artikal", "Barkod", "Cena", "Stanje")
        inv_table.cursor_type = "row"

        cart_table = self.query_one("#cart-table", DataTable)
        cart_table.add_columns("Artikal", "Količina", "Cena", "Ukupno")

        # Load inventory
        self.load_inventory()

        # Focus search input
        self.query_one("#search-input", Input).focus()

        # Update low stock banner
        self.update_low_stock_banner()

    def is_admin(self) -> bool:
        """Check if current user is admin"""
        return self.current_user and self.current_user['role'] == 'admin'

    def require_admin(self, action_name: str = "Ova akcija") -> bool:
        """Check admin permission and show error if not admin"""
        if not self.is_admin():
            self.notify(
                f"{action_name} je dostupna samo administratorima!",
                severity="error"
            )
            return False
        return True

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Control action/binding visibility based on user role.

        Returns False to hide the binding from footer.
        Returns True or None to show it.
        """
        # Admin-only actions - hide from footer for non-admins
        admin_only_actions = {"otpremnice", "user_management", "customers", "inventory"}

        if action in admin_only_actions:
            return self.is_admin()

        # Shop-only actions - hide in restaurant mode
        shop_only_actions = {"last_sale", "duplicate_sale"}
        if action in shop_only_actions:
            return self.is_shop_mode

        return True

    def action_logout(self) -> None:
        """F9 - Logout current user (with confirmation)"""
        def do_logout(confirmed):
            if not confirmed:
                return

            # Clear cart before logout for security
            self.cart = []
            self.cart_total = 0.0

            # Clear current user
            self.current_user = None

            # Refresh footer to hide admin-only bindings
            self.refresh_bindings()

            # Pop all screens back to base to prevent restricted screens from remaining
            # This fixes the bug where admin logs out on Users screen and cashier still sees it
            while len(self.screen_stack) > 1:
                self.pop_screen()

            # Reset cart display
            self.update_cart_display()

            # Clear user info bar
            user_info = self.query_one("#user-info", Static)
            user_info.update("")

            # Show login screen again
            self.push_screen(LoginScreen(self.user_service), self.handle_login)

        # Show confirmation dialog
        self.push_screen(
            ConfirmDialog("Da li ste sigurni da želite da se odjavite?", "ODJAVA"),
            do_logout
        )

    def action_edit_quantity(self) -> None:
        """E - Edit quantity of selected cart item"""
        cart_table = self.query_one("#cart-table", DataTable)
        if cart_table.cursor_row is not None and self.cart:
            if cart_table.cursor_row < len(self.cart):
                cart_item = self.cart[cart_table.cursor_row]
                # Reuse QuantityInputScreen with edit_mode=True
                self.push_screen(
                    QuantityInputScreen(
                        item=cart_item,
                        current_quantity=cart_item['quantity'],
                        edit_mode=True  # ← Enable edit mode
                    ),
                    lambda new_qty: self.handle_edit_quantity(cart_table.cursor_row, new_qty)
                )
        else:
            self.notify("Korpa je prazna!", severity="warning")

    def handle_edit_quantity(self, cart_index: int, new_quantity: float) -> None:
        """Handle edited quantity"""
        if new_quantity is None:
            # Cancelled
            return

        if new_quantity == 0:
            # Delete item
            if cart_index < len(self.cart):
                removed_item = self.cart[cart_index]
                del self.cart[cart_index]
                self.update_cart_display()
                self.notify(f"Uklonjeno: {removed_item['item']}", severity="warning")
        else:
            # Update quantity
            if cart_index < len(self.cart):
                old_qty = self.cart[cart_index]['quantity']
                self.cart[cart_index]['quantity'] = new_quantity
                self.update_cart_display()
                self.notify(
                    f"Ažurirano: {self.cart[cart_index]['item']} "
                    f"({old_qty:.2f} → {new_quantity:.2f})"
                )

    def load_inventory(self, search_term: str = None) -> None:
        """Load inventory items"""
        table = self.query_one("#inventory-table", DataTable)
        table.clear()
        
        # If no search_term provided, get it from the input field
        if search_term is None:
            search_input = self.query_one("#search-input", Input)
            search_term = search_input.value.strip() if search_input else ""
        
        items = self.app.pos.search_inventory(search_term)
        for item in items:
            vat_rate = item.get('vat_rate', 0.20)
            vat_percent = int(vat_rate * 100)

            # Add warning indicator for low stock
            stock_display = f"{item['quantity']:.2f}"
            if item['quantity'] <= 0:
                stock_display = f"{stock_display:<10}{'⛔':>2}"
            elif item['quantity'] < CONFIG['low_stock_threshold']:
                stock_display = f"{stock_display:<10}{'🟡':>2}"

            table.add_row(
                str(item['id']),
                item['item'],
                item['barcode'] or "",
                f"{item['price']:.2f}",
                stock_display
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Live search as user types"""
        if event.input.id == "search-input":
            # Only handle if we're in shop mode
            if not self.is_shop_mode:
                return

            search_term = event.value.strip()

            # Try as barcode first (only if looks like complete barcode)
            if len(search_term) > 8:  # Barcodes are usually longer
                item = self.pos.find_item_by_barcode(search_term)
                if item:
                    # Don't add yet - wait for Enter
                    # Just show it in the list
                    self.load_inventory(search_term)
                    return

            # Live search by name
            self.load_inventory(search_term)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in search box"""
        if event.input.id == "search-input":
            # Only handle if we're in shop mode
            if not self.is_shop_mode:
                return

            inv_table = self.query_one("#inventory-table", DataTable)
            search_term = event.value.strip()

            if search_term:
                # Try as barcode first
                item = self.pos.find_item_by_barcode(search_term)
                if item:
                    # Barcode found - add to cart instantly!
                    self.add_item_to_cart(item, 1.0)
                    event.input.value = ""
                    return

                # Not a barcode - add first item from filtered list
                if inv_table.row_count > 0:
                    # Get first row
                    row = inv_table.get_row_at(0)
                    item_id = int(row[0])
                    item = self.pos.get_inventory_item(item_id)
                    if item:
                        self.push_screen(
                            QuantityInputScreen(item),
                            lambda qty: self.handle_quantity_input(item, qty, clear_search=True)
                        )
            else:
                # Empty search - just reload all
                self.load_inventory()

    def add_item_to_cart(self, item: dict, quantity: float = 1.0) -> None:
        """Add item to shopping cart"""
        # Check for low stock warning
        remaining_stock = item['quantity'] - quantity

        if remaining_stock < 0 and CONFIG["allow_oversell"]:
            # Ask for confirmation with callback
            self.push_screen(
                ConfirmDialog(
                    f"Količina ide u minus ({remaining_stock:.1f})!\n"
                    f"Artikal: {item['item']}\n"
                    f"Na stanju: {item['quantity']:.1f}\n"
                    f"Traženo: {quantity:.1f}\n\n"
                    f"Da li ste sigurni?",
                    "UPOZORENJE - NEMA DOVOLJNO ZALIHA"
                ),
                lambda confirmed: self.handle_oversell_confirmation(confirmed, item, quantity)
            )
            return  # ← Stop here, callback will handle the rest
        elif remaining_stock < 0 and not CONFIG["allow_oversell"]:
            self.handle_oversell_confirmation(False, item, 999)
            return

        # Normal flow - no confirmation needed
        self.actually_add_to_cart(item, quantity)

    def handle_oversell_confirmation(self, confirmed: bool, item: dict, quantity: float) -> None:
        """Handle the result of oversell confirmation"""
        if confirmed:
            # User said yes - add anyway
            self.actually_add_to_cart(item, quantity)
        else:
            if quantity == 999:
                self.notify("Nije dozvoljena prodaja u minusu!", severity="error")
            # User said no - just notify and do nothing
            self.notify("Dodavanje otkazano", severity="warning")
    
    def actually_add_to_cart(self, item: dict, quantity: float) -> None:
        """Actually add item to cart (after any confirmations)"""
        # Check if item already in cart
        for cart_item in self.cart:
            if cart_item['id'] == item['id']:
                cart_item['quantity'] += quantity
                break
        else:
            # New item
            self.cart.append({
                'id': item['id'],
                'item': item['item'],
                'price': item['price'],
                'quantity': quantity,
                'vat_rate': item.get('vat_rate', 0.20)
            })
        
        self.update_cart_display()
        
        # Check for low stock warning
        remaining_stock = item['quantity'] - quantity
        
        if remaining_stock <= 0:
            self.notify(
                f"🟡  {item['item']}: NEMA NA STANJU! (Ostalo: {remaining_stock:.1f})",
                severity="error",
                timeout=5
            )
        elif remaining_stock < CONFIG["low_stock_threshold"]:
            self.notify(
                f"🟡  {item['item']}: Nisko stanje! (Ostalo: {remaining_stock:.1f} kom)",
                severity="warning",
                timeout=5
            )
        else:
            self.notify(f"Dodato: {quantity}x {item['item']}")

        
    def update_cart_display(self) -> None:
        """Refresh cart table and total"""
        cart_table = self.query_one("#cart-table", DataTable)
        cart_table.clear()

        total = 0.0
        item_count = 0
        for item in self.cart:
            line_total = item['price'] * item['quantity']
            total += line_total
            item_count += int(item['quantity'])

            cart_table.add_row(
                item['item'],
                f"{item['quantity']:.2f}",
                f"{item['price']:.2f}",
                f"{line_total:.2f}"
            )

        self.cart_total = total

        # Update cart label with item count
        cart_label = self.query_one("#cart-label", Label)
        cart_label.update(f"🛒 KORPA ({item_count})")

        total_label = self.query_one("#total-label", Static)
        total_label.update(f"UKUPNO: {total:.2f} RSD")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in tables (Enter key or click)"""
        # Check if we're on modal/subscreen - if so, don't hande
        if len(self.screen_stack) > 1:
            return # We're in a modal, let it handle its own events

        if event.data_table.id == "inventory-table":
            # User selected an item from inventory
            row = event.data_table.get_row_at(event.cursor_row)
            item_id = int(row[0])
            item = self.pos.get_inventory_item(item_id)
            if item:
                self.push_screen(
                    QuantityInputScreen(item),
                    lambda qty: self.handle_quantity_input(item, qty)
                )

        elif event.data_table.id == "cart-table":
            # User selected item from cart - open edit dialog
            if event.cursor_row < len(self.cart):
                cart_item = self.cart[event.cursor_row]
                self.push_screen(
                    QuantityInputScreen(
                        item=cart_item,
                        current_quantity=cart_item['quantity'],
                        edit_mode=True
                    ),
                    lambda new_qty: self.handle_edit_quantity(event.cursor_row, new_qty)
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "add-to-cart":
            # Get selected item from inventory
            inv_table = self.query_one("#inventory-table", DataTable)
            if inv_table.cursor_row is not None:
                row = inv_table.get_row_at(inv_table.cursor_row)
                item_id = int(row[0])
                item = self.pos.get_inventory_item(item_id)
                if item:
                    self.push_screen(QuantityInputScreen(item), lambda qty: self.handle_quantity_input(item, qty))

        elif event.button.id == "remove-from-cart":
            cart_table = self.query_one("#cart-table", DataTable)
            if cart_table.cursor_row is not None and self.cart:
                del self.cart[cart_table.cursor_row]
                self.update_cart_display()

        elif event.button.id == "clear-cart":
            self.cart = []
            self.update_cart_display()

        elif event.button.id == "checkout":
            if self.cart:
                self.push_screen(PaymentScreen(self.cart_total, self.customer_repo), self.handle_checkout)
            else:
                self.notify("Korpa je prazna!", severity="warning")

    def handle_quantity_input(self, item: dict, quantity: float, clear_search: bool = False) -> None:
        """Handle quantity input result"""
        if quantity:
            self.add_item_to_cart(item, quantity)
            # Refocus search input for next scan
            search_input = self.query_one("#search-input", Input)
            if clear_search:
                search_input.value = ""
            search_input.focus()
        else:
            # Cancelled
            self.query_one("#search-input", Input).focus()

    def handle_checkout(self, payment_info: PaymentInfo) -> None:
        """Handle completed payment"""
        if not payment_info:
            self.notify("Plaćanje otkazano", severity="warning")
            return

        # Process entire cart as one transaction
        try:
            result = self.pos.sell_items(
                items=self.cart,
                payment_info=payment_info,
                allow_oversell=CONFIG["allow_oversell"]
            )

            if not result.success:
                self.notify(f"Greška: {result.message}", severity="error")
                return

            last_sale_id = result.sale_id

            # Get the receipt that was generated
            if last_sale_id:
                # Use unified sales to get receipt (receipt_text is in sales table now)
                sale_record = self.unified_sales.get_by_id(last_sale_id)

                if sale_record and sale_record.get('receipt_text'):
                    # Prepare sale_data for PDF generation
                    from datetime import datetime
                    sale_data = {
                        'items': result.sale_items,
                        'customer_info': result.customer_info,
                        'payment_info': {
                            'payment_type': payment_info.payment_type,
                            'cash_amount': payment_info.cash_amount,
                            'card_amount': payment_info.card_amount,
                            'amount_tendered': payment_info.amount_tendered,
                            'change_given': payment_info.change_given,
                        },
                        'timestamp': datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                    }

                    # Show receipt viewer with sale_data for PDF
                    self.push_screen(
                        ReceiptViewerScreen(
                            sale_record['receipt_text'],
                            last_sale_id,
                            sale_data
                        ),
                        self.after_receipt_shown
                    )
                else:
                    # Fallback if no receipt found
                    self.after_receipt_shown()
            else:
                self.after_receipt_shown()

        except Exception as e:
            self.notify(f"Greška pri prodaji: {str(e)}", severity="error")

    def after_receipt_shown(self, result=None) -> None:
        """Called after receipt is closed"""
        # Success message
        self.notify(f"✅ Prodaja uspešna! Ukupno: {self.cart_total:.2f} RSD", severity="success")

        # Save cart for duplicate sale feature before clearing
        self.last_cart = list(self.cart)

        # Clear cart and reload inventory
        self.cart = []
        self.update_cart_display()
        self.load_inventory()

        # Update low stock banner
        self.update_low_stock_banner()

        # Update today's sales in header
        self.update_user_info_bar()

        # Focus search for next sale
        self.query_one("#search-input", Input).focus()

    def action_last_sale(self) -> None:
        """L - Show last sale preview"""
        if not self.is_shop_mode:
            return

        # Get the most recent sale
        try:
            recent_sales = self.unified_sales.get_recent_sales(limit=1)
            if not recent_sales:
                self.notify("Nema prethodnih prodaja", severity="warning")
                return

            last_sale = recent_sales[0]
            sale_id = last_sale['id']

            # Get full sale with items
            sale_with_items = self.unified_sales.get_sale_with_items(sale_id)
            if not sale_with_items:
                self.notify("Greška pri učitavanju prodaje", severity="error")
                return

            sale = sale_with_items['sale']
            items = sale_with_items['items']

            # Build preview text
            lines = [
                f"POSLEDNJA PRODAJA #{sale_id}",
                f"Vreme: {sale['timestamp']}",
                "-" * 30,
            ]

            for item in items:
                lines.append(f"{item['item_name']} x{item['quantity']} = {item['line_total']:.2f}")

            lines.extend([
                "-" * 30,
                f"UKUPNO: {sale['total_amount']:.2f} RSD",
                f"Plaćanje: {sale['payment_type']}",
            ])

            # Show in a simple dialog
            self.push_screen(
                ConfirmDialog("\n".join(lines), "POSLEDNJA PRODAJA"),
                lambda x: None  # Dismiss handler does nothing
            )

        except Exception as e:
            self.notify(f"Greška: {str(e)}", severity="error")

    def action_duplicate_sale(self) -> None:
        """D - Duplicate last sale (reload last cart)"""
        if not self.is_shop_mode:
            return

        if not self.last_cart:
            self.notify("Nema prethodne prodaje za ponavljanje", severity="warning")
            return

        # Clear current cart and load last cart
        self.cart = []
        for item in self.last_cart:
            # Make a copy of each item to avoid reference issues
            self.cart.append(dict(item))

        self.update_cart_display()
        self.notify(f"Učitana prethodna prodaja ({len(self.cart)} stavki)", severity="information")

    def action_sales(self) -> None:
        """F2 - Sales screen"""
        self.notify("Prodaja - trenutni ekran")

    def action_inventory(self) -> None:
        """F3 - Inventory management (admin only)"""
        if not self.require_admin("Upravljanje inventarom"):
            return

        screen = InventoryManagementScreen(self.pos, self.category_service)
        if self.is_shop_mode:
            self.open_main_screen(screen)
        else:
            self.push_screen(screen)

    def action_reports(self) -> None:
        # Cashiers can see basic reports, admins see all
        """F4 - Reports"""
        screen = ReportsScreen(
            self.daily_reports,
            self.reports,
            self.is_admin()
        )
        if self.is_shop_mode:
            self.open_main_screen(screen)
        else:
            self.push_screen(screen) 

    def action_show_help(self) -> None:
        """F1 - Show help"""
        self.notify(
            "F2: Prodaja | F3: Inventar | F4: Izveštaji | Q: Izlaz",
            severity="information"
        )

    def action_checkout(self) -> None:
        """F5 - Checkout"""
        if self.cart:
            self.push_screen(
                PaymentScreen(self.cart_total, self.customer_repo),
                self.handle_checkout
            )
        else:
            self.notify("Korpa je prazna!", severity="warning")

    def action_clear_cart(self) -> None:
        """C - Clear cart"""
        self.cart = []
        self.update_cart_display()
        self.notify("Korpa očišćena")

    def action_add_selected(self) -> None:
        """Enter - Add selected item to cart"""
        inv_table = self.query_one("#inventory-table", DataTable)
        if inv_table.cursor_row is not None:
            row = inv_table.get_row_at(inv_table.cursor_row)
            item_id = int(row[0])
            item = self.pos.get_inventory_item(item_id)
            if item:
                self.push_screen(QuantityInputScreen(item), lambda qty: self.handle_quantity_input(item, qty))

    def action_remove_selected(self) -> None:
        """- - Remove selected item from cart"""
        cart_table = self.query_one("#cart-table", DataTable)
        if cart_table.cursor_row is not None and self.cart:
            removed = self.cart[cart_table.cursor_row]
            del self.cart[cart_table.cursor_row]
            self.update_cart_display()
            self.notify(f"Uklonjeno: {removed['item']}")


class SalesHistoryScreen(Screen):
    """Screen for viewing sales history with split-panel layout"""

    CSS = """
        SalesHistoryScreen {
            background: $surface;
        }

        #sales-history-container {
            height: 100%;
            padding: 1;
        }

        #date-section {
            height: auto;
            background: $panel;
            padding: 1;
            margin-bottom: 1;
        }

        #date-row {
            layout: horizontal;
            height: auto;
        }

        #panels-container {
            height: 1fr;
            layout: horizontal;
        }

        #left-panel {
            width: 30%;
            border: solid $primary;
            margin-right: 1;
        }

        #right-panel {
            width: 70%;
            border: solid $secondary;
        }

        #receipts-table {
            height: 100%;
        }

        #items-table {
            height: 100%;
        }

        #controls {
            dock: bottom;
            height: auto;
            layout: horizontal;
            background: $panel;
            padding: 1;
        }

        .panel-header {
            background: $primary;
            color: $text;
            padding: 0 1;
            text-style: bold;
        }
    """

    BINDINGS = [
        Binding("escape", "close", "Zatvori"),
        Binding("f2", "close", "Main", show=True),
        Binding("r", "refund", "Povraćaj"),
        Binding("p", "print_receipt", "Štampaj"),
        Binding("tab", "switch_panel", "Promeni panel"),
    ]

    def __init__(self, unified_sales_repo, refund_service=None, current_user=None):
        super().__init__()
        self.unified_sales = unified_sales_repo
        self.refund_service = refund_service
        self.current_user = current_user
        self.selected_sale_id = None
        self.current_sales = []

    def compose(self) -> ComposeResult:
        with Vertical(id="sales-history-container"):
            yield Label("📋 PREGLED PRODAJE", classes="label")

            with Vertical(id="date-section"):
                yield Label("Pretraga prodaje:")
                with Horizontal(id="date-row"):
                    yield Input(
                        placeholder="Datum (YYYY-MM-DD) ili Enter za danas",
                        id="date-input"
                    )
                    yield Button("Pretraži", id="search-btn", variant="primary")

            with Horizontal(id="panels-container"):
                with Vertical(id="left-panel"):
                    yield Static("Računi", classes="panel-header")
                    yield DataTable(id="receipts-table")

                with Vertical(id="right-panel"):
                    yield Static("Stavke računa", classes="panel-header", id="items-header")
                    yield DataTable(id="items-table")

            with Horizontal(id="controls"):
                yield Button("Povraćaj \\[R]", id="refund-btn", variant="warning")
                yield Button("Štampaj \\[P]", id="print-btn", variant="default")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        """Setup tables and load today's sales"""
        from datetime import datetime

        # Setup receipts table (left panel)
        receipts_table = self.query_one("#receipts-table", DataTable)
        receipts_table.add_columns("Račun", "Vreme", "Ukupno")
        receipts_table.cursor_type = "row"

        # Setup items table (right panel)
        items_table = self.query_one("#items-table", DataTable)
        items_table.add_columns("Artikal", "Kol.", "Cena", "Ukupno")
        items_table.cursor_type = "row"

        # Load today's sales
        today = datetime.now().strftime("%Y-%m-%d")
        self.query_one("#date-input", Input).value = today
        self.load_sales(today)

    def load_sales(self, date: str) -> None:
        """Load sales for the given date"""
        receipts_table = self.query_one("#receipts-table", DataTable)
        receipts_table.clear()

        try:
            self.current_sales = self.unified_sales.get_sales_with_items_by_date(date)

            if not self.current_sales:
                self.notify("Nema prodaje za ovaj datum", severity="warning")
                self.clear_items_table()
                return

            for sale_data in self.current_sales:
                sale = sale_data['sale']
                time_str = sale['created_at'].split()[1][:5] if sale['created_at'] else ""
                receipts_table.add_row(
                    f"#{sale['receipt_number']}",
                    time_str,
                    f"{sale['total_amount']:.2f}",
                    key=str(sale['id'])
                )

            # Select first row
            if self.current_sales:
                receipts_table.move_cursor(row=0)
                self.show_sale_items(self.current_sales[0])

        except Exception as e:
            self.notify(f"Greška: {e}", severity="error")

    def show_sale_items(self, sale_data: dict) -> None:
        """Display items for the selected sale"""
        items_table = self.query_one("#items-table", DataTable)
        items_table.clear()

        sale = sale_data['sale']
        items = sale_data['items']

        self.selected_sale_id = sale['id']

        # Update header
        header = self.query_one("#items-header", Static)
        header.update(f"Stavke računa #{sale['receipt_number']}")

        for item in items:
            items_table.add_row(
                item['item'],
                f"{item['quantity']:.2f}",
                f"{item['item_price']:.2f}",
                f"{item['total']:.2f}"
            )

    def clear_items_table(self) -> None:
        """Clear the items table"""
        items_table = self.query_one("#items-table", DataTable)
        items_table.clear()
        self.selected_sale_id = None

        header = self.query_one("#items-header", Static)
        header.update("Stavke računa")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in receipts table"""
        if event.data_table.id == "receipts-table":
            # Find the sale data for this row
            row_key = event.row_key.value if event.row_key else None
            if row_key:
                for sale_data in self.current_sales:
                    if str(sale_data['sale']['id']) == row_key:
                        self.show_sale_items(sale_data)
                        break

    def on_data_table_cursor_changed(self, event) -> None:
        """Handle cursor change in receipts table"""
        table = event.data_table
        if table.id == "receipts-table" and table.row_count > 0:
            row_key = table.get_row_at(table.cursor_row)
            # Get the key from the row
            try:
                keys = list(table._row_locations.keys())
                if table.cursor_row < len(keys):
                    row_key_obj = keys[table.cursor_row]
                    sale_id = row_key_obj.value if hasattr(row_key_obj, 'value') else str(row_key_obj)
                    for sale_data in self.current_sales:
                        if str(sale_data['sale']['id']) == sale_id:
                            self.show_sale_items(sale_data)
                            break
            except:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search-btn":
            date = self.query_one("#date-input", Input).value.strip()
            if not date:
                from datetime import datetime
                date = datetime.now().strftime("%Y-%m-%d")
            self.load_sales(date)
        elif event.button.id == "close-btn":
            self.action_close()
        elif event.button.id == "refund-btn":
            self.action_refund()
        elif event.button.id == "print-btn":
            self.action_print_receipt()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in date input"""
        if event.input.id == "date-input":
            date = event.value.strip()
            if not date:
                from datetime import datetime
                date = datetime.now().strftime("%Y-%m-%d")
                event.input.value = date
            self.load_sales(date)

    def action_close(self) -> None:
        self.dismiss()

    def action_switch_panel(self) -> None:
        """Switch focus between panels"""
        receipts = self.query_one("#receipts-table", DataTable)
        items = self.query_one("#items-table", DataTable)

        if receipts.has_focus:
            items.focus()
        else:
            receipts.focus()

    def action_refund(self) -> None:
        """Process refund for selected sale"""
        if not self.selected_sale_id:
            self.notify("Izaberite račun za povraćaj", severity="warning")
            return

        # Open RefundSaleScreen for the selected sale
        self.app.push_screen(
            RefundSaleScreen(
                sale_id=self.selected_sale_id,
                unified_sales_repo=self.unified_sales,
                refund_service=self.refund_service,
                current_user=self.current_user
            ),
            self.handle_refund_result
        )

    def handle_refund_result(self, result) -> None:
        """Handle result from refund screen"""
        if result:
            # Reload sales to reflect any status changes
            date = self.query_one("#date-input", Input).value.strip()
            if date:
                self.load_sales(date)

    def action_print_receipt(self) -> None:
        """Print receipt for selected sale (reprint)"""
        if not self.selected_sale_id:
            self.notify("Izaberite račun za štampanje", severity="warning")
            return

        # Get sale with items
        sale_data = self.unified_sales.get_sale_with_items(self.selected_sale_id)
        if not sale_data:
            self.notify("Greška: Račun nije pronađen", severity="error")
            return

        sale = sale_data['sale']
        items = sale_data['items']

        # Get customer info if exists
        customer_info = None
        if sale.get('customer_id'):
            from pos_db_layer import CustomerRepository
            customer_repo = CustomerRepository(self.unified_sales.db)
            customer_info = customer_repo.get_by_id(sale['customer_id'])

        # Build receipt text - either from stored or regenerate
        # Add reprint header receipt
        reprint_header = [
            "=" * 40,
            "*** PONOVLJEN RAČUN ***".center(40),
            "=" * 40,
            ""
        ]
        if sale.get('receipt_text'):
            receipt_text = "\n".join(reprint_header) + sale['receipt_text']
        else:
            # Regenerate receipt if not stored
            from receipt_printer import FiscalReceipt
            from config import STORE_CONFIG

            printer = FiscalReceipt(STORE_CONFIG)
            printer.receipt_counter = sale['receipt_number']

            # Prepare items for receipt
            receipt_items = [{
                'item': item['item'],
                'price': item['item_price'],
                'quantity': item['quantity'],
                'vat_rate': item.get('vat_rate', 0.20)
            } for item in items]

            # Prepare payment info
            payment_info = {
                'payment_type': sale['payment_type'],
                'cash_amount': sale.get('cash_amount', 0),
                'card_amount': sale.get('card_amount', 0),
                'amount_tendered': sale.get('amount_tendered', 0),
                'change_given': sale.get('change_given', 0)
            }

            receipt_data = {
                'items': receipt_items,
                'payment_info': payment_info,
                'sale_id': sale['id'],
                'timestamp': sale['created_at'],
                'customer_info': customer_info
            }

            receipt_text = "\n".join(reprint_header) + printer.generate_receipt(receipt_data)

        # Prepare sale_data for ReceiptViewerScreen
        viewer_sale_data = {
            'items': items,
            'customer_info': customer_info,
            'payment_info': {
                'payment_type': sale['payment_type'],
                'cash_amount': sale.get('cash_amount', 0),
                'card_amount': sale.get('card_amount', 0),
                'amount_tendered': sale.get('amount_tendered', 0),
                'change_given': sale.get('change_given', 0)
            }
        }

        # Show receipt
        self.app.push_screen(
            ReceiptViewerScreen(receipt_text, sale['id'], viewer_sale_data)
        )


class RefundSaleScreen(Screen):
    """Screen for processing refunds from a specific sale/receipt"""

    CSS = """
        RefundSaleScreen {
            background: $surface;
        }

        #refund-sale-container {
            height: 100%;
            padding: 1;
        }

        #sale-header {
            height: auto;
            background: $primary;
            padding: 1;
            margin-bottom: 1;
        }

        #sale-header Static {
            color: $text;
        }

        #items-section {
            height: 1fr;
            border: solid $primary;
            margin-bottom: 1;
        }

        #items-table {
            height: 100%;
        }

        #controls {
            dock: bottom;
            height: auto;
            layout: horizontal;
            background: $panel;
            padding: 1;
        }

        #controls Button {
            margin-right: 1;
        }

        .refund-info {
            color: $warning;
            padding: 0 1;
        }
    """

    BINDINGS = [
        Binding("escape", "close", "Zatvori"),
        Binding("r", "refund_all", "Računa"),
        Binding("s", "refund_item", "Stavke"),
    ]

    def __init__(self, sale_id: int, unified_sales_repo, refund_service, current_user):
        super().__init__()
        self.sale_id = sale_id
        self.unified_sales = unified_sales_repo
        self.refund_service = refund_service
        self.current_user = current_user
        self.sale_data = None
        self.items_with_refunds = []

    def compose(self) -> ComposeResult:
        with Vertical(id="refund-sale-container"):
            yield Label("↩️  POVRAĆAJ RAČUNA", classes="label")

            with Vertical(id="sale-header"):
                yield Static("Učitavanje...", id="sale-info")

            with Vertical(id="items-section"):
                yield DataTable(id="items-table")

            with Horizontal(id="controls"):
                yield Button("Povraćaj računa \\[R]", id="refund-all-btn", variant="error")
                yield Button("Povraćaj stavke \\[S]", id="refund-item-btn", variant="warning")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        """Load sale data and setup table"""
        # Setup table
        table = self.query_one("#items-table", DataTable)
        table.add_columns("Artikal", "Prodato", "Vraćeno", "Dostupno", "Cena", "Ukupno")
        table.cursor_type = "row"

        # Load sale data
        self.load_sale_data()

    def load_sale_data(self) -> None:
        """Load the sale and its items with refund info"""
        self.sale_data = self.unified_sales.get_sale_with_items(self.sale_id)

        if not self.sale_data:
            self.notify("Račun nije pronađen!", severity="error")
            self.dismiss(None)
            return

        sale = self.sale_data['sale']
        items = self.sale_data['items']

        # Get existing refunds for this sale
        refunds = self.unified_sales.get_refunds_for_sale(self.sale_id)

        # Calculate refunded quantities per item
        refunded_by_item = {}
        for refund in refunds:
            item_name = refund['item']
            refunded_by_item[item_name] = refunded_by_item.get(item_name, 0) + refund['quantity']

        # Update header
        sale_info = self.query_one("#sale-info", Static)
        status_text = ""
        if sale['status'] == 'refunded':
            status_text = " [VRAĆEN]"
        elif sale['status'] == 'partial_refund':
            status_text = " [DELIMIČNO VRAĆEN]"

        sale_info.update(
            f"Račun #{sale['receipt_number']}{status_text}\n"
            f"Datum: {sale['created_at']}\n"
            f"Ukupno: {sale['total_amount']:.2f} RSD | "
            f"Plaćanje: {sale['payment_type']}"
        )

        # Populate table
        table = self.query_one("#items-table", DataTable)
        table.clear()

        self.items_with_refunds = []
        for item in items:
            refunded_qty = refunded_by_item.get(item['item'], 0)
            available_qty = item['quantity'] - refunded_qty

            self.items_with_refunds.append({
                'item': item['item'],
                'item_price': item['item_price'],
                'quantity_sold': item['quantity'],
                'quantity_refunded': refunded_qty,
                'quantity_available': available_qty,
                'total': item['total']
            })

            # Show refunded in table if any
            refund_display = f"{refunded_qty:.2f}" if refunded_qty > 0 else "-"
            available_display = f"{available_qty:.2f}" if available_qty > 0 else "0"

            table.add_row(
                item['item'],
                f"{item['quantity']:.2f}",
                refund_display,
                available_display,
                f"{item['item_price']:.2f}",
                f"{item['total']:.2f}"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refund-all-btn":
            self.action_refund_all()
        elif event.button.id == "refund-item-btn":
            self.action_refund_item()
        elif event.button.id == "close-btn":
            self.action_close()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_refund_all(self) -> None:
        """Refund entire receipt - all items with available quantity"""
        if not self.items_with_refunds:
            self.notify("Nema stavki za povraćaj!", severity="warning")
            return

        # Check if there's anything to refund
        has_available = any(item['quantity_available'] > 0 for item in self.items_with_refunds)
        if not has_available:
            self.notify("Sve stavke su već vraćene!", severity="warning")
            return

        # Show confirmation dialog
        self.app.push_screen(
            RefundConfirmScreen(
                items=self.items_with_refunds,
                refund_all=True,
                refund_service=self.refund_service,
                sale_id=self.sale_id,
                user_id=self.current_user['id'],
                unified_sales=self.unified_sales
            ),
            self.handle_refund_result
        )

    def action_refund_item(self) -> None:
        """Refund selected item"""
        table = self.query_one("#items-table", DataTable)

        if table.cursor_row is None or not self.items_with_refunds:
            self.notify("Izaberite stavku za povraćaj!", severity="warning")
            return

        if table.cursor_row >= len(self.items_with_refunds):
            self.notify("Neispravna stavka!", severity="error")
            return

        item = self.items_with_refunds[table.cursor_row]

        if item['quantity_available'] <= 0:
            self.notify(f"Stavka '{item['item']}' je već potpuno vraćena!", severity="warning")
            return

        # Open quantity input screen for single item
        self.app.push_screen(
            RefundItemQuantityScreen(
                item=item,
                refund_service=self.refund_service,
                sale_id=self.sale_id,
                user_id=self.current_user['id'],
                unified_sales=self.unified_sales
            ),
            self.handle_refund_result
        )

    def handle_refund_result(self, result) -> None:
        """Handle result from refund screens"""
        if result:
            self.notify("Povraćaj uspešno obrađen!", severity="information")
            # Reload data to show updated quantities
            self.load_sale_data()


class RefundItemQuantityScreen(Screen):
    """Screen for inputting refund quantity for a single item"""

    CSS = """
        RefundItemQuantityScreen {
            align: center middle;
        }

        #quantity-dialog {
            width: 60;
            height: auto;
            border: thick $warning;
            background: $surface;
            padding: 2;
        }

        #item-info {
            padding: 1;
            background: $panel;
            margin-bottom: 1;
        }

        .input-label {
            padding: 1 0 0 0;
        }

        Input {
            margin-bottom: 1;
        }

        #refund-method {
            layout: horizontal;
            height: auto;
            margin: 1 0;
        }

        #buttons {
            layout: horizontal;
            height: auto;
            margin-top: 1;
        }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Otkaži"),
    ]

    def __init__(self, item: dict, refund_service, sale_id: int, user_id: int, unified_sales):
        super().__init__()
        self.item = item
        self.refund_service = refund_service
        self.sale_id = sale_id
        self.user_id = user_id
        self.unified_sales = unified_sales
        self.refund_method = "cash"

    def compose(self) -> ComposeResult:
        with Vertical(id="quantity-dialog"):
            yield Label("↩️  POVRAĆAJ STAVKE", classes="label")

            yield Static(
                f"Artikal: {self.item['item']}\n"
                f"Prodato: {self.item['quantity_sold']:.2f} kom\n"
                f"Već vraćeno: {self.item['quantity_refunded']:.2f} kom\n"
                f"Dostupno za povraćaj: {self.item['quantity_available']:.2f} kom\n"
                f"Cena: {self.item['item_price']:.2f} RSD",
                id="item-info"
            )

            yield Label("Količina za povraćaj (1 - " + f"{self.item['quantity_available']:.2f}):", classes="input-label")
            yield Input(
                placeholder="Količina...",
                id="quantity-input",
                type="number",
                value=str(int(self.item['quantity_available']))
            )

            yield Label("Razlog povraćaja:", classes="input-label")
            yield Input(
                placeholder="Opciono - razlog povraćaja...",
                id="reason-input"
            )

            yield Label("Način povraćaja:", classes="input-label")
            with Horizontal(id="refund-method"):
                yield Button("Gotovina", id="cash-btn", variant="primary")
                yield Button("Kartica", id="card-btn", variant="default")

            with Horizontal(id="buttons"):
                yield Button("Izvrši povraćaj", id="process-btn", variant="warning")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="default")

    def on_mount(self) -> None:
        self.query_one("#quantity-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cash-btn":
            self.refund_method = "cash"
            event.button.variant = "primary"
            self.query_one("#card-btn", Button).variant = "default"
        elif event.button.id == "card-btn":
            self.refund_method = "card"
            event.button.variant = "primary"
            self.query_one("#cash-btn", Button).variant = "default"
        elif event.button.id == "process-btn":
            self.process_refund()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def process_refund(self) -> None:
        """Process the refund for this item"""
        quantity_str = self.query_one("#quantity-input", Input).value.strip()
        reason = self.query_one("#reason-input", Input).value.strip()

        if not quantity_str:
            self.notify("Unesite količinu!", severity="error")
            return

        try:
            quantity = float(quantity_str)

            if quantity <= 0:
                self.notify("Količina mora biti veća od 0!", severity="error")
                return

            if quantity > self.item['quantity_available']:
                self.notify(
                    f"Maksimalna količina za povraćaj je {self.item['quantity_available']:.2f}!",
                    severity="error"
                )
                return

            # Process refund
            success, message = self.refund_service.process_refund(
                sale_id=self.sale_id,
                item_name=self.item['item'],
                quantity=quantity,
                refund_method=self.refund_method,
                reason=reason,
                user_id=self.user_id
            )

            if success:
                # Update sale status
                self._update_sale_status()
                self.notify(message, severity="information")
                self.dismiss(True)
            else:
                self.notify(message, severity="error")

        except ValueError:
            self.notify("Neispravna količina!", severity="error")

    def _update_sale_status(self) -> None:
        """Update the sale status based on refund state"""
        # Get updated refund info
        refunds = self.unified_sales.get_refunds_for_sale(self.sale_id)
        sale_data = self.unified_sales.get_sale_with_items(self.sale_id)

        if not sale_data:
            return

        items = sale_data['items']

        # Calculate total sold and refunded
        total_sold = sum(item['quantity'] for item in items)
        total_refunded = sum(r['quantity'] for r in refunds)

        if total_refunded >= total_sold:
            self.unified_sales.update_status(self.sale_id, 'refunded')
        elif total_refunded > 0:
            self.unified_sales.update_status(self.sale_id, 'partial_refund')


class RefundConfirmScreen(Screen):
    """Screen for confirming full receipt refund"""

    CSS = """
        RefundConfirmScreen {
            align: center middle;
        }

        #confirm-dialog {
            width: 70;
            height: auto;
            border: thick $error;
            background: $surface;
            padding: 2;
        }

        #items-summary {
            height: auto;
            max-height: 15;
            overflow-y: auto;
            background: $panel;
            padding: 1;
            margin: 1 0;
        }

        #total-section {
            background: $warning 20%;
            padding: 1;
            margin: 1 0;
        }

        .input-label {
            padding: 1 0 0 0;
        }

        Input {
            margin-bottom: 1;
        }

        #refund-method {
            layout: horizontal;
            height: auto;
            margin: 1 0;
        }

        #buttons {
            layout: horizontal;
            height: auto;
            margin-top: 1;
        }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Otkaži"),
    ]

    def __init__(self, items: list, refund_all: bool, refund_service, sale_id: int, user_id: int, unified_sales):
        super().__init__()
        self.items = items
        self.refund_all = refund_all
        self.refund_service = refund_service
        self.sale_id = sale_id
        self.user_id = user_id
        self.unified_sales = unified_sales
        self.refund_method = "cash"

    def compose(self) -> ComposeResult:
        # Calculate totals
        refund_items = []
        total_refund = 0

        for item in self.items:
            if item['quantity_available'] > 0:
                refund_amount = item['quantity_available'] * item['item_price']
                total_refund += refund_amount
                refund_items.append(
                    f"  {item['item']}: {item['quantity_available']:.2f} x {item['item_price']:.2f} = {refund_amount:.2f} RSD"
                )

        items_text = "\n".join(refund_items)

        with Vertical(id="confirm-dialog"):
            yield Label("⚠️  POVRAĆAJ CELOG RAČUNA", classes="label")

            yield Label("Stavke za povraćaj:", classes="input-label")
            yield Static(items_text, id="items-summary")

            yield Static(
                f"UKUPNO ZA POVRAĆAJ: {total_refund:.2f} RSD",
                id="total-section"
            )

            yield Label("Razlog povraćaja:", classes="input-label")
            yield Input(
                placeholder="Opciono - razlog povraćaja...",
                id="reason-input"
            )

            yield Label("Način povraćaja:", classes="input-label")
            with Horizontal(id="refund-method"):
                yield Button("Gotovina", id="cash-btn", variant="primary")
                yield Button("Kartica", id="card-btn", variant="default")

            with Horizontal(id="buttons"):
                yield Button("Potvrdi povraćaj", id="confirm-btn", variant="error")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cash-btn":
            self.refund_method = "cash"
            event.button.variant = "primary"
            self.query_one("#card-btn", Button).variant = "default"
        elif event.button.id == "card-btn":
            self.refund_method = "card"
            event.button.variant = "primary"
            self.query_one("#cash-btn", Button).variant = "default"
        elif event.button.id == "confirm-btn":
            self.process_full_refund()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def process_full_refund(self) -> None:
        """Process refunds for all items with available quantity"""
        reason = self.query_one("#reason-input", Input).value.strip()

        success_count = 0
        fail_count = 0

        for item in self.items:
            if item['quantity_available'] > 0:
                success, message = self.refund_service.process_refund(
                    sale_id=self.sale_id,
                    item_name=item['item'],
                    quantity=item['quantity_available'],
                    refund_method=self.refund_method,
                    reason=reason,
                    user_id=self.user_id
                )

                if success:
                    success_count += 1
                else:
                    fail_count += 1

        # Update sale status to fully refunded
        self.unified_sales.update_status(self.sale_id, 'refunded')

        if fail_count == 0:
            self.notify(f"Povraćaj uspešan za {success_count} stavki!", severity="information")
            self.dismiss(True)
        else:
            self.notify(f"Povraćaj: {success_count} uspešnih, {fail_count} neuspešnih", severity="warning")
            self.dismiss(True)


class RefundReceiptScreen(Screen):
    """Screen for refunding entire receipt"""
    
    CSS = """
    RefundReceiptScreen {
        align: center middle;
    }
    
    #refund-dialog {
        width: 70;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 2;
    }
    
    #items-table {
        height: 15;
        border: solid $warning;
        margin: 1 0;
    }
    
    #refund-method {
        layout: horizontal;
        height: auto;
        margin: 1 0;
    }
    
    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(
        self, 
        sale_id: int,
        receipt_number: int,
        refund_service,
        pos_service,
        user_id: int
    ):
        super().__init__()
        self.sale_id = sale_id
        self.receipt_number = receipt_number
        self.refund_service = refund_service
        self.pos_service = pos_service
        self.user_id = user_id
        self.refund_method = "cash"
        self.items = []
        self.total = 0
    
    def compose(self) -> ComposeResult:
        with Vertical(id="refund-dialog"):
            yield Label(f"↩️  POVRAĆAJ CELOG RAČUNA #{self.receipt_number}", classes="label")
            
            yield Label("Stavke na računu:")
            yield DataTable(id="items-table")
            
            yield Static(f"Ukupan iznos povraćaja: 0.00 RSD", id="total-label")
            
            yield Label("Razlog povraćaja:")
            yield Input(placeholder="Opciono - razlog...", id="reason-input")
            
            yield Label("Način povraćaja:")
            with Horizontal(id="refund-method"):
                yield Button("Gotovina", id="cash-btn", variant="primary")
                yield Button("Kartica", id="card-btn", variant="default")
            
            with Horizontal(id="buttons"):
                yield Button("Izvrši povraćaj SVEGA", id="process-btn", variant="error")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="default")
    
    def on_mount(self) -> None:
        """Load receipt items"""
        table = self.query_one("#items-table", DataTable)
        table.add_columns("Artikal", "Količina", "Cena", "Ukupno")
        
        # Get all sales with this receipt number
        # For now, we'll get by sale_id (simplified)
        # In production, you'd query all items with same receipt_number
        
        # Get the sale
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        all_sales = self.pos_service.sales.get_sales_by_date(today)
        
        # Filter to this receipt (simplified - you'd use receipt_number in production)
        receipt_sales = [s for s in all_sales if s['id'] == self.sale_id]
        
        for sale in receipt_sales:
            table.add_row(
                sale['item'],
                f"{sale['quantity']:.2f}",
                f"{sale['item_price']:.2f}",
                f"{sale['total']:.2f}"
            )
            
            self.items.append({
                'item': sale['item'],
                'quantity': sale['quantity'],
                'price': sale['item_price'],
                'total': sale['total']
            })
            self.total += sale['total']
        
        self.query_one("#total-label", Static).update(
            f"Ukupan iznos povraćaja: {self.total:.2f} RSD"
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cash-btn":
            self.refund_method = "cash"
            event.button.variant = "primary"
            self.query_one("#card-btn", Button).variant = "default"
        
        elif event.button.id == "card-btn":
            self.refund_method = "card"
            event.button.variant = "primary"
            self.query_one("#cash-btn", Button).variant = "default"
        
        elif event.button.id == "process-btn":
            self.process_full_refund()
        
        elif event.button.id == "cancel-btn":
            self.dismiss(None)
    
    def process_full_refund(self) -> None:
        """Process refund for all items"""
        reason = self.query_one("#reason-input", Input).value.strip()
        
        # Confirm first
        self.app.push_screen(
            ConfirmDialog(
                f"Da li ste sigurni da želite da vratite CELU fakturu?\n\n"
                f"Ukupan iznos: {self.total:.2f} RSD\n"
                f"Broj stavki: {len(self.items)}",
                "POTVRDA POVRAĆAJA"
            ),
            lambda confirmed: self.do_refund(confirmed, reason) if confirmed else None
        )
    
    def do_refund(self, confirmed: bool, reason: str) -> None:
        """Actually process the refund"""
        success_count = 0
        total_refunded = 0
        
        for item in self.items:
            success, message = self.refund_service.process_refund(
                sale_id=self.sale_id,
                item_name=item['item'],
                quantity=item['quantity'],
                refund_method=self.refund_method,
                reason=reason or "Povraćaj celog računa",
                user_id=self.user_id
            )
            
            if success:
                success_count += 1
                total_refunded += item['total']
        
        if success_count == len(self.items):
            self.notify(
                f"✅ Povraćeno {success_count} stavki | {total_refunded:.2f} RSD",
                severity="success"
            )
            self.dismiss(True)
        else:
            self.notify(
                f"⚠️  Povraćeno {success_count}/{len(self.items)} stavki",
                severity="warning"
            )


class ProcessRefundScreen(Screen):
    """Screen for processing individual refund"""
    
    CSS = """
    ProcessRefundScreen {
        align: center middle;
    }
    
    #refund-dialog {
        width: 60;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 2;
    }
    
    #sale-info {
        padding: 1;
        background: $panel;
        margin-bottom: 1;
    }
    
    .input-label {
        padding: 1 0 0 0;
    }
    
    Input {
        margin-bottom: 1;
    }
    
    #refund-method {
        layout: horizontal;
        height: auto;
        margin: 1 0;
    }
    
    #buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(
        self, 
        sale_id: int, 
        item_name: str, 
        quantity_sold: float,
        price: float,
        refund_service,
        user_id: int
    ):
        super().__init__()
        self.sale_id = sale_id
        self.item_name = item_name
        self.quantity_sold = quantity_sold
        self.price = price
        self.refund_service = refund_service
        self.user_id = user_id
        self.refund_method = "cash"
    
    def compose(self) -> ComposeResult:
        total = self.price * self.quantity_sold
        
        with Vertical(id="refund-dialog"):
            yield Label("↩️  POVRAĆAJ ARTIKLA", classes="label")
            
            yield Static(
                f"Artikal: {self.item_name}\n"
                f"Prodato: {self.quantity_sold:.2f} kom\n"
                f"Cena: {self.price:.2f} RSD\n"
                f"Ukupno: {total:.2f} RSD",
                id="sale-info"
            )
            
            yield Label("Količina za povraćaj:", classes="input-label")
            yield Input(
                placeholder="Količina...",
                id="quantity-input",
                type="number",
                value=str(self.quantity_sold)  # Default to full refund
            )
            
            yield Label("Razlog povraćaja:", classes="input-label")
            yield Input(
                placeholder="Opciono - razlog povraćaja...",
                id="reason-input"
            )
            
            yield Label("Način povraćaja:", classes="input-label")
            with Horizontal(id="refund-method"):
                yield Button("Gotovina", id="cash-btn", variant="primary")
                yield Button("Kartica", id="card-btn", variant="default")
            
            with Horizontal(id="buttons"):
                yield Button("Izvrši povraćaj", id="process-btn", variant="warning")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="default")
    
    def on_mount(self) -> None:
        self.query_one("#quantity-input", Input).focus()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cash-btn":
            self.refund_method = "cash"
            event.button.variant = "primary"
            self.query_one("#card-btn", Button).variant = "default"
        
        elif event.button.id == "card-btn":
            self.refund_method = "card"
            event.button.variant = "primary"
            self.query_one("#cash-btn", Button).variant = "default"
        
        elif event.button.id == "process-btn":
            self.process_refund()
        
        elif event.button.id == "cancel-btn":
            self.dismiss(None)
    
    def process_refund(self) -> None:
        """Process the refund"""
        quantity_str = self.query_one("#quantity-input", Input).value.strip()
        reason = self.query_one("#reason-input", Input).value.strip()
        
        if not quantity_str:
            self.notify("Unesite količinu!", severity="error")
            return
        
        try:
            quantity = float(quantity_str)
            
            if quantity <= 0:
                self.notify("Količina mora biti veća od 0!", severity="error")
                return
            
            if quantity > self.quantity_sold:
                self.notify(
                    f"Ne možete vratiti više nego što je prodato ({self.quantity_sold:.2f})!",
                    severity="error"
                )
                return
            
            # Process refund
            success, message = self.refund_service.process_refund(
                sale_id=self.sale_id,
                item_name=self.item_name,
                quantity=quantity,
                refund_method=self.refund_method,
                reason=reason,
                user_id=self.user_id
            )
            
            if success:
                self.notify(f"✅ {message}", severity="success")
                self.dismiss(True)
            else:
                self.notify(f"❌ {message}", severity="error")
        
        except ValueError:
            self.notify("Unesite ispravnu količinu!", severity="error")


class ConfirmDeleteScreen(Screen):
    """Screen for confirming user deletion"""
    CSS = """
        ConfirmDeleteScreen {
            align: center middle;
        }

        #confirm-dialog {
            width: 50;
            height: auto;
            max-height: 20;
            border: thick $error;
            background: $surface;
            padding: 2;
        }

        #buttons {
            height: auto;
            layout: horizontal;
            align: center middle;
            margin-top: 1;
        }
    """

    BINDINGS = [
        Binding("d", "confirm_delete", "Confirm Delete"),
        Binding("n", "cancel_delete", "Cancel Delete"),
    ]

    def __init__(self, user_service, user_id: int, username: str):
        super().__init__()
        self.user_service = user_service
        self.user_id = user_id
        self.username = username

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label("🟡  BRISANJE KORISNIKA", classes="label")
            yield Static(f"Da li ste sigurni da želite da obrišete korisnika {self.username}?")
            with Horizontal(id="buttons"):
                yield Button("Da \\[D]", id="confirm-btn", variant="success")
                yield Button("Ne \\[N]", id="cancel-btn", variant="error")


    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.action_confirm_delete()
        elif event.button.id == "cancel-btn":
            self.action_cancel_delete()

    def action_confirm_delete(self) -> None:
        """Confirm user deletion"""
        success, message = self.user_service.delete_user(self.user_id)
        if success:
            self.notify(message, severity="success")
            self.dismiss(True)
        else:
            self.notify(message, severity="error")
            self.dismiss(False)

    def action_cancel_delete(self) -> None:
        """Cancel user deletion"""
        self.dismiss(False)



if __name__ == "__main__":
    app = POSApp()
    app.run()
