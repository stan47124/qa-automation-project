import allure

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC

from material_files import resource, text_resource
from mobile_config import BASE_DIRECTORY


@allure.epic("QA.Guru graduation project")
@allure.feature("Mobile: Material Files")
@allure.story("Open an isolated directory")
@allure.title("Open an isolated directory")
def test_open_qa_guru_folder(files_screen, mobile_workspace):
    # qa_guru was opened by the fixture; verify only this test's own sample.
    files_screen.open_folder(mobile_workspace)
    assert files_screen.visible(text_resource("nameText", "sample.txt")).is_displayed()


@allure.epic("QA.Guru graduation project")
@allure.feature("Mobile: Material Files")
@allure.story("Create a directory")
@allure.title("Create a directory")
def test_create_folder(files_screen, mobile_workspace):
    files_screen.open_folder(mobile_workspace)
    folder_name = f"created_{mobile_workspace}"
    assert not files_screen.driver.find_elements(*text_resource("nameText", folder_name))
    files_screen.create_folder(folder_name)
    assert files_screen.visible(text_resource("nameText", folder_name)).is_displayed()
    files_screen.open_folder(folder_name)


@allure.epic("QA.Guru graduation project")
@allure.feature("Mobile: Material Files")
@allure.story("Rename a file")
@allure.title("Rename a file")
def test_rename_file(files_screen, mobile_workspace):
    files_screen.open_folder(mobile_workspace)
    old_name = text_resource("nameText", "sample.txt")
    files_screen.visible(old_name)
    new_name = f"renamed_{mobile_workspace}.txt"
    assert not files_screen.driver.find_elements(*text_resource("nameText", new_name))
    files_screen.open_file_menu("sample.txt")
    files_screen.click(text_resource("title", "Rename"))
    files_screen.visible(text_resource("alertTitle", "Rename"))
    files_screen.submit_name(new_name)
    assert files_screen.visible(text_resource("nameText", new_name)).is_displayed()
    assert files_screen.wait.until(EC.invisibility_of_element_located(old_name))


@allure.epic("QA.Guru graduation project")
@allure.feature("Mobile: Material Files")
@allure.story("Copy a file")
@allure.title("Copy a file")
def test_copy_file(files_screen, mobile_workspace, adb_shell):
    directory = BASE_DIRECTORY / mobile_workspace
    original_content = adb_shell(f"cat {directory}/sample.txt")
    files_screen.open_folder(mobile_workspace)
    sample = text_resource("nameText", "sample.txt")
    files_screen.visible(sample)

    # Prepare an empty destination through the already verified creation UI.
    files_screen.create_folder("destination")

    files_screen.open_file_menu("sample.txt")
    files_screen.click(text_resource("title", "Copy"))
    files_screen.open_folder("destination")
    files_screen.visible(resource("emptyView"))
    assert not files_screen.driver.find_elements(*sample)
    files_screen.click(resource("action_paste"))
    assert files_screen.visible(sample).is_displayed()

    # Check that Copy kept the source, rather than moving it.
    files_screen.click(text_resource("text", mobile_workspace))
    assert files_screen.visible(sample).is_displayed()
    files_screen.open_folder("destination")
    assert files_screen.visible(sample).is_displayed()
    assert adb_shell(f"cat {directory}/sample.txt") == original_content
    assert adb_shell(f"cat {directory}/destination/sample.txt") == original_content


@allure.epic("QA.Guru graduation project")
@allure.feature("Mobile: Material Files")
@allure.story("Delete a file")
@allure.title("Delete a file")
def test_delete_file(files_screen, mobile_workspace, adb_shell):
    directory = BASE_DIRECTORY / mobile_workspace
    adb_shell(f"test -f {directory}/sample.txt")
    files_screen.open_folder(mobile_workspace)
    sample = text_resource("nameText", "sample.txt")
    files_screen.visible(sample)
    files_screen.open_file_menu("sample.txt")
    files_screen.click(text_resource("title", "Delete"))
    message = files_screen.visible((AppiumBy.ID, "android:id/message"))
    assert message.text.startswith("Delete ") and "sample.txt" in message.text
    files_screen.click((AppiumBy.ID, "android:id/button1"))
    files_screen.wait.until(
        EC.invisibility_of_element_located((AppiumBy.ID, "android:id/message"))
    )
    files_screen.visible(text_resource("text", mobile_workspace))
    assert files_screen.wait.until(EC.invisibility_of_element_located(sample))
    assert files_screen.visible(resource("emptyView")).is_displayed()
    adb_shell(f"test ! -e {directory}/sample.txt")
