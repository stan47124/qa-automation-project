import allure
from selene import be, have

class CartPage:
    def __init__(self, browser):
        self.browser = browser

    def should_be_opened(self):
        self.browser.should(have.url("https://www.saucedemo.com/cart.html"))
        self.browser.element("#cart_contents_container").should(be.visible)

    @allure.step("Check the exact cart contents")
    def should_contain(self, product):
        self.should_be_opened()
        self.browser.all(".cart_item").should(have.size(1))
        row = self.browser.element(".cart_item")
        row.element(".inventory_item_name").should(have.exact_text(product.name))
        row.element(".inventory_item_price").should(have.exact_text(f"${product.price}"))
        row.element(".cart_quantity").should(have.exact_text("1"))
        self.browser.element(".shopping_cart_badge").should(have.exact_text("1"))

    @allure.step("Remove the selected product")
    def remove(self, product):
        self.browser.element(f"#remove-{product.slug}").should(be.clickable).click()

    @allure.step("Check that the cart is empty")
    def should_be_empty(self):
        self.should_be_opened()
        self.browser.all(".cart_item").should(have.size(0))
        self.browser.element(".shopping_cart_badge").should(be.absent)

    def checkout(self):
        self.browser.element('[data-test="checkout"]').should(be.clickable).click()
