import allure
from selene import be, have


@allure.epic("QA.Guru graduation project")
@allure.feature("Web UI: Automation Exercise")
@allure.story("Home page")
@allure.title("Главная страница доступна")
def test_home_page(storefront):
    storefront.open_home()
    browser = storefront.browser
    browser.should(have.url("https://automationexercise.com/"))
    browser.all("header a").element_by(have.exact_text("Home")).should(be.visible)
    browser.element('header a[href="/products"]').should(be.visible)


@allure.epic("QA.Guru graduation project")
@allure.feature("Web UI: Automation Exercise")
@allure.story("Products navigation")
@allure.title("Переход на страницу Products")
def test_products_navigation(storefront, product):
    storefront.open_products()
    storefront.browser.element("#search_product").should(be.visible)
    storefront.product_card(product).should(be.visible)


@allure.epic("QA.Guru graduation project")
@allure.feature("Web UI: Automation Exercise")
@allure.story("Product details")
@allure.title("Карточка выбранного товара и его данные")
def test_product_details(storefront, product):
    storefront.open_product(product)
    details = storefront.browser.element(".product-information")
    details.element("span > span").should(have.exact_text(f'Rs. {product["price"]}'))
    details.should(have.text(f'Category: {product["category"]}'))
    details.should(have.text("Availability: In Stock"))
    details.should(have.text("Condition: New"))
    details.should(have.text(f'Brand: {product["brand"]}'))
    details.element("#quantity").should(have.value("1"))


@allure.epic("QA.Guru graduation project")
@allure.feature("Web UI: Automation Exercise")
@allure.story("Add to cart")
@allure.title("Добавление товара в гостевую корзину")
def test_add_product_to_cart(storefront, product):
    storefront.open_product(product)
    storefront.add_to_cart()
    storefront.browser.element('#cartModal a[href="/view_cart"]').should(be.visible)
    storefront.browser.element("#cartModal .close-modal").should(be.clickable).click()
    storefront.browser.element("#cartModal").should(be.hidden)


@allure.epic("QA.Guru graduation project")
@allure.feature("Web UI: Automation Exercise")
@allure.story("Cart contents")
@allure.title("Товар, цена и количество в корзине")
def test_cart_product_and_quantity(storefront, product):
    storefront.open_product(product)
    storefront.add_to_cart()
    storefront.view_cart()
    storefront.assert_cart_product(product, quantity=1)


@allure.epic("QA.Guru graduation project")
@allure.feature("Web UI: Automation Exercise")
@allure.story("Select product quantity")
@allure.title("Выбор количества на странице товара и проверка корзины")
def test_selected_quantity_is_kept_in_cart(storefront, product):
    storefront.open_product(product)
    quantity = storefront.browser.element("#quantity")
    quantity.should(have.value("1")).set_value("4").should(have.value("4"))
    storefront.add_to_cart()
    storefront.view_cart()
    storefront.assert_cart_product(product, quantity=4)
