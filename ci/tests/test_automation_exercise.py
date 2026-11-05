"""Safety of restored Web UI evidence, without contacting a browser/site."""
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/ui'))
import automation_exercise_diagnostics as diagnostic


@pytest.mark.parametrize('raw,expected', [
    ('https://private:private@automationexercise.com/products?token=private#private',
     'https://automationexercise.com/products'),
    ('https://automationexercise.com/private', 'https://automationexercise.com/[other path omitted]'),
    ('https://other.example/private', '[unexpected URL omitted]'),
])
def test_url_omits_private_components(raw, expected):
    assert diagnostic.safe_url(raw) == expected


@pytest.mark.parametrize('path,flags', [
    ('/contact_us', {}), ('/', {'contact': True}), ('/', {'password': True}),
    ('/products', {'challenge': True}), ('/view_cart', {'captcha': True}),
])
def test_sensitive_or_blocked_pages_never_produce_screenshots(path, flags, monkeypatch):
    driver = Mock(title='Automation Exercise', current_url='https://automationexercise.com'+path)
    driver.execute_script.return_value = flags
    attach = Mock()
    monkeypatch.setattr(diagnostic.allure, 'attach', attach)
    diagnostic.attach_failure(driver, 'call')
    driver.find_element.assert_not_called()
    driver.get_screenshot_as_png.assert_not_called()


def test_public_catalog_uses_container_only(monkeypatch):
    driver = Mock(title='Automation Exercise', current_url='https://automationexercise.com/')
    driver.execute_script.return_value = {'catalog': True}
    driver.find_element.return_value.screenshot_as_png = b'\x89PNG\r\n\x1a\nunit'
    attach = Mock()
    monkeypatch.setattr(diagnostic.allure, 'attach', attach)
    diagnostic.attach_failure(driver, 'call')
    driver.find_element.assert_called_once_with('css selector', '.features_items')
    driver.get_screenshot_as_png.assert_not_called()
    assert json.loads(attach.call_args_list[0].args[0])['catalog'] is True


def test_diagnostic_failures_do_not_replace_test_error_or_save_payload(monkeypatch):
    driver = Mock()
    driver.execute_script.side_effect = RuntimeError('private-payload')
    attach = Mock(side_effect=OSError('private-payload'))
    monkeypatch.setattr(diagnostic.allure, 'attach', attach)
    original = AssertionError('original assertion')
    with pytest.raises(AssertionError) as captured:
        try:
            raise original
        finally:
            diagnostic.attach_failure(driver, 'call')
    assert captured.value is original
    assert all('private-payload' not in call.args[0] for call in attach.call_args_list)
