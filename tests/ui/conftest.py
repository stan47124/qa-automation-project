import json
import os
import allure
import pytest
from selene import Browser, Config
from selenium import webdriver
from storefront import Storefront
from automation_exercise_diagnostics import attach_failure

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
            driver=driver, base_url="https://automationexercise.com", timeout=15,
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
def storefront(ui_browser):
    return Storefront(ui_browser)


@pytest.fixture
def product():
    # Verified against the product card and details, never selected by list order.
    return {
        "id": "1",
        "name": "Blue Top",
        "price": 500,
        "category": "Women > Tops",
        "brand": "Polo",
    }


@pytest.fixture
def upload_file(tmp_path):
    upload_path = tmp_path / "contact_upload.txt"
    upload_path.write_text("QA.Guru TXT upload: do not submit the contact form.", encoding="utf-8")
    return upload_path
