"""Allowlisted evidence; never capture login or full HTML."""
import json
from urllib.parse import urlsplit
import allure
from selenium.webdriver.common.by import By

KNOWN_TITLES = {"Swag Labs", "One moment, please...", "Just a moment...", "Секундочку…", "403 Forbidden", "Access Denied"}
CONTAINERS = {
    "/inventory.html": '[data-test="inventory-container"]',
    "/cart.html": "#cart_contents_container",
    "/checkout-step-one.html": "#checkout_info_container",
    "/checkout-step-two.html": "#checkout_summary_container",
    "/checkout-complete.html": "#checkout_complete_container",
}
PAGE_FLAGS = """
return {
  document_ready: document.readyState === 'complete',
  catalog_marker: !!document.querySelector('[data-test="inventory-container"]'),
  cart_marker: !!document.querySelector('#cart_contents_container'),
  checkout_marker: !!document.querySelector('#checkout_info_container,#checkout_summary_container,#checkout_complete_container'),
  login_marker: !!document.querySelector('#login-button,#user-name'),
  password_input: !!document.querySelector('input[type="password"]'),
  challenge_title: /one moment|just a moment|секундочку|access denied|403 forbidden/i.test(document.title),
  challenge_message: /verify you are human|checking your browser|запрос будет проверен/i.test(document.body?.innerText || ''),
  captcha: [...document.querySelectorAll('iframe[src*="captcha"],iframe[title*="challenge"]')].some(e => e.getBoundingClientRect().height > 0)
};
"""

def safe_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname != "www.saucedemo.com":
            return "[unexpected URL omitted]"
        path = parsed.path if parsed.path in {"/", *CONTAINERS} else "/[other path omitted]"
        return "https://www.saucedemo.com" + path
    except (TypeError, ValueError):
        return "[invalid URL omitted]"

def browser_state(driver):
    flags = driver.execute_script(PAGE_FLAGS)
    result = {key: flags.get(key) is True for key in (
        "document_ready", "catalog_marker", "cart_marker", "checkout_marker",
        "login_marker", "password_input", "challenge_title", "challenge_message", "captcha",
    )}
    title = driver.title
    result.update(url=safe_url(driver.current_url),
                  title=title if title in KNOWN_TITLES else "[unrecognized title omitted]")
    result["request_check_page"] = result["challenge_title"] or result["challenge_message"] or result["captcha"]
    return result

def attach_browser_state(driver, phase):
    try:
        state = browser_state(driver)
    except Exception as error:
        state = {"diagnostic_error_type": type(error).__name__}
    try:
        allure.attach(json.dumps(state, ensure_ascii=False),
                      name=f"Web UI: {phase} page state (allowlisted)",
                      attachment_type=allure.attachment_type.JSON)
    except Exception:
        pass

def attach_failure(driver, phase):
    attach_browser_state(driver, phase)
    try:
        state = browser_state(driver)
        path = urlsplit(state["url"]).path
        if state["title"] != "Swag Labs" or path not in CONTAINERS or state["login_marker"] or state["password_input"] or state["request_check_page"]:
            return
        # Container screenshot excludes the login footer; stale lookup fails safely.
        png = driver.find_element(By.CSS_SELECTOR, CONTAINERS[path]).screenshot_as_png
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Expected PNG evidence")
        allure.attach(png, name=f"Web UI: {phase} safe page container",
                      attachment_type=allure.attachment_type.PNG)
    except Exception as error:
        try:
            allure.attach(type(error).__name__, name="Web UI: screenshot diagnostic",
                          attachment_type=allure.attachment_type.TEXT)
        except Exception:
            pass
