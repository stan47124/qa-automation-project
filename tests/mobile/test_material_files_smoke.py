import allure

from material_files import FilesScreen, resource
from mobile_config import PACKAGE


@allure.epic("QA.Guru graduation project")
@allure.feature("Mobile: Material Files")
@allure.story("Application smoke")
@allure.title("Application smoke")
def test_material_files_main_screen(mobile_driver):
    screen = FilesScreen(mobile_driver)
    screen.wait_ready()
    for name in ("toolbar", "breadcrumbLayout", "recyclerView", "action_search"):
        assert screen.visible(resource(name)).is_displayed()
    assert mobile_driver.current_package == PACKAGE
