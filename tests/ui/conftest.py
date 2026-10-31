from pathlib import Path

import pytest
from selene import Browser, Config
from selenium import webdriver

from storefront import Storefront


@pytest.fixture
def ui_browser(tmp_path, request):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-notifications")
    # ChromeDriver creates a separate temporary profile for each new session.
    driver = webdriver.Chrome(options=options)
    request.node._qa_drivers = {"Web UI": driver}
    try:
        driver.set_page_load_timeout(45)
        yield Browser(
            Config(
                driver=driver,
                base_url="https://automationexercise.com",
                timeout=15,
                reports_folder=str(tmp_path / "selene"),
                save_screenshot_on_failure=True,
                # Full HTML may contain CSRF tokens; do not save it to reports.
                save_page_source_on_failure=False,
            )
        )
    finally:
        driver.quit()


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
def upload_file(tmp_path: Path):
    upload_path = tmp_path / "contact_upload.txt"
    upload_path.write_text("QA.Guru TXT upload: do not submit the contact form.", encoding="utf-8")
    return upload_path
