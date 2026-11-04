import json
import os
import allure
import pytest
from selene import Browser, Config
from selenium import webdriver
from saucedemo.data import BASE_URL, STANDARD, BACKPACK
from saucedemo.login_page import LoginPage
from saucedemo.inventory_page import InventoryPage
from saucedemo.cart_page import CartPage
from saucedemo.checkout_page import CheckoutPage
from web_diagnostics import attach_failure

@pytest.fixture
def ui_browser(tmp_path, request):
    headless = os.getenv("HEADLESS", "false").strip().lower() in {"true", "1", "yes"}
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-notifications")
    driver = webdriver.Chrome(options=options)
    # Do not register Web in the root hook's raw screenshot registry.
    request.node._qa_failure_diagnostics = {
        "Web UI evidence": lambda phase: attach_failure(driver, phase),
    }
    lifecycle = {
        "headless": headless, "created": True, "closed": False,
        "chrome": driver.capabilities.get("browserVersion"),
        "chromedriver": driver.capabilities.get("chrome", {}).get("chromedriverVersion", "").split(" ")[0],
        "profile_instance": os.path.basename(driver.capabilities.get("chrome", {}).get("userDataDir", "")),
    }
    try:
        driver.set_page_load_timeout(45)
        yield Browser(Config(
            driver=driver, base_url=BASE_URL, timeout=15,
            reports_folder=str(tmp_path / "selene"),
            save_screenshot_on_failure=False, save_page_source_on_failure=False,
            log_outer_html_on_failure=False,
        ))
    finally:
        try:
            driver.quit()
            lifecycle["closed"] = True
        except Exception as error:
            lifecycle["cleanup_error_type"] = type(error).__name__
            raise
        finally:
            try:
                allure.attach(json.dumps(lifecycle), name="Web UI: session lifecycle",
                              attachment_type=allure.attachment_type.JSON)
            except Exception:
                pass

@pytest.fixture
def login_page(ui_browser):
    return LoginPage(ui_browser)

@pytest.fixture
def authenticated_inventory(login_page, ui_browser):
    login_page.open().submit(STANDARD)
    page = InventoryPage(ui_browser)
    page.should_be_opened()
    return page

@pytest.fixture
def cart_page(ui_browser):
    return CartPage(ui_browser)

@pytest.fixture
def cart_with_backpack(authenticated_inventory, cart_page):
    authenticated_inventory.add(BACKPACK)
    authenticated_inventory.open_cart()
    cart_page.should_contain(BACKPACK)
    return cart_page

@pytest.fixture
def checkout_started(cart_with_backpack, ui_browser):
    cart_with_backpack.checkout()
    page = CheckoutPage(ui_browser)
    page.should_show_information()
    return page
