"""Infrastructure-only fixtures; no real browser, device, or application results."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tests/ui'), str(ROOT / 'tests/mobile')]
import web_diagnostics as web
import mobile_session as mobile
from mobile_config import UIAUTOMATOR2_SERVER_LAUNCH_TIMEOUT_MS


@pytest.mark.parametrize('url,expected', [
    ('https://automationexercise.com/contact_us?token=unit-secret#unit-secret',
     'https://automationexercise.com/contact_us'),
    ('https://unit-secret:unit-secret@automationexercise.com/products',
     'https://automationexercise.com/products'),
    ('https://automationexercise.com/product_details/1',
     'https://automationexercise.com/product_details/1'),
    ('https://automationexercise.com/unit-secret',
     'https://automationexercise.com/[other path omitted]'),
    ('https://unit-secret.example/unit-secret', '[unexpected URL omitted]'),
    ('javascript:unit-secret', '[unexpected URL omitted]'),
])
def test_url_never_logs_credentials_query_fragment_or_unknown_path(url, expected):
    assert web.safe_url(url) == expected
    assert 'unit-secret' not in web.safe_url(url)


def test_browser_state_reports_observed_block_page_without_raw_body():
    driver = Mock(title='Секундочку…', current_url='https://automationexercise.com/')
    driver.execute_script.return_value = {
        'document_ready': True, 'challenge_title': True, 'challenge_message': True,
        'body': 'unit-secret', 'cookies': 'unit-secret',
    }
    state = web.browser_state(driver)
    assert state['request_check_page'] is True
    assert state['home_marker'] is False
    assert state['title'] == 'Секундочку…'
    assert 'unit-secret' not in json.dumps(state)


def test_unknown_title_and_nonboolean_values_are_not_attached():
    driver = Mock(title='unit-secret', current_url='https://automationexercise.com/')
    driver.execute_script.return_value = {'home_marker': 'unit-secret', 'extra': 'unit-secret'}
    state = web.browser_state(driver)
    assert state['title'] == '[unrecognized title omitted]'
    assert state['home_marker'] is False
    assert 'unit-secret' not in json.dumps(state)


def test_unavailable_browser_diagnostic_attaches_only_error_type(monkeypatch):
    driver = Mock()
    driver.execute_script.side_effect = RuntimeError('unit-secret')
    attach = Mock()
    monkeypatch.setattr(web.allure, 'attach', attach)
    web.attach_browser_state(driver, 'call')
    assert json.loads(attach.call_args.args[0]) == {'diagnostic_error_type': 'RuntimeError'}


def test_logcat_is_bounded_since_session_and_contains_no_raw_messages():
    text = ('11-04 18:00:00.000 1 2 E AndroidRuntime: io.appium.uiautomator2 old crash\n'
            '11-04 18:01:00.000 1 2 E AndroidRuntime: other.application unit-secret\n'
            '11-04 18:01:01.000 1 2 E AndroidRuntime: io.appium.uiautomator2.server crash java.lang.IllegalStateException unit-secret\n')
    result = mobile.logcat_summary(text, '11-04 18:01:00.000')
    assert result['events'] == [{'time': '11-04 18:01:01.000', 'event': 'appium_crash',
                                 'exception_types': ['java.lang.IllegalStateException']}]
    assert 'unit-secret' not in json.dumps(result)
    assert len(mobile.logcat_summary(text * 500)['events']) <= 80
    assert mobile.logcat_summary(text * 500)['examined_lines'] == 400


def test_logcat_filters_anr_for_appium_only():
    summary = mobile.logcat_summary('11-04 18:01:00.000 1 2 E ActivityManager: ANR in io.appium.uiautomator2.server unit-secret')
    assert summary['events'][0]['event'] == 'appium_anr'
    assert 'unit-secret' not in json.dumps(summary)


def test_successful_session_is_created_once_and_timed_without_logcat():
    session = object()
    factory = Mock(return_value=session)
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout='11-04 18:01:00.000\n'))
    attach = Mock()
    assert mobile.create_session(factory, adb='adb', device='unit-device', launch_timeout_ms=60000,
                                 run=run, clock=Mock(side_effect=[1, 12]), attach=attach) is session
    factory.assert_called_once_with()
    assert run.call_count == 1
    timing = json.loads(attach.call_args.args[0])
    assert timing['outcome'] == 'created'
    assert timing['session_create_seconds'] == 11
    assert timing['uiautomator2_server_launch_timeout_ms'] == 60000


def test_failed_session_keeps_original_error_and_attaches_sanitized_logcat():
    original = RuntimeError('unit-secret')
    factory = Mock(side_effect=original)
    run = Mock(side_effect=[SimpleNamespace(returncode=0, stdout='11-04 18:01:00.000'),
                            SimpleNamespace(returncode=0, stdout='11-04 18:01:01.000 1 2 E AndroidRuntime: io.appium.uiautomator2.server fatal unit-secret')])
    attach = Mock()
    with pytest.raises(RuntimeError) as captured:
        mobile.create_session(factory, adb='adb', device='unit-device', launch_timeout_ms=60000,
                              run=run, clock=Mock(side_effect=[1, 40]), attach=attach)
    assert captured.value is original
    factory.assert_called_once_with()
    assert run.call_args.args[0][-1] == '*:S'
    assert '-c' not in run.call_args.args[0]  # never clear user's logcat
    assert run.call_args.kwargs['timeout'] == 10
    assert len(attach.call_args_list) == 2
    assert all('unit-secret' not in call.args[0] for call in attach.call_args_list)
    assert json.loads(attach.call_args.args[0])['session_create_seconds'] == 39


def test_diagnostic_and_attachment_failure_cannot_mask_session_error():
    original = RuntimeError('original unit failure')
    factory = Mock(side_effect=original)
    with pytest.raises(RuntimeError) as captured:
        mobile.create_session(factory, adb='adb', device='unit-device', launch_timeout_ms=60000,
                              run=Mock(side_effect=subprocess.TimeoutExpired('adb', 5)),
                              clock=Mock(side_effect=[1, 3]), attach=Mock(side_effect=OSError('unit attachment failure')))
    assert captured.value is original
    factory.assert_called_once_with()


def test_session_cancellation_is_not_reported_as_success():
    attach = Mock()
    with pytest.raises(KeyboardInterrupt):
        mobile.create_session(Mock(side_effect=KeyboardInterrupt), adb='adb', device='unit-device',
                              launch_timeout_ms=60000, run=Mock(side_effect=OSError),
                              clock=Mock(side_effect=[1, 3]), attach=attach)
    assert json.loads(attach.call_args.args[0])['outcome'] == 'interrupted'


def test_launch_timeout_remains_bounded():
    assert UIAUTOMATOR2_SERVER_LAUNCH_TIMEOUT_MS == 60000


def test_root_failure_hook_preserves_failure_when_diagnostic_raises(monkeypatch):
    spec = importlib.util.spec_from_file_location('diagnostic_root_hooks', ROOT / 'conftest.py')
    hooks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hooks)
    attach = Mock()
    monkeypatch.setattr(hooks.allure, 'attach', attach)
    failure = SimpleNamespace(failed=True, when='call')
    item = SimpleNamespace(_qa_failure_diagnostics={'page': Mock(side_effect=RuntimeError('unit-secret'))})
    wrapper = hooks.pytest_runtest_makereport(item, None)
    next(wrapper)
    with pytest.raises(StopIteration):
        wrapper.send(SimpleNamespace(get_result=lambda: failure))
    assert failure.failed
    assert attach.call_args.args[0] == 'RuntimeError'


def test_real_allure_json_attachments_for_diagnostic_unit_fixture():
    # These are actual unit-test attachments, not results of an application test.
    result = mobile.create_session(lambda: object(), adb='unit-unavailable-adb', device='unit-device',
                                   launch_timeout_ms=60000, run=Mock(side_effect=OSError),
                                   clock=Mock(side_effect=[1, 2]))
    assert result is not None
    driver = Mock(title='One moment, please...', current_url='https://automationexercise.com/')
    driver.execute_script.return_value = {'challenge_title': True, 'document_ready': True}
    web.attach_browser_state(driver, 'unit-fixture')
    with pytest.raises(RuntimeError, match='expected unit failure'):
        mobile.create_session(Mock(side_effect=RuntimeError('expected unit failure')),
                              adb='unit-unavailable-adb', device='unit-device', launch_timeout_ms=60000,
                              run=Mock(side_effect=[
                                  SimpleNamespace(returncode=0, stdout='11-04 18:01:00.000'),
                                  SimpleNamespace(returncode=0, stdout='11-04 18:01:01.000 1 2 E AndroidRuntime: io.appium.uiautomator2.server fatal'),
                              ]), clock=Mock(side_effect=[1, 32]))
