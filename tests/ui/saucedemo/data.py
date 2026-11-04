from dataclasses import dataclass, field
from decimal import Decimal

BASE_URL = "https://www.saucedemo.com"

@dataclass(frozen=True)
class DemoUser:
    role: str
    username: str = field(repr=False)
    password: str = field(repr=False)

# Public training accounts published by SauceDemo; never user credentials.
STANDARD = DemoUser("standard", "standard_user", "secret_sauce")
INVALID = DemoUser("invalid", "standard_user", "intentionally_invalid_demo_password")
LOCKED = DemoUser("locked", "locked_out_user", "secret_sauce")

@dataclass(frozen=True)
class Product:
    slug: str
    name: str
    price: Decimal

BACKPACK = Product("sauce-labs-backpack", "Sauce Labs Backpack", Decimal("29.99"))

@dataclass(frozen=True)
class Customer:
    first_name: str
    last_name: str
    postal_code: str

CUSTOMER = Customer("QA", "Student", "101000")
