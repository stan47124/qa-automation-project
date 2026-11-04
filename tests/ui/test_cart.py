import allure
import pytest
from selene import be
from saucedemo.data import BACKPACK

pytestmark = [allure.epic("QA.Guru graduation project"), allure.feature("Web UI: SauceDemo"),
              allure.parent_suite("Web UI"), allure.suite("SauceDemo"), allure.story("Cart")]

@allure.id("SD-UI-005")
@allure.title("Add Backpack and verify the cart")
@allure.severity(allure.severity_level.CRITICAL)
def test_add_product_to_cart(authenticated_inventory, cart_page):
    cart_page.browser.element(".shopping_cart_badge").should(be.absent)
    authenticated_inventory.add(BACKPACK)
    authenticated_inventory.open_cart()
    cart_page.should_contain(BACKPACK)

@allure.id("SD-UI-006")
@allure.title("Remove Backpack and verify the empty cart")
@allure.severity(allure.severity_level.CRITICAL)
def test_remove_product_from_cart(cart_with_backpack):
    cart_with_backpack.remove(BACKPACK)
    cart_with_backpack.should_be_empty()
