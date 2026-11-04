import allure
import pytest
from saucedemo.data import STANDARD, INVALID, LOCKED
from saucedemo.inventory_page import InventoryPage

pytestmark = [allure.epic("QA.Guru graduation project"), allure.feature("Web UI: SauceDemo"),
              allure.parent_suite("Web UI"), allure.suite("SauceDemo"), allure.story("Authentication")]

@allure.id("SD-UI-001")
@allure.title("Successful demonstration login")
@allure.severity(allure.severity_level.CRITICAL)
def test_successful_login(login_page, ui_browser):
    login_page.open().submit(STANDARD)
    InventoryPage(ui_browser).should_be_opened()

@allure.id("SD-UI-002")
@allure.title("Reject invalid credentials")
@allure.severity(allure.severity_level.NORMAL)
def test_invalid_credentials(login_page):
    login_page.open().submit(INVALID)
    login_page.should_show_error("Epic sadface: Username and password do not match any user in this service")

@allure.id("SD-UI-003")
@allure.title("Reject the locked demonstration user")
@allure.severity(allure.severity_level.NORMAL)
def test_locked_out_user(login_page):
    login_page.open().submit(LOCKED)
    login_page.should_show_error("Epic sadface: Sorry, this user has been locked out.")
