import allure
import json
from decimal import Decimal
from time import monotonic
from selene import be, have
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from .helpers import label_money

class CheckoutPage:
    def __init__(self, browser):
        self.browser = browser

    def should_show_information(self):
        self.browser.should(have.url("https://www.saucedemo.com/checkout-step-one.html"))
        self.browser.element("#checkout_info_container").should(be.visible)

    def fill(self, customer):
        # A context step does not serialize the customer's field values.
        with allure.step("Fill synthetic checkout information"):
            self.should_show_information()
            for selector, value in [("#first-name", customer.first_name),
                                    ("#last-name", customer.last_name),
                                    ("#postal-code", customer.postal_code)]:
                self._fill_field(selector, value)

    def _fill_field(self, selector, value):
        driver = self.browser.config.driver
        wait = WebDriverWait(
            driver, self.browser.config.timeout, poll_frequency=0.1,
            ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
        )

        def locate():
            return driver.find_element(By.CSS_SELECTOR, selector)

        def focused():
            return driver.execute_script(
                "return document.activeElement === arguments[0]", locate()
            )

        def ready(_):
            element = locate()
            return element.is_displayed() and element.is_enabled()

        def matches(expected):
            # Only reads are polled; every poll resolves the current DOM element.
            return lambda _: locate().get_property("value") == expected

        stage, expected = "availability", value
        started = stage_started = monotonic()
        try:
            wait.until(ready, "Checkout field is not available for input")
            stage, expected, stage_started = "clear", "", monotonic()
            # Actions deliberately bypass Selene's retrying command wrapper.
            # Addressed Selenium send_keys focuses the field; no preliminary click
            # or activeElement precondition is needed for keyboard input.
            locate().send_keys(Keys.CONTROL, "a", Keys.NULL, Keys.BACKSPACE)
            wait.until(matches(""), "Checkout field did not become empty")
            if value:
                stage, expected, stage_started = "input", value, monotonic()
                locate().send_keys(value)
            stage, expected, stage_started = "verify", value, monotonic()
            wait.until(matches(value), "Checkout field does not match the expected value")
        except Exception:
            # Diagnostics are best effort and never replace the original exception.
            try:
                evidence = {
                    "stage": stage, "field": selector,
                    "expected_state": "nonempty" if expected else "empty",
                    "expected_match": None, "focused": None, "document_focused": None,
                    "stage_elapsed_s": round(monotonic() - stage_started, 3),
                    "field_elapsed_s": round(monotonic() - started, 3),
                }
                for key, read in [
                    ("expected_match", lambda: locate().get_property("value") == expected),
                    ("focused", lambda: bool(focused())),
                    ("document_focused", lambda: bool(driver.execute_script("return document.hasFocus()"))),
                ]:
                    try:
                        evidence[key] = read()
                    except Exception:
                        pass
                allure.attach(json.dumps(evidence), name="Checkout field operation",
                              attachment_type=allure.attachment_type.JSON)
            except Exception:
                pass
            raise

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
