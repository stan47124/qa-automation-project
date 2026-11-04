import json

import allure
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from mobile_config import BASE_DIRECTORY, PACKAGE, TIMEOUT_SECONDS


def resource(name):
    return AppiumBy.ID, f"{PACKAGE}:id/{name}"


def text_resource(resource_name, text):
    return (
        AppiumBy.ANDROID_UIAUTOMATOR,
        f"new UiSelector().resourceId({json.dumps(f'{PACKAGE}:id/{resource_name}')})"
        f".text({json.dumps(text)})",
    )


class FilesScreen:
    """Small UI helper using locators verified on installed Material Files."""

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(
            driver, TIMEOUT_SECONDS, ignored_exceptions=(StaleElementReferenceException,)
        )

    @allure.step("Click the UI control: {locator}")
    def click(self, locator):
        def click_when_ready(driver):
            element = EC.element_to_be_clickable(locator)(driver)
            if not element:
                return False
            element.click()
            return True

        # Retry lookup and click together if a list redraw invalidates the element.
        self.wait.until(click_when_ready)

    @allure.step("Check visibility: {locator}")
    def visible(self, locator):
        return self.wait.until(EC.visibility_of_element_located(locator))

    @allure.step("Wait until the UI element is visible: {locator}")
    def wait_visible(self, locator):
        # Return the confirmed condition, not an element to query again outside
        # the wait. Each poll looks up the current node after a list redraw.
        return self.wait.until(lambda driver: driver.find_element(*locator).is_displayed())

    @allure.step("Open the context menu of file {name}")
    def open_file_menu(self, name):
        self.visible(text_resource("nameText", name))
        self.click(
            (
                AppiumBy.XPATH,
                f'//*[@resource-id="{PACKAGE}:id/nameText" and @text={json.dumps(name)}]'
                f'/ancestor::*[@resource-id="{PACKAGE}:id/itemLayout"][1]'
                f'//*[@resource-id="{PACKAGE}:id/menuButton"]',
            )
        )

    @allure.step("Open folder {name} and check its breadcrumb")
    def open_folder(self, name):
        selector = (
            f'new UiScrollable(new UiSelector().resourceId("{PACKAGE}:id/recyclerView"))'
            f'.scrollIntoView(new UiSelector().resourceId("{PACKAGE}:id/nameText")'
            f'.text({json.dumps(name)}))'
        )
        self.click((AppiumBy.ANDROID_UIAUTOMATOR, selector))
        self.visible(text_resource("text", name))

    @allure.step("Wait for Material Files")
    def wait_ready(self):
        explanation = (
            AppiumBy.XPATH,
            '//*[@resource-id="android:id/message" and '
            'starts-with(@text, "App needs permission to post notifications")]',
        )
        self.wait.until(
            EC.any_of(
                EC.visibility_of_element_located(resource("toolbar")),
                EC.visibility_of_element_located(explanation),
            )
        )
        if self.driver.find_elements(*explanation):
            self.click((AppiumBy.ID, "android:id/button2"))
            self.wait.until(EC.invisibility_of_element_located(explanation))

    @allure.step("Open the qa_guru directory")
    def open_test_root(self):
        self.wait_ready()
        self.click((AppiumBy.ACCESSIBILITY_ID, "Open navigation drawer"))
        self.click(text_resource("titleText", "Downloads"))
        self.open_folder(BASE_DIRECTORY.name)

    @allure.step("Enter {name} and confirm the name dialog")
    def submit_name(self, name):
        edit = self.visible(resource("nameEdit"))
        edit.clear()
        edit.send_keys(name)
        self.click((AppiumBy.ID, "android:id/button1"))
        self.wait.until(EC.invisibility_of_element_located(resource("nameEdit")))

    @allure.step("Create folder {name}")
    def create_folder(self, name):
        self.click(resource("sd_main_fab"))
        self.click((AppiumBy.ACCESSIBILITY_ID, "Folder"))
        self.visible(text_resource("alertTitle", "New folder"))
        self.submit_name(name)
        self.visible(text_resource("nameText", name))
