"""Monitor contract tests use fake transports; no browser or site is opened."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webelement import WebElement

from ci.diagnostics import webdriver_monitor as monitor


class Driver:
    _is_remote = False

    def __init__(self, profile=''):
        self.capabilities = {
            'browserName': 'chrome', 'browserVersion': '156.0.8078.81',
            'platformName': 'windows', 'pageLoadStrategy': 'normal',
            'acceptInsecureCerts': False,
            'chrome': {'chromedriverVersion': '156.0.8078.80 (private-build-marker)',
                       'userDataDir': profile},
            'proxy': {'password': 'private-proxy-password'},
            'goog:chromeOptions': {'debuggerAddress': 'private-debugger-address'},
        }
        self.calls = []
        self.response = {'value': object()}
        self.error = None

    def execute(self, driver_command, params=None):
        self.calls.append((driver_command, params))
        if self.error is not None:
            raise self.error
        return self.response

    def execute_script(self, script):
        self.calls.append(('setup_probe', None))
        return {'width': 1422, 'height': 848, 'dpr': 1, 'headless': True}


def configuration(root):
    return SimpleNamespace(rootpath=root, option=SimpleNamespace(collectonly=False),
                           getoption=lambda name: str(root/'artifacts/pytest-tmp'))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    config = configuration(tmp_path)
    manager = monitor.Monitor(config, tmp_path/'artifacts/diagnostics')
    node = SimpleNamespace(nodeid='tests/ui/test_checkout.py::test_complete_checkout',
                           name='test_complete_checkout', path=tmp_path/'tests/ui/test_checkout.py')
    driver = Driver(str(tmp_path/'private-profile-owner/scoped_dir123_456'))
    monkeypatch.setenv('TEMP', str(tmp_path/'private-profile-owner'))
    browser = SimpleNamespace(config=SimpleNamespace(driver=driver))
    monkeypatch.setattr(monitor, 'windows_context', lambda: {
        'user_id': '0000000000000000', 'session_id': 5,
        'session_type': 'interactive_window_station'})
    return manager, node, browser, driver


def test_wrapper_preserves_argument_and_result_identity_and_calls_once():
    driver = Driver()
    recorder = monitor.Recorder(driver, 'test_complete_checkout', {})
    params = {'text': 'private-input-marker', 'Authorization': 'private-auth-marker'}
    response = driver.execute('sendKeysToElement', params)
    assert response is driver.response
    assert driver.calls == [('sendKeysToElement', params)]
    assert driver.calls[0][1] is params
    assert recorder.events[0]['outcome'] == 'ok'
    assert recorder.events[0]['duration_ms'] >= 0
    assert 'private-' not in json.dumps(recorder.document())


@pytest.mark.parametrize('error', [WebDriverException('private-message'),
                                  KeyboardInterrupt('private-message'), SystemExit('private-message')])
def test_original_exception_identity_is_preserved(error):
    driver = Driver()
    recorder = monitor.Recorder(driver, 'test_complete_checkout', {})
    driver.error = error
    with pytest.raises(type(error)) as captured:
        driver.execute('sendKeysToElement', {'text': 'private-input'})
    assert captured.value is error
    assert len(driver.calls) == 1
    assert recorder.events[0]['exception_type'] == type(error).__name__
    assert 'private-' not in json.dumps(recorder.document())


@pytest.mark.parametrize('fails', [False, True])
def test_broken_logging_cannot_change_transport_outcome(fails, monkeypatch):
    driver = Driver()
    recorder = monitor.Recorder(driver, 'test_complete_checkout', {})
    original = WebDriverException('private-original')
    driver.error = original if fails else None
    monkeypatch.setattr(recorder, 'record', Mock(side_effect=OSError('private-log-error')))
    if fails:
        with pytest.raises(WebDriverException) as captured:
            driver.execute('getCurrentUrl')
        assert captured.value is original
    else:
        assert driver.execute('getCurrentUrl') is driver.response
    assert len(driver.calls) == 1
    assert recorder.diagnostic_errors == 1


def test_clear_input_cookie_script_payloads_and_responses_are_not_retained():
    driver = Driver()
    recorder = monitor.Recorder(driver, 'private-test-name', {})
    driver.response = {'value': {'cookies': 'private-cookie-response', 'html': 'private-html'}}
    for command in ['sendKeysToElement', 'getCookies', 'addCookie', 'w3cExecuteScript', 'private-command']:
        assert driver.execute(command, {'text': 'private-text', 'script': 'private-script',
                                         'cookie': 'private-cookie'}) is driver.response
    document = recorder.document()
    assert document['test'] == 'other_ui_test'
    assert document['commands'][-1]['command'] == 'other'
    assert 'private-' not in json.dumps(document)


def test_operation_mapping_uses_unwrapped_element_without_extra_commands():
    driver = Driver()
    recorder = monitor.Recorder(driver, 'test_complete_checkout', {})
    element = WebElement(driver, 'private-element-id')
    driver.response = {'value': element}
    response = driver.execute('findElement', {'using': 'css selector', 'value': '#last-name'})
    assert response is driver.response
    element.send_keys('private-value')
    assert len(driver.calls) == 2
    assert recorder.events[-1]['operation'] == 'checkout.last_name'
    assert 'private-' not in json.dumps(recorder.document())


def test_command_hot_path_performs_no_disk_writes(monkeypatch):
    driver = Driver()
    recorder = monitor.Recorder(driver, 'test_complete_checkout', {})
    with monkeypatch.context() as patch:
        opened = Mock(side_effect=AssertionError('No disk I/O between commands'))
        patch.setattr(Path, 'open', opened)
        driver.execute('clickElement', {})
        driver.execute('sendKeysToElement', {})
        opened.assert_not_called()
    assert len(recorder.events) == 2


def test_event_buffer_is_bounded_without_dropping_transport_calls(monkeypatch):
    monkeypatch.setattr(monitor, 'MAX_EVENTS', 2)
    driver = Driver()
    recorder = monitor.Recorder(driver, 'test_complete_checkout', {})
    for _ in range(5):
        driver.execute('getElementProperty', {'name': 'value'})
    assert len(driver.calls) == 5
    assert len(recorder.events) == 2
    assert recorder.dropped == 3


def test_setup_probe_is_once_and_wrapper_remains_until_after_quit(setup):
    manager, node, browser, driver = setup
    original = driver.execute
    manager.attach(node, browser)
    assert driver.calls == [('setup_probe', None)]
    driver.execute('clickElement', {})
    driver.execute('quit')
    manager.close(node.nodeid)
    manager.close(node.nodeid)
    assert driver.execute == original
    assert 'execute' not in driver.__dict__
    files = list(manager.output.glob('*.json'))
    assert len(files) == 1
    document = json.loads(files[0].read_text())
    assert [item['command'] for item in document['commands']] == ['clickElement', 'quit']
    assert document['context']['viewport'] == {'width': 1422, 'height': 848, 'dpr': 1}
    assert document['context']['isolated_temporary_profile'] is True
    assert 'private-' not in json.dumps(document)


def test_duplicate_profile_is_marked_not_assumed_isolated(setup):
    manager, node, browser, driver = setup
    manager.attach(node, browser)
    manager.close(node.nodeid)
    manager.attach(node, browser)
    recorder, _ = manager.active[node.nodeid]
    assert recorder.context['isolated_temporary_profile'] is False
    manager.close(node.nodeid)
    assert len(list(manager.output.glob('*.json'))) == 2


def test_failed_setup_read_does_not_disable_recording_or_repeat_probe(setup):
    manager, node, browser, driver = setup
    driver.execute_script = Mock(side_effect=WebDriverException('private-probe-message'))
    manager.attach(node, browser)
    driver.execute('clickElement')
    manager.close(node.nodeid)
    driver.execute_script.assert_called_once()
    document = json.loads(next(manager.output.glob('*.json')).read_text())
    assert document['context']['viewport'] is None
    assert document['commands'][0]['command'] == 'clickElement'
    assert 'private-' not in json.dumps(document)


def test_file_error_restores_driver_and_does_not_escape(setup, monkeypatch):
    manager, node, browser, driver = setup
    original = driver.execute
    manager.attach(node, browser)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', Mock(side_effect=PermissionError('private-path')))
        manager.close(node.nodeid)
    assert driver.execute == original
    assert manager.failed == 1
    assert not manager.active


def test_output_outside_artifacts_is_rejected_before_browser_probe(setup):
    manager, node, browser, driver = setup
    manager.output = Path(manager.config.rootpath)/'other'
    manager.attach(node, browser)
    assert manager.failed == 1
    assert not driver.calls
    assert not manager.output.exists()


@pytest.mark.parametrize('collectonly,output', [(False, None), (False, ''), (True, 'enabled')])
def test_plugin_is_inert_when_disabled_or_collecting(tmp_path, monkeypatch, collectonly, output):
    config = configuration(tmp_path)
    config.option.collectonly = collectonly
    if output is not None:
        monkeypatch.setenv(monitor.ENVIRONMENT, str(tmp_path/'artifacts/diagnostics') if output else '')
    else:
        monkeypatch.delenv(monitor.ENVIRONMENT, raising=False)
    monitor.pytest_configure(config)
    assert not hasattr(config, '_qa_webdriver_monitor')
    assert not (tmp_path/'artifacts').exists()


@pytest.mark.parametrize('suite,fixture', [('api', 'ui_browser'), ('mobile', 'ui_browser'), ('ui', 'other_fixture')])
def test_hook_does_not_instrument_other_suites_or_fixtures(setup, suite, fixture):
    manager, node, browser, driver = setup
    manager.config._qa_webdriver_monitor = manager
    node.path = Path(manager.config.rootpath)/'tests'/suite/'test_probe.py'
    request = SimpleNamespace(config=manager.config, node=node)
    hook = monitor.pytest_fixture_setup(SimpleNamespace(argname=fixture), request)
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(SimpleNamespace(excinfo=None, get_result=lambda: browser))
    assert not driver.calls
    assert not manager.output.exists()


def test_unknown_exception_class_name_is_not_serialized():
    private_error = type('private-class-marker', (Exception,), {})('private-message')
    assert monitor.error_type(private_error) == 'OtherException'


def test_windows_context_contains_no_raw_sid_or_account_name():
    context = monitor.windows_context()
    assert context['user_id'] is None or len(context['user_id']) == 16
    assert context['session_id'] is None or isinstance(context['session_id'], int)
    assert 'S-1-' not in json.dumps(context)


def test_real_pytest_fixture_hooks_with_fake_transport_only(tmp_path):
    root = tmp_path/'isolated'
    suite = root/'tests/ui'
    suite.mkdir(parents=True)
    (root/'pytest.ini').write_text('[pytest]\n')
    (suite/'conftest.py').write_text('''
import pytest
from types import SimpleNamespace
class Driver:
    capabilities = {}
    def execute(self, driver_command, params=None): return {'value': None}
    def execute_script(self, script): return {'width': 100, 'height': 100, 'dpr': 1, 'headless': True}
@pytest.fixture
def ui_browser():
    driver = Driver()
    try: yield SimpleNamespace(config=SimpleNamespace(driver=driver))
    finally: driver.execute('quit')
''')
    (suite/'test_probe.py').write_text('''
def test_complete_checkout(ui_browser):
    assert ui_browser.config.driver.execute('clickElement', {'text':'private-never-save'}) == {'value':None}
''')
    repository = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.update(PYTHONPATH=str(repository), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               QA_WEBDRIVER_DIAGNOSTICS=str(root/'artifacts/diagnostics'))
    env.pop('PYTEST_ADDOPTS', None)
    process = subprocess.run([sys.executable, '-m', 'pytest', 'tests/ui', '-q',
                              '-p', 'ci.diagnostics.webdriver_monitor', '--confcutdir='+str(root),
                              '--basetemp='+str(root/'artifacts/tmp')], cwd=root, env=env,
                             capture_output=True, timeout=45)
    assert process.returncode == 0, process.stdout.decode(errors='replace')
    files = list((root/'artifacts/diagnostics').glob('*.json'))
    assert len(files) == 1
    document = json.loads(files[0].read_text())
    assert [event['command'] for event in document['commands']] == ['clickElement', 'quit']
    assert 'private-never-save' not in files[0].read_text()
