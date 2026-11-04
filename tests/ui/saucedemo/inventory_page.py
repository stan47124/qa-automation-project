import allure
from collections import Counter
from selene import be, have
from selenium.webdriver.support.ui import Select
from .helpers import money

class InventoryPage:
    def __init__(self, browser):
        self.browser = browser

    @allure.step("Check the inventory page and its products")
    def should_be_opened(self):
        self.browser.should(have.url("https://www.saucedemo.com/inventory.html"))
        self.browser.element('[data-test="inventory-container"]').should(be.visible)
        self.browser.all(".inventory_item").should(have.size_greater_than(1))
        self.browser.element('[data-test="error"]').should(be.absent)

    def products(self):
        return [(row.find_element("css selector", ".inventory_item_name").text,
                 money(row.find_element("css selector", ".inventory_item_price").text))
                for row in self.browser.driver.find_elements("css selector", ".inventory_item")]

    @allure.step("Sort every product by price: {direction}")
    def sort_by_price(self, direction):
        control = self.browser.element('[data-test="product-sort-container"]').should(be.visible)
        Select(control.locate()).select_by_value(direction)

    @allure.step("Check the full sorted price list")
    def should_have_prices(self, expected, original_products):
        def matches(_):
            products = self.products()
            actual = [price for _, price in products]
            assert actual == expected, "The complete price order differs"
            assert Counter(products) == Counter(original_products), "The product set changed during sorting"
            return actual
        self.browser.wait.for_(matches)

    @allure.step("Add the selected product to the cart")
    def add(self, product):
        card = self.browser.all(".inventory_item").element_by(
            have.text(product.name)
        )
        card.element(".inventory_item_name").should(have.exact_text(product.name))
        card.element(".inventory_item_price").should(have.exact_text(f"${product.price}"))
        card.element(f"#add-to-cart-{product.slug}").should(be.clickable).click()
        card.element(f"#remove-{product.slug}").should(be.visible)
        self.browser.element(".shopping_cart_badge").should(have.exact_text("1"))

    def open_cart(self):
        self.browser.element(".shopping_cart_link").should(be.clickable).click()
