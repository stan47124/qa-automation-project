import allure
from selene import have


@allure.epic("QA.Guru graduation project")
@allure.feature("Web UI: Automation Exercise")
@allure.story("Product search")
@allure.title("Search for an existing product")
def test_search_for_existing_product(storefront, product):
    storefront.open_products()
    storefront.search(product["name"])
    storefront.browser.all(".features_items .productinfo p").should(
        have.exact_texts(product["name"])
    )
    storefront.product_card(product)
