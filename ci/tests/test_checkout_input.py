"""Exercise checkout state waits with fresh DOM handles and one-shot actions."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.keys import Keys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests/ui"))
from saucedemo.checkout_page import CheckoutPage
import saucedemo.checkout_page as checkout_module


class FieldDriver:
    def __init__(self, *, clear=True, enter=True, available=True):
        self.value = "previous-private-marker"
        self.clear_ok, self.enter_ok = clear, enter
        self.available = available
        self.focused = False
        self.focus_queries = 0
        self.actions = []
        self.reads = []
        self.handles = []
        self.stale_reads = 0
        self.delayed_clear_reads = 0

    def find_element(self, by, selector):
        handle = FieldHandle(self)
        self.handles.append(handle)
        return handle

    def execute_script(self, script, *args):
        self.focus_queries += 1
        return self.focused


class FieldHandle:
    def __init__(self, driver):
        self.driver = driver

    def is_displayed(self):
        return self.driver.available

    def is_enabled(self):
        return self.driver.available

    def click(self):
        raise AssertionError("A preliminary click is not required")

    def send_keys(self, *keys):
        driver = self.driver
        if keys == (Keys.CONTROL, "a", Keys.NULL, Keys.BACKSPACE):
            driver.actions.append("clear")
            if driver.clear_ok:
                driver.value = ""
        else:
            # Input must follow an observed empty state, not merely a clear command.
            assert driver.reads and driver.reads[-1] == ""
            driver.actions.append("input")
            if driver.enter_ok:
                driver.value += "".join(keys)

    def get_property(self, name):
        assert name == "value"
        driver = self.driver
        if driver.stale_reads:
            driver.stale_reads -= 1
            raise StaleElementReferenceException("private-stale-marker")
        if driver.delayed_clear_reads and driver.actions[-1] == "clear":
            driver.delayed_clear_reads -= 1
            result = "previous-private-marker"
        else:
            result = driver.value
        driver.reads.append(result)
        return result


def page(driver):
    return CheckoutPage(SimpleNamespace(config=SimpleNamespace(driver=driver, timeout=0.25)))


@pytest.fixture
def attachments(monkeypatch):
    attach = Mock()
    monkeypatch.setattr(checkout_module.allure, "attach", attach)
    return attach


def test_clear_and_input_are_once_and_input_follows_confirmed_empty(attachments):
    driver = FieldDriver()
    driver.delayed_clear_reads = 1
    page(driver)._fill_field("#last-name", "target-private-marker")
    assert driver.actions == ["clear", "input"]
    assert driver.reads == ["previous-private-marker", "", "target-private-marker"]
    assert driver.focus_queries == 0
    attachments.assert_not_called()


def test_empty_target_is_verified_without_input(attachments):
    driver = FieldDriver()
    page(driver)._fill_field("#last-name", "")
    assert driver.actions == ["clear"]
    assert driver.reads == ["", ""]


def test_successful_fill_needs_neither_focus_check_nor_preliminary_click(attachments):
    driver = FieldDriver()
    driver.execute_script = Mock(side_effect=AssertionError("Focus is diagnostic only"))
    page(driver)._fill_field("#last-name", "target-private-marker")
    assert driver.actions == ["clear", "input"]
    driver.execute_script.assert_not_called()
    attachments.assert_not_called()


def test_stale_read_resolves_a_new_dom_handle_without_repeating_actions(attachments):
    driver = FieldDriver()
    driver.stale_reads = 1
    page(driver)._fill_field("#last-name", "target-private-marker")
    assert driver.actions == ["clear", "input"]
    assert len(driver.handles) == len({id(handle) for handle in driver.handles})
    assert len(driver.handles) >= 5
    assert driver.focus_queries == 0
    attachments.assert_not_called()


@pytest.mark.parametrize("options,stage,actions", [
    ({"clear": False}, "clear", ["clear"]),
    ({"enter": False}, "verify", ["clear", "input"]),
    ({"available": False}, "availability", []),
])
def test_failed_state_times_out_with_safe_evidence(options, stage, actions, attachments):
    driver = FieldDriver(**options)
    with pytest.raises(TimeoutException) as captured:
        page(driver)._fill_field("#last-name", "target-private-marker")
    assert driver.actions == actions
    evidence = json.loads(attachments.call_args.args[0])
    assert evidence["stage"] == stage
    assert evidence["field"] == "#last-name"
    assert evidence["expected_match"] is False
    assert isinstance(evidence["focused"], bool)
    assert evidence["stage_elapsed_s"] >= 0
    assert evidence["field_elapsed_s"] >= evidence["stage_elapsed_s"]
    for marker in ["previous-private-marker", "target-private-marker"]:
        assert marker not in str(captured.value)
        assert marker not in attachments.call_args.args[0]


def test_final_value_requires_exact_equality_not_substring(attachments):
    driver = FieldDriver()
    original_send = FieldHandle.send_keys

    def append_unexpected_suffix(handle, *keys):
        original_send(handle, *keys)
        if handle.driver.actions[-1] == "input":
            handle.driver.value += "-unexpected"

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(FieldHandle, "send_keys", append_unexpected_suffix)
        with pytest.raises(TimeoutException):
            page(driver)._fill_field("#last-name", "target-private-marker")
    assert driver.actions == ["clear", "input"]
    assert json.loads(attachments.call_args.args[0])["expected_match"] is False


def test_attachment_error_does_not_replace_original_exception(attachments):
    driver = FieldDriver()
    original = TimeoutException("original operation failure")
    driver.find_element = Mock(side_effect=original)
    attachments.side_effect = OSError("private-diagnostic-marker")
    with pytest.raises(TimeoutException) as captured:
        page(driver)._fill_field("#last-name", "target-private-marker")
    assert captured.value is original
    attachments.assert_called_once()
    evidence = json.loads(attachments.call_args.args[0])
    assert evidence["expected_match"] is None
    assert evidence["focused"] is None
    assert "private-diagnostic-marker" not in str(captured.value)


@pytest.mark.parametrize("operation", ["clear", "input"])
def test_command_timeout_is_not_retried_or_replaced(operation, attachments, monkeypatch):
    driver = FieldDriver()
    original = TimeoutException("original keyboard operation failure")
    send = FieldHandle.send_keys

    def fail_input(handle, *keys):
        current = "clear" if Keys.BACKSPACE in keys else "input"
        if current == operation:
            handle.driver.actions.append(current)
            raise original
        return send(handle, *keys)

    monkeypatch.setattr(FieldHandle, "send_keys", fail_input)
    with pytest.raises(TimeoutException) as captured:
        page(driver)._fill_field("#last-name", "target-private-marker")
    assert captured.value is original
    assert driver.actions == (["clear"] if operation == "clear" else ["clear", "input"])
    assert json.loads(attachments.call_args.args[0])["stage"] == operation
