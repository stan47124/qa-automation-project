import importlib.util
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest
from selenium.common.exceptions import WebDriverException

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tests/ui'), str(ROOT / 'ci')]
from saucedemo.helpers import money, label_money
from saucedemo.data import DemoUser
from saucedemo.login_page import LoginPage
from saucedemo.inventory_page import InventoryPage
import web_diagnostics as diagnostic
from check_allure_metadata import compare_identities


@pytest.mark.parametrize('text,expected', [('$29.99', Decimal('29.99')), ('$0.10', Decimal('0.10')), (' $49.99 ', Decimal('49.99'))])
def test_money_keeps_exact_decimal_values(text, expected):
    assert money(text) == expected
    assert isinstance(money(text), Decimal)


@pytest.mark.parametrize('text', ['29.99', '$29.999', '$NaN', '$1e2', '$-1.00', 'unit-secret'])
def test_money_rejects_invalid_amount_without_echoing_input(text):
    with pytest.raises(ValueError) as failure:
        money(text)
    assert text not in str(failure.value)


def test_label_money_does_not_accept_another_total_field():
    assert label_money('Tax: $2.40', 'Tax:') == Decimal('2.40')
    with pytest.raises(ValueError):
        label_money('Total: $32.39', 'Tax:')


def test_credentials_and_input_errors_are_not_serialized():
    user = DemoUser('unit', 'unit-username-marker', 'unit-password-marker')
    assert user.username not in repr(user) and user.password not in repr(user)
    browser = Mock()
    browser.element.return_value.locate.return_value.send_keys.side_effect = WebDriverException('unit-password-marker')
    with pytest.raises(WebDriverException) as failure:
        LoginPage(browser).submit(user)
    assert user.password not in str(failure.value)
    assert user.username not in str(failure.value)


def test_sort_condition_reads_current_full_list_until_correct():
    page = InventoryPage(Mock())
    expected = [Decimal('7.99'), Decimal('29.99')]
    products = [("First", expected[0]), ("Second", expected[1])]
    page.products = Mock(side_effect=[list(reversed(products)), products])
    def until(condition):
        with pytest.raises(AssertionError):
            condition(None)
        return condition(None)
    page.browser.wait.for_.side_effect = until
    page.should_have_prices(expected, products)
    assert page.products.call_count == 2


@pytest.mark.parametrize('path,flags', [
    ('/', {'login_marker': True}),
    ('/inventory.html', {'password_input': True}),
    ('/cart.html', {'captcha': True}),
    ('/unknown', {}),
])
def test_unsafe_pages_never_produce_screenshots(path, flags, monkeypatch):
    driver = Mock(title='Swag Labs', current_url='https://www.saucedemo.com'+path)
    driver.execute_script.return_value = flags
    monkeypatch.setattr(diagnostic.allure, 'attach', Mock())
    diagnostic.attach_failure(driver, 'call')
    driver.find_element.assert_not_called()
    driver.get_screenshot_as_png.assert_not_called()


@pytest.mark.parametrize('path', ['/inventory.html','/cart.html','/checkout-step-one.html','/checkout-step-two.html','/checkout-complete.html'])
def test_safe_pages_capture_only_known_container(path, monkeypatch):
    driver = Mock(title='Swag Labs', current_url='https://www.saucedemo.com'+path)
    driver.execute_script.return_value = {}
    driver.find_element.return_value.screenshot_as_png = b'\x89PNG\r\n\x1a\nunit'
    attach = Mock()
    monkeypatch.setattr(diagnostic.allure, 'attach', attach)
    diagnostic.attach_failure(driver, 'call')
    driver.find_element.assert_called_once_with('css selector', diagnostic.CONTAINERS[path])
    driver.get_screenshot_as_png.assert_not_called()
    assert attach.call_args.kwargs['attachment_type'] == diagnostic.allure.attachment_type.PNG


def test_failed_diagnostics_and_attachments_preserve_original_exception(monkeypatch):
    driver = Mock()
    driver.execute_script.side_effect = RuntimeError('unit-secret')
    attach = Mock(side_effect=OSError('unit-secret'))
    monkeypatch.setattr(diagnostic.allure, 'attach', attach)
    original = AssertionError('original assertion')
    with pytest.raises(AssertionError) as captured:
        try:
            raise original
        finally:
            diagnostic.attach_failure(driver, 'call')
    assert captured.value is original
    assert all('unit-secret' not in c.args[0] for c in attach.call_args_list)


def test_fixture_disables_automatic_evidence_and_always_quits(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('sauce_fixtures', ROOT/'tests/ui/conftest.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    driver = Mock(capabilities={'browserVersion':'unit', 'chrome':{'chromedriverVersion':'unit','userDataDir':'unit'}})
    monkeypatch.setattr(fixtures.webdriver, 'Chrome', Mock(return_value=driver))
    attach = Mock()
    monkeypatch.setattr(fixtures.allure, 'attach', attach)
    node = SimpleNamespace()
    generator = fixtures.ui_browser.__wrapped__(tmp_path, SimpleNamespace(node=node))
    browser = next(generator)
    assert browser.config.save_screenshot_on_failure is False
    assert browser.config.save_page_source_on_failure is False
    assert browser.config.log_outer_html_on_failure is False
    assert not hasattr(node, '_qa_drivers')
    generator.close()
    driver.quit.assert_called_once_with()
    assert json.loads(attach.call_args.args[0])['closed'] is True


def identities():
    current=[];previous=[]
    for i in range(22):
        web = i>=14
        record={'fullName':f'new-{i}' if web else f'kept-{i}', 'testCaseId':f'case-{i}',
                'historyId':f'history-{i}', 'labels':{'parentSuite':'Web UI' if web else 'API'}}
        current.append(record)
        previous.append({**record, 'fullName':f'old-{i}' if web else record['fullName'],
                         'labels':[{'name':'parentSuite','value':'Web UI' if web else 'API'}]})
    return current,previous


def test_migration_requires_explicit_permission_and_preserves_all_14_ids():
    current,previous=identities()
    assert compare_identities(current,previous)
    assert compare_identities(current,previous,True)==[]
    current[0]['historyId']='changed'
    assert compare_identities(current,previous,True)


def test_migration_rejects_reusing_an_old_ui_identity():
    current,previous=identities()
    current[14]['fullName']=previous[14]['fullName']
    assert compare_identities(current,previous,True)
