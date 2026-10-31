import allure
from selene import be, have


@allure.epic("QA.Guru graduation project")
@allure.feature("Web UI: Automation Exercise")
@allure.story("Attach TXT without submission")
@allure.step("Fill the contact fields and verify the selected TXT without submitting")
@allure.title("Attach a TXT file without submitting Contact Us")
def test_contact_us_file_upload(ui_browser, upload_file):
    ui_browser.open("/contact_us")
    ui_browser.element(".contact-form h2").should(have.exact_text("GET IN TOUCH"))
    ui_browser.element('[data-qa="name"]').should(be.visible).set_value("QA Guru Student")
    ui_browser.element('[data-qa="email"]').set_value("qa-guru-diagnostic@example.com")
    ui_browser.element('[data-qa="subject"]').set_value("Diagnostic file upload")
    ui_browser.element('[data-qa="message"]').set_value(
        "The form is intentionally not submitted."
    )
    upload = ui_browser.element('input[type="file"][name="upload_file"]')
    upload.send_keys(str(upload_file.resolve()))
    upload.should(have.value_containing(upload_file.name))
    # Read only the selected filename/size; never submit or click Submit.
    selected = ui_browser.driver.execute_script(
        "return {count: arguments[0].files.length, name: arguments[0].files[0].name, "
        "size: arguments[0].files[0].size}",
        upload.locate(),
    )
    assert selected == {"count": 1, "name": upload_file.name, "size": upload_file.stat().st_size}
    ui_browser.should(have.url_containing("/contact_us"))
    ui_browser.element("#contact-us-form").should(be.visible)
    ui_browser.element(".contact-form .status").should(be.hidden)
