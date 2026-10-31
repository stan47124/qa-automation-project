import re
import shlex
import shutil
import subprocess
from uuid import uuid4

import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options

from material_files import FilesScreen
from mobile_config import (
    APP_ACTIVITY,
    APPIUM_URL,
    BASE_DIRECTORY,
    DEVICE,
    PACKAGE,
    TIMEOUT_SECONDS,
)


@pytest.fixture
def mobile_driver(request):
    options = UiAutomator2Options().load_capabilities(
        {
            "platformName": "Android",
            "appium:automationName": "UiAutomator2",
            "appium:udid": DEVICE,
            "appium:appPackage": PACKAGE,
            "appium:appActivity": APP_ACTIVITY,
            "appium:noReset": True,
            "appium:forceAppLaunch": True,
        }
    )
    driver = webdriver.Remote(APPIUM_URL, options=options)
    request.node._qa_drivers = {"Android": driver}
    try:
        yield driver
    finally:
        driver.quit()


@pytest.fixture
def adb_shell():
    """ADB is restricted to data preparation, independent checks and cleanup."""
    adb = shutil.which("adb")
    if adb is None:
        pytest.fail("adb was not found in PATH")

    def shell(command):
        result = subprocess.run(
            [adb, "-s", DEVICE, "shell", command],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, (
            f"ADB command failed: {command}\n{result.stdout}\n{result.stderr}"
        )
        return result.stdout

    return shell


@pytest.fixture
def mobile_workspace(adb_shell):
    """Own one unique directory; never modify the existing qa_guru/sample.txt."""
    adb_shell(f"test -d {shlex.quote(str(BASE_DIRECTORY))}")
    name = f"test_{uuid4().hex}"
    directory = BASE_DIRECTORY / name
    # mkdir without -p refuses to take ownership of an existing directory.
    adb_shell(f"mkdir {shlex.quote(str(directory))}")
    try:
        adb_shell(
            f"printf '%s\\n' {shlex.quote(name)} > "
            f"{shlex.quote(str(directory / 'sample.txt'))}"
        )
        yield name
    finally:
        # Restrict recursive cleanup to the direct child created above.
        assert directory.parent == BASE_DIRECTORY
        assert re.fullmatch(r"test_[0-9a-f]{32}", directory.name)
        adb_shell(f"rm -rf -- {shlex.quote(str(directory))}")
        adb_shell(f"test ! -e {shlex.quote(str(directory))}")


@pytest.fixture
def files_screen(mobile_workspace, mobile_driver):
    screen = FilesScreen(mobile_driver)
    screen.open_test_root()
    return screen
