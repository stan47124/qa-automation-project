import allure
from decimal import Decimal
from selene import be, have
from selenium.webdriver.common.keys import Keys
from .helpers import label_money

class CheckoutPage:
    def __init__(self, browser):
        self.browser = browser

    def should_show_information(self):
        self.browser.should(have.url("https://www.saucedemo.com/checkout-step-one.html"))
        self.browser.element("#checkout_info_container").should(be.visible)

    @allure.step("Fill synthetic checkout information")
    def fill(self, customer):
        self.should_show_information()
        # Keyboard input notifies React even when the desired value is empty.
        # Restore every field rather than relying on the previous validation case.
        for selector, value in [("#first-name", customer.first_name),
                                ("#last-name", customer.last_name),
                                ("#postal-code", customer.postal_code)]:
            element = self.browser.element(selector).should(be.visible)
            element.send_keys(Keys.CONTROL, "a", Keys.NULL, Keys.BACKSPACE)
            if value:
                element.type(value)
            element.should(have.value(value))

    def continue_to_overview(self):
        self.browser.element('[data-test="continue"]').should(be.clickable).click()

    @allure.step("Check checkout validation")
    def should_show_error(self, message):
        self.should_show_information()
        self.browser.element('[data-test="error"]').should(have.exact_text(message))
        self.browser.element("#checkout_summary_container").should(be.absent)

    @allure.step("Check order overview, product and monetary totals")
    def should_show_overview(self, product):
        self.browser.should(have.url("https://www.saucedemo.com/checkout-step-two.html"))
        self.browser.element("#checkout_summary_container").should(be.visible)
        self.browser.all(".cart_item").should(have.size(1))
        row = self.browser.element(".cart_item")
        row.element(".inventory_item_name").should(have.exact_text(product.name))
        row.element(".cart_quantity").should(have.exact_text("1"))
        row.element(".inventory_item_price").should(have.exact_text(f"${product.price}"))
        subtotal = label_money(self.browser.element(".summary_subtotal_label").locate().text, "Item total:")
        tax = label_money(self.browser.element(".summary_tax_label").locate().text, "Tax:")
        total = label_money(self.browser.element(".summary_total_label").locate().text, "Total:")
        assert subtotal == product.price
        assert tax == (subtotal * Decimal("0.08")).quantize(Decimal("0.01"))
        assert total == subtotal + tax

    def finish(self):
        self.browser.element('[data-test="finish"]').should(be.clickable).click()

    @allure.step("Check successful order completion and cleared cart")
    def should_be_complete(self):
        self.browser.should(have.url("https://www.saucedemo.com/checkout-complete.html"))
        self.browser.element("#checkout_complete_container").should(be.visible)
        self.browser.element(".complete-header").should(have.exact_text("Thank you for your order!"))
        self.browser.element(".shopping_cart_badge").should(be.absent)
        self.browser.element('[data-test="back-to-products"]').should(be.clickable).click()
        self.browser.element(".shopping_cart_link").should(be.clickable).click()
        self.browser.should(have.url("https://www.saucedemo.com/cart.html"))
        self.browser.element("#cart_contents_container").should(be.visible)
        self.browser.all(".cart_item").should(have.size(0))
