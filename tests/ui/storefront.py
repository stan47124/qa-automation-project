import allure
from selene import be, have


class Storefront:
    """Shared UI actions using selectors verified in Chrome's live DOM."""

    def __init__(self, browser):
        self.browser = browser

    @allure.step("Open the home page")
    def open_home(self):
        self.browser.open("/")
        self.browser.element(".features_items .title").should(have.exact_text("FEATURES ITEMS"))

    @allure.step("Navigate to Products from the home page")
    def open_products(self):
        self.open_home()
        self.browser.element('header a[href="/products"]').should(be.clickable).click()
        self.browser.should(have.url_containing("/products"))
        self.browser.element(".features_items .title").should(have.exact_text("ALL PRODUCTS"))

    @allure.step("Search for {name}")
    def search(self, name):
        self.browser.element("#search_product").should(be.visible).set_value(name)
        self.browser.element("#submit_search").should(be.clickable).click()
        self.browser.element(".features_items .title").should(have.exact_text("SEARCHED PRODUCTS"))

    @allure.step("Check the product card")
    def product_card(self, product):
        card = self.browser.element(
            f'.product-image-wrapper:has(.productinfo a[data-product-id="{product["id"]}"])'
        )
        card.element(".productinfo p").should(have.exact_text(product["name"]))
        return card

    @allure.step("Open the verified product card")
    def open_product(self, product):
        self.open_products()
        self.search(product["name"])
        self.product_card(product).element(
            f'a[href="/product_details/{product["id"]}"]'
        ).should(be.clickable).click()
        self.browser.should(have.url_containing(f'/product_details/{product["id"]}'))
        self.browser.element(".product-information h2").should(have.exact_text(product["name"]))
        self.browser.element("#product_id").should(have.value(product["id"]))

    @allure.step("Add the selected product to the guest cart")
    def add_to_cart(self):
        self.browser.element(".product-information button.cart").should(be.clickable).click()
        self.browser.element("#cartModal").should(be.visible)
        self.browser.element("#cartModal .modal-title").should(have.exact_text("Added!"))
        self.browser.element("#cartModal .modal-body").should(
            have.text("Your product has been added to cart.")
        )

    @allure.step("Open the guest cart")
    def view_cart(self):
        self.browser.element('#cartModal a[href="/view_cart"]').should(be.clickable).click()
        self.browser.should(have.url_containing("/view_cart"))
        self.browser.element("#cart_info_table").should(be.visible)

    @allure.step("Check cart contents: quantity {quantity}")
    def assert_cart_product(self, product, quantity):
        self.browser.all("#cart_info_table tbody tr").should(have.size(1))
        row = self.browser.element(f'#cart_info_table #product-{product["id"]}')
        row.element(f'.cart_description a[href="/product_details/{product["id"]}"]').should(
            have.exact_text(product["name"])
        )
        row.element(".cart_description p").should(have.exact_text(product["category"]))
        row.element(".cart_price p").should(have.exact_text(f'Rs. {product["price"]}'))
        row.element(".cart_quantity button").should(have.exact_text(str(quantity)))
        row.element(".cart_total_price").should(
            have.exact_text(f'Rs. {product["price"] * quantity}')
        )
