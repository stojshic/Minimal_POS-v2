"""
Configuration for POS system
Store this info or load from settings file
"""

STORE_CONFIG = {
    "name": "Moja Prodavnica", # Your store name
    "address": "Dejana Brankova 26, Bela Crkva", # Store address
    "pib": "123123123", # Your PIB
    'pfr_number': "PFR-001", # Fiscal device number
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
    "low_stock_threshold": 10.0,  # Items below this trigger warnings
    "allow_oversell": True,  # Allow selling items with negative stock
    "show_low_stock_banner": False,  # Show persistent low stock banner
    "auto_print_receipt": False,  # Automatically print to printer (not implemented yet)
}
