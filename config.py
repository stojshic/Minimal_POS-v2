"""
Configuration for POS system
Store this info or load from settings file
"""

STORE_CONFIG = {
    "store_type": "shop",  # "shop" for retail POS, "restaurant" for table-based service
    "name": "Moja Prodavnica",  # Your store name
    "address": "Dejana Brankova 26, Bela Crkva",  # Store address
    "pib": "123123123",  # Your PIB
    "pfr_number": "PFR-001",  # Fiscal device number
    "cashier": "Kasir 1",
}

# Serbian VAT rates
VAT_RATES = {
    "standard": 0.20,   # 20% standard rate
    "reduced": 0.10,    # 10% reduced rate
    "zero": 0.00,       # 0% (books, some food items)
}

# POS System Configuration
CONFIG = {
    "low_stock_threshold": 10.0,     # Items below this trigger warnings
    "allow_oversell": True,          # Allow selling items with negative stock
    "show_low_stock_banner": True,   # Show persistent low stock banner
    "auto_print_receipt": False,     # Automatically print to printer (not implemented yet)
    "left_side": 23,    # For 42-char printers: left_side: 20, middle_side: 8, right_side: 14
    "middle_side": 9,   # For 48-char printers: left_side: 23, middle_side: 9, right_side: 16
    "right_side": 16,   # For 56-char printers: left_side: 28, middle_side: 10, right_side: 18

    # Session security
    "session_timeout_minutes": 30,   # Auto-logout after N minutes of inactivity (0 = disabled)
    "max_login_attempts": 5,         # Lock account after N failed login attempts
    "lockout_duration_minutes": 15,  # Account lockout duration after max failed attempts
}
