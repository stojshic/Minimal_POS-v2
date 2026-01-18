"""
Textual TUI for POS System
Beautiful terminal interface
"""
from typing import Optional
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Button, DataTable, Input, Label, Static
from textual.binding import Binding
from textual.screen import Screen 
from time import time
from pos_db_layer import (
    Database, InventoryRepository, SalesRepository,
    InvoiceRepository, PaymentRepository, ReceiptRepository,
    UserRepository, RefundRepository
)
from pos_business_logic import (
        POSService, ReportService, PaymentInfo, DailyReportService, 
        UserService, RefundService
)
from config import STORE_CONFIG, CONFIG

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
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, message: str, title: str = "POTVRDA"):
        super().__init__()
        self.message = message
        self.title = title
    
    def compose(self) -> ComposeResult:  # ← No parameters here!
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


class RefundsHistoryScreen(Screen):
    """View refund history"""
    
    CSS = """
    RefundsHistoryScreen {
        background: $surface;
    }
    
    #history-container {
        height: 100%;
        padding: 1;
    }
    
    #refunds-table {
        height: 1fr;
        border: solid $warning;
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
    ]
    
    def __init__(self, refund_service):
        super().__init__()
        self.refund_service = refund_service
    
    def compose(self) -> ComposeResult:
        with Vertical(id="history-container"):
            yield Label("📋 ISTORIJA POVRAĆAJA", classes="label")
            
            with Horizontal():
                yield Input(
                    placeholder="Datum (YYYY-MM-DD) ili Enter za danas",
                    id="date-input"
                )
                yield Button("Prikaži", id="show-btn", variant="primary")
            
            yield DataTable(id="refunds-table")
            
            with Horizontal(id="controls"):
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
    
    def on_mount(self) -> None:
        from datetime import datetime
        
        table = self.query_one("#refunds-table", DataTable)
        table.add_columns("ID", "Artikal", "Količina", "Iznos", "Metoda", "Razlog", "Vreme")
        
        today = datetime.now().strftime("%Y-%m-%d")
        self.query_one("#date-input", Input).value = today
        self.load_refunds(today)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "show-btn":
            self.load_from_input()
        elif event.button.id == "close-btn":
            self.action_close()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "date-input":
            event.stop()
            self.load_from_input()
    
    def load_from_input(self) -> None:
        date = self.query_one("#date-input", Input).value.strip()
        self.load_refunds(date)
    
    def load_refunds(self, date: str) -> None:
        from datetime import datetime
        
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        refunds = self.refund_service.refunds.get_refunds_by_date(date)
        
        table = self.query_one("#refunds-table", DataTable)
        table.clear()
        
        if not refunds:
            self.notify(f"Nema povraćaja za {date}", severity="information")
            return
        
        for refund in refunds:
            table.add_row(
                str(refund['id']),
                refund['item'],
                f"{refund['quantity']:.2f}",
                f"{refund['refund_amount']:.2f}",
                refund['refund_method'].upper(),
                refund['reason'] or "-",
                refund['created_at']
            )
        
        total = sum(r['refund_amount'] for r in refunds)
        self.notify(
            f"Učitano {len(refunds)} povraćaja | Ukupno: {total:.2f} RSD",
            severity="information"
        )
    
    def action_close(self) -> None:
        self.dismiss()


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
        Binding("n", "new_item", "New Item"),
        Binding("e", "edit_item", "Edit Item"),
        Binding("delete", "delete_item", "Delete Item"),
        Binding("p", "change_price", "Change Price"),
    ]

    def __init__(self, pos_service):
        super().__init__()
        self.pos_service = pos_service

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

    def on_mount(self) -> None:
        """Setup table and load inventory"""
        table = self.query_one("#inventory-table", DataTable)
        table.add_columns("ID", "Artikal", "Barkod", "Cena", "Količina", "PDV %")
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
            table.add_row(
                str(item['id']),
                item['item'],
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
        self.app.push_screen(AddEditItemScreen(self.pos_service), self.handle_item_changed)

    def action_edit_item(self) -> None:
        """Edit selected item"""
        item = self.get_selected_item()
        if item:
            self.app.push_screen(
                AddEditItemScreen(self.pos_service, item),
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

    #vat-selection {
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

    def __init__(self, pos_service, item: Optional[dict] = None):
        super().__init__()
        self.pos_service = pos_service
        self.item = item  # None for new item, dict for editing
        self.is_edit_mode = item is not None
        self.selected_vat = item.get('vat_rate', 0.20) if item else 0.20

    def compose(self) -> ComposeResult:
        title = "✏️  IZMENA ARTIKLA" if self.is_edit_mode else "➕ NOVI ARTIKAL"

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

            yield Label("PDV stopa:", classes="input-label")
            with Horizontal(id="vat-selection"):
                yield Button("0%", id="vat-0", variant="default")
                yield Button("10%", id="vat-10", variant="default")
                yield Button("20%", id="vat-20", variant="primary")

            with Horizontal(id="buttons"):
                yield Button("Sačuvaj", id="save-btn", variant="success")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        """Focus name input and set VAT button states"""
        self.query_one("#name-input", Input).focus()

        # Highlight correct VAT button
        self.update_vat_buttons()

    def update_vat_buttons(self) -> None:
        """Update VAT button appearances"""
        vat_buttons = {
            0.0: self.query_one("#vat-0", Button),
            0.10: self.query_one("#vat-10", Button),
            0.20: self.query_one("#vat-20", Button),
        }

        for rate, button in vat_buttons.items():
            button.variant = "primary" if rate == self.selected_vat else "default"

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
        elif event.button.id == "save-btn":
            self.save_item()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def save_item(self) -> None:
        """Save the item"""
        name = self.query_one("#name-input", Input).value.strip()
        barcode = self.query_one("#barcode-input", Input).value.strip() or None
        price_str = self.query_one("#price-input", Input).value.strip()
        quantity_str = self.query_one("#quantity-input", Input).value.strip()

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
                # Update existing item
                # We need to add an update method that handles all fields
                item_id = self.item['id']

                # Update price
                self.pos_service.inventory.update_price(item_id, price)

                # Update quantity (delta from current)
                current_qty = self.item['quantity']
                qty_delta = quantity - current_qty
                self.pos_service.inventory.update_quantity(item_id, qty_delta)

                # TODO: Update name, barcode, VAT rate (need to add method)

                self.notify(f"✅ Artikal '{name}' ažuriran!", severity="success")
            else:
                # Add new item
                item_id = self.pos_service.inventory.add(name, price, quantity, barcode)

                # TODO: Set VAT rate (need to add method)

                self.notify(f"✅ Artikal '{name}' dodat!", severity="success")

            self.dismiss(True)

        except Exception as e:
            self.notify(f"❌ Greška: {str(e)}", severity="error")

    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)


class InvoiceManagementScreen(Screen):
    """Screen for receiving goods via invoices"""

    CSS = """
    InvoiceManagementScreen {
        background: $surface;
    }

    #invoice-container {
        height: 100%;
        padding: 1;
    }

    #invoice-header {
        height: auto;
        background: $panel;
        padding: 1;
        margin-bottom: 1;
    }

    #invoice-items-table {
        height: 1fr;
        border: solid $primary;
        margin-bottom: 1;
    }

    #invoice-controls {
        dock: bottom;
        height: auto;
        layout: horizontal;
        background: $panel;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("n", "add_item", "Add Item"),
        Binding("d", "remove_item", "Remove Item"),
        Binding("s", "save_invoice", "Save Invoice"),
    ]

    def __init__(self, pos_service):
        super().__init__()
        self.pos_service = pos_service
        self.invoice_items = []  # Items to add to invoice

    def compose(self) -> ComposeResult:
        with Vertical(id="invoice-container"):
            yield Label("📄 PRIJEM ROBE - NOVA FAKTURA", classes="label")

            with Vertical(id="invoice-header"):
                yield Label("Broj fakture:")
                yield Input(placeholder="Unesite broj fakture...", id="invoice-number-input")

            yield Label("Stavke fakture:")
            yield DataTable(id="invoice-items-table")

            with Horizontal(id="invoice-controls"):
                yield Button("Dodaj stavku \\[N]", id="add-item-btn", variant="success")
                yield Button("Ukloni \\[D]", id="remove-item-btn", variant="error")
                yield Button("Sačuvaj fakturu \\[S]", id="save-btn", variant="primary")
                yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="default")

    def on_mount(self) -> None:
        """Setup table"""
        table = self.query_one("#invoice-items-table", DataTable)
        table.add_columns("Naziv", "Barkod", "Cena", "Količina", "Ukupno")
        table.cursor_type = "row"

        self.query_one("#invoice-number-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-item-btn":
            self.action_add_item()
        elif event.button.id == "remove-item-btn":
            self.action_remove_item()
        elif event.button.id == "save-btn":
            self.action_save_invoice()
        elif event.button.id == "cancel-btn":
            self.action_close()

    def action_add_item(self) -> None:
        """Add item to invoice"""
        self.app.push_screen(
            AddInvoiceItemScreen(self.pos_service),
            self.handle_item_added
        )

    def action_remove_item(self) -> None:
        """Remove selected item from invoice"""
        table = self.query_one("#invoice-items-table", DataTable)
        if table.cursor_row is not None and self.invoice_items:
            del self.invoice_items[table.cursor_row]
            self.update_items_display()
            self.notify("Stavka uklonjena", severity="warning")

    def action_save_invoice(self) -> None:
        """Save invoice and update inventory"""
        invoice_number = self.query_one("#invoice-number-input", Input).value.strip()

        if not invoice_number:
            self.notify("Unesite broj fakture!", severity="error")
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
            self.dismiss(True)
        else:
            self.notify(f"❌ {message}", severity="error")

    def action_close(self) -> None:
        """Close without saving"""
        self.dismiss(None)

    def handle_item_added(self, item_data) -> None:
        """Callback when item is added"""
        if item_data:
            self.invoice_items.append(item_data)
            self.update_items_display()

    def update_items_display(self) -> None:
        """Refresh items table"""
        table = self.query_one("#invoice-items-table", DataTable)
        table.clear()

        for item in self.invoice_items:
            total = item['price'] * item['quantity']
            table.add_row(
                item['name'],
                item.get('barcode') or "",
                f"{item['price']:.2f}",
                f"{item['quantity']:.2f}",
                f"{total:.2f}"
            )
            

class ReportsScreen(Screen):
    """Screen for viewing reports"""
    
    CSS = """
    ReportsScreen {
        background: $surface;
    }
    
    #reports-container {
        height: 100%;
        padding: 1;
    }
    
    #report-menu {
        width: 40;
        height: auto;
        border: solid $primary;
        padding: 2;
        align: center top;
    }
    
    .menu-button {
        width: 100%;
        margin: 1 0;
    }
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
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
        with Vertical(id="reports-container"):
            yield Label("📊 IZVEŠTAJI", classes="label")
            
            with Vertical(id="report-menu"):
                yield Button("1. Dnevni izveštaj", id="daily-btn", variant="primary", classes="menu-button")
                yield Button("2. Zatvaranje kase", id="cash-btn", variant="success", classes="menu-button")
                yield Button("3. Nisko stanje zaliha", id="stock-btn", variant="warning", classes="menu-button")
                
                if self.is_admin:
                    yield Button("4. Nedeljni izveštaj", id="weekly-btn", variant="default", classes="menu-button")
                    yield Button("5. Mesečni izveštaj", id="monthly-btn", variant="default", classes="menu-button")
                    yield Button("6. Top artikli", id="top-btn", variant="default", classes="menu-button")
                
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="error", classes="menu-button")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "daily-btn":
            self.action_daily_report()
        elif event.button.id == "cash-btn":
            self.action_cash_reconciliation()
        elif event.button.id == "stock-btn":
            self.action_low_stock()
        elif event.button.id == "weekly-btn" and self.is_admin:
            self.notify("Nedeljni izveštaj - u izradi", severity="information")
        elif event.button.id == "monthly-btn" and self.is_admin:
            self.notify("Mesečni izveštaj - u izradi", severity="information")
        elif event.button.id == "top-btn" and self.is_admin:
            self.show_top_items()
        elif event.button.id == "close-btn":
            self.action_close()
    
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
        background: $surface;
    }
    
    #daily-container {
        height: 100%;
        padding: 1;
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
    ]
    
    def __init__(self, daily_reports):
        super().__init__()
        self.daily_reports = daily_reports
    
    def compose(self) -> ComposeResult:
        with Vertical(id="daily-container"):
            yield Label("📊 DNEVNI IZVEŠTAJ", classes="label")
            
            yield Input(
                placeholder="Datum (YYYY-MM-DD) ili Enter za danas",
                id="date-input"
            )
            
            yield Static("", id="report-content")
            
            with Horizontal(id="controls"):
                yield Button("Prikaži", id="show-btn", variant="primary")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
    
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
        
        # Format report
        content = []
        content.append("=" * 60)
        content.append(f"DNEVNI IZVEŠTAJ ZA {date}".center(60))
        content.append("=" * 60)
        
        summary = report['summary']
        content.append("\n📊 OSNOVNI PODACI:")
        content.append(f"   Ukupan prihod:        {summary['total_revenue']:>12.2f} RSD")
        content.append(f"   Broj transakcija:     {summary['total_transactions']:>12}")
        content.append(f"   Prodato artikala:     {summary['total_items_sold']:>12.2f}")
        content.append(f"   Prosečna transakcija: {summary['avg_transaction']:>12.2f} RSD")
        
        payments = report['payments']
        content.append("\n💳 NAČIN PLAĆANJA:")
        content.append(f"   Gotovina:             {payments['cash']:>12.2f} RSD")
        content.append(f"   Kartica:              {payments['card']:>12.2f} RSD")
        content.append(f"   {'─'*40}")
        content.append(f"   UKUPNO:               {payments['total']:>12.2f} RSD")
        
        content.append("\n📋 PDV REKAPITULACIJA:")
        for vat_rate, data in report['vat_breakdown'].items():
            vat_percent = int(vat_rate * 100)
            content.append(f"   Stopa {vat_percent}%:")
            content.append(f"      Osnovica:          {data['base']:>12.2f} RSD")
            content.append(f"      PDV:               {data['vat']:>12.2f} RSD")
            content.append(f"      Ukupno:            {data['total']:>12.2f} RSD")
        
        content.append("\n🏆 TOP 10 ARTIKALA:")
        for i, (item_name, data) in enumerate(report['top_items'], 1):
            content.append(f"   {i:2}. {item_name:<30} {data['quantity']:>6.0f} kom  {data['revenue']:>10.2f} RSD")
        
        content.append("\n⏰ PRODAJA PO SATIMA:")
        for hour, data in report['hourly_sales']:
            bar_length = int(data['revenue'] / 100)
            bar = '█' * min(bar_length, 40)
            content.append(f"   {hour}:00  {data['transactions']:>3} trans  {data['revenue']:>10.2f} RSD  {bar}")
        
        # Show refunds if any
        if 'refunds' in report and report['refunds']:
            content.append("\n↩️  POVRAĆAJI:")
            total_refunds = sum(r['refund_amount'] for r in report['refunds'])
            content.append(f"   Broj povraćaja: {len(report['refunds'])}")
            content.append(f"   Ukupan iznos:   {total_refunds:>12.2f} RSD")

            for refund in report['refunds'][:10]:  # Show first 10
                content.append(
                    f"   • {refund['item']}: {refund['quantity']:.0f} kom "
                    f"({refund['refund_amount']:.2f} RSD) - {refund['reason'] or 'Bez razloga'}"
                )

        content.append("\n" + "=" * 60)
            
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
            result.append("=" * 50)
            result.append("ZATVARANJE KASE")
            result.append("=" * 50)
            result.append(f"\nDatum: {reconciliation['date']}")
            result.append(f"\nOčekivana gotovina:    {reconciliation['expected_cash']:>12.2f} RSD")
            result.append(f"Prebrojana gotovina:   {actual_cash:>12.2f} RSD")
            result.append(f"Izdati kusur:          {reconciliation['total_change_given']:>12.2f} RSD")
            result.append("─" * 50)
            
            diff = reconciliation['difference']
            if reconciliation['is_balanced']:
                result.append(f"Status: ✅ URAVNOTEŽENO")
            elif diff > 0:
                result.append(f"Status: 🟡  VIŠAK: {diff:>12.2f} RSD")
            else:
                result.append(f"Status: ❌ MANJAK: {abs(diff):>12.2f} RSD")
            
            result.append("=" * 50)
            
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
    
    #stock-table {
        height: 1fr;
        border: solid $warning;
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
            
            with Horizontal():
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

    #payment-buttons {
        layout: horizontal;
        height: auto;
        align: center middle;
        padding-top: 1;
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
    ]

    def __init__(self, cart_total: float):
        super().__init__()
        self.cart_total = cart_total
        self.payment_info = None

    def compose(self) -> ComposeResult:
        with Vertical(id="payment-dialog"):
            yield Label(f"💰 UKUPNO ZA NAPLATU: {self.cart_total:.2f} RSD", id="payment-info")
            yield Label("Izaberite način plaćanja:", classes="label")

            with Horizontal(id="payment-buttons"):
                yield Button("Gotovina \\[1]", id="cash-btn", variant="success", classes="payment-option")
                yield Button("Kartica \\[2]", id="card-btn", variant="primary", classes="payment-option")
                yield Button("Kombinovano \\[3]", id="split-btn", variant="warning", classes="payment-option")

            yield Button("Otkaži \\[ESC]", id="cancel-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle payment method selection"""
        if event.button.id == "cash-btn":
            self.action_cash()
        elif event.button.id == "card-btn":
            self.action_card()
        elif event.button.id == "split-btn":
            self.action_split()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cash(self) -> None:
        """Cash payment"""
        self.app.push_screen(CashPaymentScreen(self.cart_total), self.handle_payment_result)

    def action_card(self) -> None:
        """Card payment"""
        payment_info = PaymentInfo(
            payment_type='card',
            card_amount=self.cart_total
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
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close"),
        Binding("p", "print", "Print Again"),
    ]

    def __init__(self, receipt_text: str, sale_id: int):
        super().__init__()
        self.receipt_text = receipt_text
        self.sale_id = sale_id

    def compose(self) -> ComposeResult:
        with Vertical(id="receipt-container"):
            yield Label("🧾 FISKALNI RAČUN", classes="label")
            yield Static(self.receipt_text, id="receipt-display")

            with Horizontal(id="close-button-container"):
                yield Button("Zatvori \\[Enter/ESC]", id="close-btn", variant="success")
                yield Button("Štampaj ponovo \\[P]", id="print-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.action_close()
        elif event.button.id == "print-btn":
            self.action_print()

    def action_close(self) -> None:
        """Close receipt viewer"""
        self.dismiss()

    def action_print(self) -> None:
        """Print receipt again (future: send to printer)"""
        self.notify("Račun bi bio odštampan (u izradi)", severity="information")


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
        background: $warning;
        color: $text;
        content-align: center middle;
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
        Binding("f1", "show_help", "Help", show=True),
        Binding("f2", "sales", "Sales", show=True),
        Binding("f3", "inventory", "Inventory", show=True),
        Binding("f4", "reports", "Reports", show=True),
        Binding("f5", "checkout", "Checkout", show=True),
        Binding("f6", "invoices", "Invoices", show=True),
        Binding("f7", "refunds", "Refunds", show=True),
        Binding("f8", "user_management", "Users", show=True),
        Binding("f9", "logout", "Logout", show=True),
        Binding("c", "clear_cart", "Clear Cart"),
        Binding("enter", "add_selected", "Add to Cart"),
        Binding("-", "remove_selected", "Remove"),
        Binding("e", "edit_quantity", "Edit Qty")
    ]

    def __init__(self):
        super().__init__()

        # Initialize backend
        db = Database("data.db")
        inv_repo = InventoryRepository(db)
        sales_repo = SalesRepository(db)
        payment_repo = PaymentRepository(db)
        user_repo = UserRepository(db)  # ← NEW
        refund_repo = RefundRepository(db)

        self.pos = POSService(
            inv_repo,
            sales_repo,
            InvoiceRepository(db),
            payment_repo,
            ReceiptRepository(db)
        )

        self.reports = ReportService(inv_repo, sales_repo)
        self.daily_reports = DailyReportService(sales_repo, payment_repo, inv_repo)
        self.user_service = UserService(user_repo)  # ← NEW
        self.refund_service = RefundService(sales_repo, inv_repo, refund_repo)

        # Current logged in user
        self.current_user = None  # ← NEW

        # Shopping cart
        self.cart = []
        self.cart_total = 0.0

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Static("", id="user-info") # Shows logged-in user
        yield Static ("", id="low-stock-banner")

        # Main container with horizontal layout
        with Horizontal(id="main-container"):
            # Left panel - Inventory
            with Vertical(id="inventory-panel"):
                yield Label("📦 INVENTAR", classes="label")
                yield Input(placeholder="Pretraga ili skeniranje...", id="search-input")
                yield DataTable(id="inventory-table", zebra_stripes=True)

            # Right panel - Shopping Cart
            with Vertical(id="cart-panel"):
                yield Label("🛒 KORPA", classes="label")
                yield DataTable(id="cart-table", zebra_stripes=True, cursor_type="row")
                yield Static("UKUPNO: 0.00 RSD", id="total-label")

        # Bottom controls
        with Horizontal(id="controls"):
            yield Button("Dodaj u korpu \\[Enter]", id="add-to-cart", variant="primary")
            yield Button("Ukloni \\[-]", id="remove-from-cart", variant="error")
            yield Button("Naplati \\[F5]", id="checkout", variant="success")
            yield Button("Očistii \\[C]", id="clear-cart")

        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts"""
        # Show login screen first
        self.push_screen(LoginScreen(self.user_service), self.handle_login)

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

    def action_user_management(self) -> None:
        """F8 - User Management (admin only)"""
        if not self.require_admin("Upravljanje korisnicima"):
            return

        self.push_screen(UserManagementScreen(self.user_service))

    def action_refunds(self):
        """F7 - Returns and refunds"""
        self.push_screen(
            RefundsScreen(self.pos, self.refund_service, self.current_user)
        )

    def action_invoices(self) -> None:
        """F6 - Invoice management (admin only)"""
        if not self.require_admin("Prijem robe"):
            return

        self.push_screen(InvoiceManagementScreen(self.pos))

    def handle_login(self, user: dict) -> None:
        """Handle successful login"""
        if user:
            if user['role'] == "admin":
                self.push_screen(InventoryManagementScreen(self.pos))
            self.current_user = user

            # Update user info bar
            user_info = self.query_one("#user-info", Static)
            user_info.update(
                f"👤 {user['full_name']} ({user['role'].upper()}) | F9: Odjava"
            )

            # Update header or show welcome message
            self.notify(
                f"✅ Prijavljeni kao: {user['full_name']} ({user['role']})",
                severity="information",
                timeout=5
            )

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
        else:
            # Login failed or cancelled - quit app
            self.exit()

    def update_ui_for_role(self) -> None:
        """Update UI based on user role"""
        if not self.current_user:
            return

        role = self.current_user['role']

        # For now, all users see the same interface
        # We'll add admin-only screens in next step

        if role == 'cashier':
            # Cashiers can't access certain features (we'll add restrictions)
            pass
        elif role == 'admin':
            # Admins see everything
            pass

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

    def action_logout(self) -> None:
        """F9 - Logout current user"""
        # Clear cart before logout for security
        self.cart = []
        self.update_cart_display()

        # Show login screen again
        self.push_screen(LoginScreen(self.user_service), self.handle_login)

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
                inv_table = self.query_one("#inventory-table", DataTable)
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
        for item in self.cart:
            line_total = item['price'] * item['quantity']
            total += line_total

            cart_table.add_row(
                item['item'],
                f"{item['quantity']:.2f}",
                f"{item['price']:.2f}",
                f"{line_total:.2f}"
            )

        self.cart_total = total
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
                self.push_screen(PaymentScreen(self.cart_total), self.handle_checkout)
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
            result = self.pos.sell_multiple_items(
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
                receipt_data = self.pos.receipts.get_receipt_by_sale_id(last_sale_id)

                if receipt_data:
                    # Show receipt viewer
                    self.push_screen(
                        ReceiptViewerScreen(receipt_data['receipt_text'], last_sale_id),
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

        # Clear cart and reload inventory
        self.cart = []
        self.update_cart_display()
        self.load_inventory()

        # Update low stock banner
        self.update_low_stock_banner()

        # Focus search for next sale
        self.query_one("#search-input", Input).focus()

    def action_sales(self) -> None:
        """F2 - Sales screen"""
        self.notify("Prodaja - trenutni ekran")

    def action_inventory(self) -> None:
        """F3 - Inventory management (admin only)"""
        if not self.require_admin("Upravljanje inventarom"):
            return

        # Show submenu for inventory management
        self.push_screen(InventoryManagementScreen(self.pos))
        # self.notify("Upravljanje inventarom - u izradi!", severity="information")

    def action_reports(self) -> None:
        # Cashiers can see basic reports, admins see all
        """F4 - Reports"""
        self.push_screen(
            ReportsScreen(
                self.daily_reports,
                self.reports,
                self.is_admin()
            )
        ) 

    def action_show_help(self) -> None:
        """F1 - Show help"""
        self.notify(
            "F2: Prodaja | F3: Inventar | F4: Izveštaji | Q: Izlaz",
            severity="information"
        )

    def action_checkout(self) -> None:
        """F5 - Checkout"""
        if self.cart:
            self.push_screen(PaymentScreen(self.cart_total), self.handle_checkout)
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


class RefundsScreen(Screen):
    """Screen for processing returns and refunds"""
    
    CSS = """
        RefundsScreen {
            background: $surface;
        }
        
        #refunds-container {
            height: 100%;
            padding: 1;
        }
        
        #search-section {
            height: auto;
            background: $panel;
            padding: 1;
            margin-bottom: 1;
        }
        
        #search-row {
            layout: horizontal;
            height: auto;
        }
        
        #sales-table {
            height: 1fr;
            border: solid $primary;
            margin: 1 0;
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
        Binding("r", "process_refund", "Refund"),
        Binding("h", "view_history", "History"),
        Binding("a", "refund_receipt", "Refund All")
    ]
    
    def __init__(self, pos_service, refund_service, current_user):
        super().__init__()
        self.pos_service = pos_service
        self.refund_service = refund_service
        self.current_user = current_user
    
    def compose(self) -> ComposeResult:
        with Vertical(id="refunds-container"):
            yield Label("↩️  POVRAĆAJ ROBE", classes="label")
            
            with Vertical(id="search-section"):
                yield Label("Pretraga prodaja:")
                with Horizontal(id="search-row"):
                    yield Input(
                        placeholder="Datum (YYYY-MM-DD) ili Enter za danas",
                        id="date-input"
                    )
                    yield Button("Pretraži", id="search-btn", variant="primary")
            
            yield Label("Nedavne prodaje:")
            yield DataTable(id="sales-table")  # ← Make sure this ID matches!
            
            with Horizontal(id="controls"):
                yield Button("Povraćaj stavke \\[R]", id="refund-btn", variant="warning")
                yield Button("Povraćaj računa \\[A]", id="refund-all-btn", variant="error")
                yield Button("Istorija \\[H]", id="history-btn", variant="default")
                yield Button("Zatvori \\[ESC]", id="close-btn", variant="default")
    
    def on_mount(self) -> None:
        """Setup and load today's sales"""
        from datetime import datetime
        
        # Setup table
        try:
            table = self.query_one("#sales-table", DataTable)
            table.add_columns("ID", "Artikal", "Količina", "Cena", "Ukupno", "Vreme")
            table.cursor_type = "row"
        except Exception as e:
            self.notify(f"Error setting up table: {e}", severity="error")
            return
        
        # Load today's sales
        today = datetime.now().strftime("%Y-%m-%d")
        self.query_one("#date-input", Input).value = today
        self.load_sales(today)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search-btn":
            self.search_sales()
        elif event.button.id == "refund-btn":
            self.action_process_refund()
        elif event.button.id == "close-btn":
            self.action_close()
        elif event.button.id == "history-btn":
            self.action_view_history()
        elif event.button.id == "refund-all-btn":
            self.action_refund_receipt()

    def action_view_history(self) -> None:
        """View refunds history"""
        self.app.push_screen(RefundsHistoryScreen(self.refund_service))
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "date-input":
            event.stop()
            self.search_sales()
    
    def search_sales(self) -> None:
        """Search sales by date"""
        date = self.query_one("#date-input", Input).value.strip()
        if date:
            self.load_sales(date)
    
    def load_sales(self, date: str) -> None:
        """Load sales for given date"""
        from datetime import datetime
        
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        sales = self.pos_service.sales.get_sales_by_date(date)
        
        table = self.query_one("#sales-table", DataTable)
        table.clear()
        
        if not sales:
            self.notify(f"Nema prodaja za {date}", severity="information")
            return
        
        for sale in sales:
            table.add_row(
                str(sale['id']),
                sale['item'],
                f"{sale['quantity']:.2f}",
                f"{sale['item_price']:.2f}",
                f"{sale['total']:.2f}",
                sale['time']
            )
        
        self.notify(f"Učitano {len(sales)} prodaja", severity="information")
    
    def action_process_refund(self) -> None:
        """Process refund for selected sale"""
        table = self.query_one("#sales-table", DataTable)
        
        if table.cursor_row is None:
            self.notify("Izaberite prodaju!", severity="warning")
            return
        
        row = table.get_row_at(table.cursor_row)
        sale_id = int(row[0])
        item_name = row[1]
        quantity_sold = float(row[2])
        price = float(row[3])
        
        # Open refund dialog
        self.app.push_screen(
            ProcessRefundScreen(
                sale_id=sale_id,
                item_name=item_name,
                quantity_sold=quantity_sold,
                price=price,
                refund_service=self.refund_service,
                user_id=self.current_user['id']
            ),
            self.handle_refund_processed
        )
    
    def handle_refund_processed(self, result) -> None:
        """Callback after refund is processed"""
        if result:
            # Reload sales
            date = self.query_one("#date-input", Input).value.strip()
            self.load_sales(date)

    def action_refund_receipt(self) -> None:
        """Refund entire receipt"""
        table = self.query_one("#sales-table", DataTable)

        if table.cursor_row is None:
            self.notify("Izaberite prodaju!", severity="warning")
            return

        row = table.get_row_at(table.cursor_row)
        sale_id = int(row[0])

        # Get receipt for this sale
        receipt_data = self.pos_service.receipts.get_receipt_by_sale_id(sale_id)

        if not receipt_data:
            self.notify("Račun nije pronađen!", severity="error")
            return

        # Show receipt refund dialog
        self.app.push_screen(
            RefundReceiptScreen(
                sale_id=sale_id,
                receipt_number=receipt_data['receipt_number'],
                refund_service=self.refund_service,
                pos_service=self.pos_service,
                user_id=self.current_user['id']
            ),
            self.handle_refund_processed
        )

    def action_close(self) -> None:
        self.dismiss()


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
