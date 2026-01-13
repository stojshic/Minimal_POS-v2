"""
Textual TUI for POS System
Beautiful terminal interface
"""
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, DataTable, Input, Label, Static
from textual.binding import Binding
from textual.screen import Screen

from pos_db_layer import (
    Database, InventoryRepository, SalesRepository,
    InvoiceRepository, PaymentRepository, ReceiptRepository,
    UserRepository
)
from pos_business_logic import POSService, ReportService, PaymentInfo, DailyReportService, UserService, InvoiceItem
from config import STORE_CONFIG


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

            yield Button("Prijavi se [Enter]", id="login-button", variant="success")

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
                yield Button("|N|ovi korisnik", id="new-user-btn", variant="success")
                yield Button("|P|romeni lozinku", id="password-btn", variant="primary")
                yield Button("|D|Aktiviraj/|D|eaktiviraj", id="toggle-btn", variant="warning")
                yield Button("|Del|Obriši", id="delete-btn", variant="error")
                yield Button("|ESC|Zatvori", id="close-btn", variant="default")

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
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")

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
                yield Button("Promeni [Enter]", id="change-btn", variant="success")
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")

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
                yield Button("1. Gotovina", id="cash-btn", variant="success", classes="payment-option")
                yield Button("2. Kartica", id="card-btn", variant="primary", classes="payment-option")
                yield Button("3. Kombinovano", id="split-btn", variant="warning", classes="payment-option")

            yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")

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
                yield Button("Potvrdi [Enter]", id="confirm-btn", variant="success")
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")

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
                yield Button("Potvrdi [Enter]", id="confirm-btn", variant="success")
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")

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
                yield Button("Zatvori [Enter/ESC]", id="close-btn", variant="success")
                yield Button("Štampaj ponovo [P]", id="print-btn", variant="primary")

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
                yield Button("Potvrdi [Enter]", id="confirm-btn", variant="success")
                # if self.edit_mode:
                #  yield Button("Obriši [Del]", id="delete-btn", variant="error")
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")

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

# Add these new classes before POSApp class in pos_tui.py

class InventoryManagementMenu(Screen):
    """Menu screen for inventory management options"""
    
    CSS = """
    InventoryManagementMenu {
        background: $surface;
    }
    
    #menu-container {
        height: 100%;
        padding: 2;
        align: center middle;
    }
    
    #menu-buttons {
        width: 50;
        height: auto;
    }
    
    Button {
        width: 100%;
        margin: 1 0;
    }
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("1", "view_inventory", "View Inventory"),
        Binding("2", "add_item", "Add Item"),
        Binding("3", "add_invoice", "Add Invoice"),
    ]
    
    def __init__(self):
        super().__init__()
    
    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            yield Label("📦 UPRAVLJANJE INVENTAROM", classes="label")
            with Vertical(id="menu-buttons"):
                yield Button("1. Pregled inventara", id="view-btn", variant="primary")
                yield Button("2. Dodaj artikal", id="add-btn", variant="success")
                yield Button("3. Unos fakture", id="invoice-btn", variant="warning")
                yield Button("Zatvori [ESC]", id="close-btn", variant="default")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "view-btn":
            self.action_view_inventory()
        elif event.button.id == "add-btn":
            self.action_add_item()
        elif event.button.id == "invoice-btn":
            self.action_add_invoice()
        elif event.button.id == "close-btn":
            self.action_close()
    
    def action_view_inventory(self) -> None:
        """View and manage inventory"""
        self.app.push_screen(InventoryManagementScreen())
    
    def action_add_item(self) -> None:
        """Add new inventory item"""
        self.app.push_screen(AddEditItemScreen(self.app.pos), self.handle_item_saved)
    
    def action_add_invoice(self) -> None:
        """Add invoice with items"""
        self.app.push_screen(AddInvoiceScreen(self.app.pos), self.handle_invoice_added)
    
    def action_close(self) -> None:
        """Close menu"""
        self.dismiss()
    
    def handle_item_saved(self, result) -> None:
        """Callback after item saved"""
        if result:
            self.notify("Artikal sačuvan!", severity="success")
    
    def handle_invoice_added(self, result) -> None:
        """Callback after invoice added"""
        if result:
            self.notify("Faktura uspešno dodata!", severity="success")
            for screen in self.app.screen_stack:
                if isinstance(screen, InventoryManagementScreen):
                    screen.load_inventory()
                    break

class InventoryManagementScreen(Screen):
    """Screen for viewing and managing inventory items"""
    
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
        Binding("n", "add_item", "New Item"),
        Binding("e", "edit_item", "Edit Item"),
        Binding("d", "delete_item", "Delete Item"),
    ]
    
    def __init__(self):
        super().__init__()
    
    def compose(self) -> ComposeResult:
        with Vertical(id="inventory-container"):
            yield Label("📦 INVENTAR", classes="label")
            yield Input(placeholder="Pretraga...", id="search-input")
            yield DataTable(id="inventory-table")
            
            with Horizontal(id="inventory-controls"):
                yield Button("Novi [N]", id="add-btn", variant="success")
                yield Button("Izmeni [E]", id="edit-btn", variant="primary")
                yield Button("Obriši [D]", id="delete-btn", variant="error")
                yield Button("Zatvori [ESC]", id="close-btn", variant="default")
    
    def on_mount(self) -> None:
        """Setup table"""
        table = self.query_one("#inventory-table", DataTable)
        table.add_columns("ID", "Artikal", "Barkod", "Cena", "Količina", "PDV")
        table.cursor_type = "row"
        self.load_inventory()
        self.query_one("#search-input", Input).focus()
    
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Live search"""
        if event.input.id == "search-input":
            self.load_inventory(event.value.strip())
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-btn":
            self.action_add_item()
        elif event.button.id == "edit-btn":
            self.action_edit_item()
        elif event.button.id == "delete-btn":
            self.action_delete_item()
        elif event.button.id == "close-btn":
            self.action_close()
    
    def action_add_item(self) -> None:
        """Add new item"""
        self.app.push_screen(AddEditItemScreen(self.app.pos), self.handle_item_saved)
    
    def action_edit_item(self) -> None:
        """Edit selected item"""
        table = self.query_one("#inventory-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            item_id = int(row[0])
            item = self.app.pos.get_inventory_item(item_id)
            if item:
                self.app.push_screen(
                    AddEditItemScreen(self.app.pos, item),
                    self.handle_item_saved
                )
            else:
                self.notify("Artikal nije pronađen!", severity="error")
        else:
            self.notify("Izaberite artikal!", severity="warning")
    
    def action_delete_item(self) -> None:
        """Delete selected item"""
        table = self.query_one("#inventory-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            item_id = int(row[0])
            item_name = row[1]
            
            self.app.push_screen(
                ConfirmDeleteItemScreen(self.app.pos, item_id, item_name),
                self.handle_item_deleted
            )
        else:
            self.notify("Izaberite artikal!", severity="warning")
    
    def action_close(self) -> None:
        """Close screen"""
        self.dismiss()
    
    def handle_item_saved(self, result) -> None:
        """Callback after item saved"""
        if result:
            self.load_inventory()
            self.notify("Artikal sačuvan!", severity="success")
    
    def handle_item_deleted(self, result) -> None:
        """Callback after item deleted"""
        if result:
            self.load_inventory()
            self.notify("Artikal obrisan!", severity="success")


class AddEditItemScreen(Screen):
    """Screen for adding or editing inventory items"""
    
    CSS = """
    AddEditItemScreen {
        align: center middle;
    }
    
    #item-dialog {
        width: 50;
        height: auto;
        max-height: 25;
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
        Binding("enter", "save", "Save"),
    ]
    
    def __init__(self, pos_service, item: dict = None):
        super().__init__()
        self.pos = pos_service
        self.item = item  # None for new item, dict for edit
        self.is_edit = item is not None
    
    def compose(self) -> ComposeResult:
        title = "✏️  IZMENA ARTIKLA" if self.is_edit else "➕ NOVI ARTIKAL"
        with Vertical(id="item-dialog"):
            yield Label(title, classes="label")
            
            yield Label("Naziv artikla:", classes="input-label")
            yield Input(
                placeholder="Unesite naziv...",
                id="name-input",
                value=self.item['item'] if self.item else ""
            )
            
            yield Label("Cena (RSD):", classes="input-label")
            yield Input(
                placeholder="0.00",
                id="price-input",
                type="number",
                value=str(self.item['price']) if self.item else ""
            )
            
            yield Label("Količina:", classes="input-label")
            yield Input(
                placeholder="0.00",
                id="quantity-input",
                type="number",
                value=str(self.item['quantity']) if self.item else ""
            )
            
            yield Label("Barkod (opciono):", classes="input-label")
            yield Input(
                placeholder="Opciono...",
                id="barcode-input",
                value=self.item.get('barcode', '') if self.item else ""
            )
            
            with Horizontal(id="buttons"):
                yield Button("Sačuvaj [Enter]", id="save-btn", variant="success")
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")
    
    def on_mount(self) -> None:
        """Focus name input"""
        self.query_one("#name-input", Input).focus()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in any input"""
        if event.input.id in ["name-input", "price-input", "quantity-input", "barcode-input"]:
            self.action_save()
    
    def action_save(self) -> None:
        """Save item"""
        name = self.query_one("#name-input", Input).value.strip()
        price_str = self.query_one("#price-input", Input).value.strip()
        quantity_str = self.query_one("#quantity-input", Input).value.strip()
        barcode = self.query_one("#barcode-input", Input).value.strip()
        
        if not name:
            self.notify("Naziv artikla je obavezan!", severity="error")
            return
        
        try:
            price = float(price_str) if price_str else 0.0
            quantity = float(quantity_str) if quantity_str else 0.0
        except ValueError:
            self.notify("Cena i količina moraju biti brojevi!", severity="error")
            return
        
        if price < 0 or quantity < 0:
            self.notify("Cena i količina ne mogu biti negativni!", severity="error")
            return
        
        item_id = self.item['id'] if self.item else None
        barcode = barcode if barcode else None
        
        success, message, item_id = self.pos.add_or_update_inventory(
            item_name=name,
            price=price,
            quantity=quantity,
            item_id=item_id,
            barcode=barcode
        )
        
        if success:
            self.notify(message, severity="success")
            self.dismiss(True)
        else:
            self.notify(message, severity="error")
    
    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)


class ConfirmDeleteItemScreen(Screen):
    """Confirmation screen for deleting inventory item"""
    
    CSS = """
    ConfirmDeleteItemScreen {
        align: center middle;
    }
    
    #delete-dialog {
        width: 50;
        height: auto;
        max-height: 15;
        border: thick $error;
        background: $surface;
        padding: 2;
    }
    """
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, pos_service, item_id: int, item_name: str):
        super().__init__()
        self.pos = pos_service
        self.item_id = item_id
        self.item_name = item_name
    
    def compose(self) -> ComposeResult:
        with Vertical(id="delete-dialog"):
            yield Label("⚠️  BRISANJE ARTIKLA", classes="label")
            yield Static(
                f"Da li ste sigurni da želite da obrišete artikal:\n\n{self.item_name}?\n\nOva akcija je TRAJNA!",
                id="warning-text"
            )
            with Horizontal():
                yield Button("Obriši", id="confirm-btn", variant="error")
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="default")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            # Delete item - need to add delete method to repository
            # For now, just notify
            self.notify("Brisanje artikla - u izradi", severity="information")
            self.dismiss(False)  # TODO: Implement actual deletion
        elif event.button.id == "cancel-btn":
            self.dismiss(None)


class AddInvoiceScreen(Screen):
    """Screen for adding invoice with items"""
    
    CSS = """
    AddInvoiceScreen {
        background: $surface;
    }
    
    #invoice-container {
        height: 100%;
        padding: 1;
    }
    
    #items-table {
        height: 1fr;
        border: solid $primary;
    }
    
    #invoice-controls {
        dock: bottom;
        height: auto;
        background: $panel;
        padding: 1;
    }
    """
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("n", "add_item", "Add Item"),
        Binding("s", "save_invoice", "Save Invoice"),
    ]
    
    def __init__(self, pos_service):
        super().__init__()
        self.pos = pos_service
        self.invoice_items = []
    
    def compose(self) -> ComposeResult:
        with Vertical(id="invoice-container"):
            yield Label("📄 UNOS FAKTURE", classes="label")
            yield Input(placeholder="Broj fakture...", id="invoice-number-input")
            yield Label("Artikli:", classes="label")
            yield DataTable(id="items-table")
            
            with Horizontal(id="invoice-controls"):
                yield Button("Dodaj artikal [N]", id="add-item-btn", variant="success")
                yield Button("Sačuvaj fakturu [S]", id="save-btn", variant="primary")
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")
    
    def on_mount(self) -> None:
        """Setup table"""
        table = self.query_one("#items-table", DataTable)
        table.add_columns("Artikal", "Cena", "Količina", "Ukupno")
        table.cursor_type = "row"
        self.update_items_display()
        self.query_one("#invoice-number-input", Input).focus()
    
    def update_items_display(self) -> None:
        """Update items table"""
        table = self.query_one("#items-table", DataTable)
        table.clear()
        for item in self.invoice_items:
            total = item.price * item.quantity
            table.add_row(
                item.item_name,
                f"{item.price:.2f}",
                f"{item.quantity:.2f}",
                f"{total:.2f}"
            )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-item-btn":
            self.action_add_item()
        elif event.button.id == "save-btn":
            self.action_save_invoice()
        elif event.button.id == "cancel-btn":
            self.action_cancel()
    
    def action_add_item(self) -> None:
        """Add item to invoice"""
        self.app.push_screen(AddInvoiceItemScreen(), self.handle_item_added)
    
    def action_save_invoice(self) -> None:
        """Save invoice"""
        invoice_number = self.query_one("#invoice-number-input", Input).value.strip()
        
        if not invoice_number:
            self.notify("Broj fakture je obavezan!", severity="error")
            return
        
        if not self.invoice_items:
            self.notify("Faktura mora imati barem jedan artikal!", severity="error")
            return
        
        success, message, invoice_id = self.pos.create_invoice_from_items(
            invoice_number, self.invoice_items
        )
        
        if success:
            self.notify(message, severity="success")
            self.dismiss(True)
        else:
            self.notify(message, severity="error")
    
    def action_cancel(self) -> None:
        """Cancel"""
        self.dismiss(None)
    
    def handle_item_added(self, item: InvoiceItem) -> None:
        """Handle item added to invoice"""
        if item:
            self.invoice_items.append(item)
            self.update_items_display()
            self.notify(f"Dodato: {item.item_name}")


class AddInvoiceItemScreen(Screen):
    """Screen for adding item to invoice"""
    
    CSS = """
    AddInvoiceItemScreen {
        align: center middle;
    }
    
    #item-dialog {
        width: 50;
        height: auto;
        max-height: 37;
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
    """
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "add", "Add"),
    ]
    
    def compose(self) -> ComposeResult:
        with Vertical(id="item-dialog"):
            yield Label("➕ DODAJ ARTIKAL U FAKTURU", classes="label")
            
            yield Label("Naziv artikla:", classes="input-label")
            yield Input(placeholder="Unesite naziv...", id="name-input")
            
            yield Label("Cena (RSD):", classes="input-label")
            yield Input(placeholder="0.00", id="price-input", type="number")
            
            yield Label("Količina:", classes="input-label")
            yield Input(placeholder="0.00", id="quantity-input", type="number")
            
            yield Label("Barkod (opciono):", classes="input-label")
            yield Input(placeholder="Opciono...", id="barcode-input")
            
            with Horizontal():
                yield Button("Dodaj [Enter]", id="add-btn", variant="success")
                yield Button("Otkaži [ESC]", id="cancel-btn", variant="error")
    
    def on_mount(self) -> None:
        """Focus name input"""
        self.query_one("#name-input", Input).focus()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-btn":
            self.action_add()
        elif event.button.id == "cancel-btn":
            self.action_cancel()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter"""
        self.action_add()
    
    def action_add(self) -> None:
        """Add item"""
        from pos_business_logic import InvoiceItem
        
        name = self.query_one("#name-input", Input).value.strip()
        price_str = self.query_one("#price-input", Input).value.strip()
        quantity_str = self.query_one("#quantity-input", Input).value.strip()
        barcode = self.query_one("#barcode-input", Input).value.strip()
        
        if not name:
            self.notify("Naziv artikla je obavezan!", severity="error")
            return
        
        try:
            price = float(price_str) if price_str else 0.0
            quantity = float(quantity_str) if quantity_str else 0.0
        except ValueError:
            self.notify("Cena i količina moraju biti brojevi!", severity="error")
            return
        
        if price < 0 or quantity < 0:
            self.notify("Cena i količina ne mogu biti negativni!", severity="error")
            return
        
        item = InvoiceItem(
            item_name=name,
            price=price,
            quantity=quantity,
            barcode=barcode if barcode else None
        )
        
        self.dismiss(item)
    
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

        # Current logged in user
        self.current_user = None  # ← NEW

        # Shopping cart
        self.cart = []
        self.cart_total = 0.0

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Static("", id="user-info") # Shows logged-in user

        # Main container with horizontal layout
        with Horizontal(id="main-container"):
            # Left panel - Inventory
            with Vertical(id="inventory-panel"):
                yield Label("📦 INVENTAR", classes="label")
                yield Input(placeholder="Pretraga ili skeniranje...", id="search-input")
                yield DataTable(id="inventory-table")

            # Right panel - Shopping Cart
            with Vertical(id="cart-panel"):
                yield Label("🛒 KORPA", classes="label")
                yield DataTable(id="cart-table")
                yield Static("UKUPNO: 0.00 RSD", id="total-label")

        # Bottom controls
        with Horizontal(id="controls"):
            yield Button("Dodaj u korpu [Enter]", id="add-to-cart", variant="primary")
            yield Button("Ukloni [-]", id="remove-from-cart", variant="error")
            yield Button("Naplati [F5]", id="checkout", variant="success")
            yield Button("Očisti [C]", id="clear-cart")

        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts"""
        # Show login screen first
        self.push_screen(LoginScreen(self.user_service), self.handle_login)

    def action_user_management(self) -> None:
        """F8 - User Management (admin only)"""
        if not self.require_admin("Upravljanje korisnicima"):
            return

        self.push_screen(UserManagementScreen(self.user_service))

    def handle_login(self, user: dict) -> None:
        """Handle successful login"""
        if user:
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
            table.add_row(
                str(item['id']),
                item['item'],
                item['barcode'] or "",
                f"{item['price']:.2f}",
                f"{item['quantity']:.2f}"
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
                allow_oversell=False
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
        self.push_screen(InventoryManagementMenu())

    def action_reports(self) -> None:
        """F4 - Reports"""
        # Cashiers can see basic reports, admins see all
        if self.is_admin():
            # Admin sees full reports menu
            self.push_screen(AdminReportsMenu(self))
        else:
            # Cashier sees limited reports
            self.notify("Dnevni izveštaj - u izradi!", severity="information")

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
        Binding("y", "confirm_delete", "Confirm Delete"),
        Binding("escape", "cancel_delete", "Cancel Delete"),
    ]

    def __init__(self, user_service, user_id: int, username: str):
        super().__init__()
        self.user_service = user_service
        self.user_id = user_id
        self.username = username

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label("⚠️  BRISANJE KORISNIKA", classes="label")
            yield Static(f"Da li ste sigurni da želite da obrišete korisnika {self.username}?")
            with Horizontal(id="buttons"):
                yield Button("Da [Y]", id="confirm-btn", variant="success")
                yield Button("Ne [N]", id="cancel-btn", variant="error")


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