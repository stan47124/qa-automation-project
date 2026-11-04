from dataclasses import replace
import allure
import pytest
from saucedemo.data import BACKPACK, CUSTOMER

pytestmark = [allure.epic("QA.Guru graduation project"), allure.feature("Web UI: SauceDemo"),
              allure.parent_suite("Web UI"), allure.suite("SauceDemo"), allure.story("Checkout")]

@allure.id("SD-UI-007")
@allure.title("Complete a demonstration checkout")
@allure.severity(allure.severity_level.CRITICAL)
def test_complete_checkout(checkout_started):
    checkout = checkout_started
    checkout.fill(CUSTOMER)
    checkout.continue_to_overview()
    checkout.should_show_overview(BACKPACK)
    checkout.finish()
    checkout.should_be_complete()

@allure.id("SD-UI-008")
@allure.title("Validate every required checkout field independently")
@allure.severity(allure.severity_level.NORMAL)
def test_checkout_required_fields(checkout_started):
    for field, message in [
        ("first_name", "Error: First Name is required"),
        ("last_name", "Error: Last Name is required"),
        ("postal_code", "Error: Postal Code is required"),
    ]:
        with allure.step(f"Missing required field: {field}"):
            checkout_started.fill(replace(CUSTOMER, **{field: ""}))
            checkout_started.continue_to_overview()
            checkout_started.should_show_error(message)
