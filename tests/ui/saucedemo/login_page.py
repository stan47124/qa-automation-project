import allure
from selene import be, have
from selenium.common.exceptions import WebDriverException

class LoginPage:
    def __init__(self, browser):
        self.browser = browser

    @allure.step("Open the demonstration login form")
    def open(self):
        self.browser.open("/")
        self.should_be_opened()
        return self

    def should_be_opened(self):
        self.browser.element("#login-button").should(be.visible)
        self.browser.element("#user-name").should(be.visible)
        self.browser.element("#password").should(be.visible)

    @allure.step("Submit demonstration login")
    def submit(self, user):
        # user repr excludes BOTH fields. No password-bearing Selene command,
        # Allure step argument or exception message is allowed.
        self.should_be_opened()
        try:
            username = self.browser.element("#user-name").locate()
            username.clear()
            username.send_keys(user.username)
            password = self.browser.element("#password").locate()
            password.clear()
            password.send_keys(user.password)
        except WebDriverException as error:
            raise type(error)("Demonstration login input operation failed") from None
        self.browser.element("#login-button").should(be.clickable).click()

    @allure.step("Check the expected login error")
    def should_show_error(self, expected):
        self.browser.element('[data-test="error"]').should(have.exact_text(expected))
        self.browser.should(have.url("https://www.saucedemo.com/"))
        self.browser.element("#inventory_container").should(be.absent)
        self.should_be_opened()
