import allure
import pytest

pytestmark = [allure.epic("QA.Guru graduation project"), allure.feature("Web UI: SauceDemo"),
              allure.parent_suite("Web UI"), allure.suite("SauceDemo"), allure.story("Inventory")]

@allure.id("SD-UI-004")
@allure.title("Sort all products by price in both directions")
@allure.severity(allure.severity_level.NORMAL)
def test_sort_products_by_price(authenticated_inventory):
    inventory = authenticated_inventory
    products = inventory.products()
    original = [price for _, price in products]
    assert len(original) > 1 and len(set(original)) > 1
    for direction, expected in [("lohi", sorted(original)), ("hilo", sorted(original, reverse=True))]:
        with allure.step(f"Check price sorting: {direction}"):
            inventory.sort_by_price(direction)
            inventory.should_have_prices(expected, products)
