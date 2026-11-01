"""CI safety checks, separate from the 22 application tests in tests/."""

import json
from contextlib import ExitStack, contextmanager, nullcontext
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, Mock
import urllib.error
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mobile_ci as ci
from windows_resources import DeviceLock, OwnedProcesses


@pytest.fixture
def run(tmp_path):
    report = tmp_path / 'mobile'
    report.mkdir()
    return ci.MobileRun(report)


def result(stdout='', code=0):
    return subprocess.CompletedProcess([], code, stdout, '')


def test_existing_emulator_is_not_launched_again(run):
    owned = Mock()
    run.command = Mock(side_effect=[
        result('List of devices attached\nemulator-5554 device product:test\n'),
        result('List of devices attached\nemulator-5554 device\n'),
        result('1\n'), result('package:/system/framework/framework-res.apk'),
        result('0\n'),
        result('package:/data/app/material-files/base.apk'),
        result(ci.PACKAGE + '/' + ci.APP_ACTIVITY), result('Status: ok\n'), result(),
    ])
    assert run.prepare_device(owned, Mock()) is None
    owned.start.assert_not_called()
    assert not any('kill' in call.args[0] for call in run.command.call_args_list)


@pytest.mark.parametrize('devices', ['List of devices attached\n',
                                   'List of devices attached\nemulator-5556 device\n'])
def test_missing_or_other_emulator_does_not_start_when_disabled(run, devices):
    run.start_emulator = False
    owned = Mock()
    run.command = Mock(return_value=result(devices))
    with pytest.raises(RuntimeError):
        run.prepare_device(owned, Mock())
    owned.start.assert_not_called()


def test_existing_appium_is_not_owned(run, monkeypatch):
    owned = Mock()
    paths = []

    def status_only(path, **kwargs):
        paths.append(path)
        assert path == '/status', 'Unsupported session listing must not be queried'
        return {'ready': True}

    monkeypatch.setattr(ci, 'read_appium', status_only)
    run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()
    assert paths == ['/status']


def test_busy_device_is_rejected_before_appium_or_commands(tmp_path, monkeypatch):
    mobile = ci.MobileRun(tmp_path / 'busy-run')
    mobile.command = Mock()
    lock = MagicMock()
    lock.__enter__.side_effect = RuntimeError('Mobile device is busy')
    monkeypatch.setattr(ci, 'DeviceLock', Mock(return_value=lock))
    owned = Mock()
    appium = Mock()
    monkeypatch.setattr(ci, 'OwnedProcesses', owned)
    monkeypatch.setattr(ci, 'read_appium', appium)
    with pytest.raises(RuntimeError, match='busy'):
        mobile.execute()
    mobile.command.assert_not_called()
    appium.assert_not_called()
    owned.assert_not_called()
    assert 'Acquire DeviceLock' in (mobile.report / 'environment.log').read_text()


def test_device_lock_contention_closes_handle_without_releasing_foreign_lock(monkeypatch):
    dll = Mock()
    dll.CreateMutexW.return_value = 123
    dll.WaitForSingleObject.return_value = 0x102  # WAIT_TIMEOUT: owned by another runner
    monkeypatch.setattr('windows_resources.kernel', lambda: dll)
    with pytest.raises(RuntimeError, match='busy'):
        DeviceLock().__enter__()
    dll.CloseHandle.assert_called_once_with(123)
    dll.ReleaseMutex.assert_not_called()


def test_check_mode_never_starts_appium(run, monkeypatch):
    run.check_only = True
    owned = Mock()
    monkeypatch.setattr(ci, 'read_appium', lambda path, **kwargs: None)
    monkeypatch.setattr(ci.time, 'monotonic', Mock(side_effect=[0, 0, 0, 61, 61]))
    with pytest.raises(TimeoutError):
        run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()


def test_unavailable_appium_starts_owned_server_and_waits_ready(run, monkeypatch):
    owned = Mock()
    owned.start.return_value.poll.return_value = None
    status = Mock(side_effect=[None, {'ready': False}, {'ready': True}])
    monkeypatch.setattr(ci, 'read_appium', status)
    monkeypatch.setattr(ci, 'appium_port_available', Mock(return_value=True))
    monkeypatch.setattr(ci.threading, 'Event', Mock())
    with ExitStack() as stack:
        run.prepare_appium(owned, stack, ['node', 'appium'])
    owned.start.assert_called_once()
    assert '--base-path' in owned.start.call_args.args[0]
    assert all(call.args == ('/status',) for call in status.call_args_list)


def test_missing_http_route_is_not_a_timeout(run, monkeypatch):
    opener = Mock()
    opener.open.side_effect = urllib.error.HTTPError(ci.APPIUM_URL + '/status', 404, 'Not Found', None, None)
    monkeypatch.setattr(ci.urllib.request, 'build_opener', Mock(return_value=opener))
    with pytest.raises(RuntimeError, match='HTTP 404') as caught:
        ci.read_appium('/status', log=run.note, report=run.report)
    assert not ci.is_timeout(caught.value)
    assert isinstance(caught.value.__cause__, urllib.error.HTTPError)


@pytest.mark.parametrize('wrapped', [False, True])
def test_http_connect_timeout_is_preserved_and_traced(run, monkeypatch, wrapped):
    error = TimeoutError('timed out')
    if wrapped:
        error = urllib.error.URLError(error)
    opener = Mock()
    opener.open.side_effect = error
    monkeypatch.setattr(ci.urllib.request, 'build_opener', Mock(return_value=opener))
    owned = Mock()
    with pytest.raises(type(error)):
        ci.read_appium('/status', log=run.note, report=run.report)
    owned.start.assert_not_called()
    diagnostic = (run.report / 'diagnostic-traceback.log').read_text()
    assert 'HTTP open /status' in diagnostic
    assert 'Traceback (most recent call last)' in diagnostic
    assert 'timed out' in diagnostic
    events = (run.report / 'environment.log').read_text()
    assert 'START HTTP open /status' in events
    assert 'END HTTP open /status status=ERROR elapsed_s=' in events
    assert f'exception={type(error).__name__}' in events


def test_http_response_body_timeout_is_distinguished(run, monkeypatch):
    response = MagicMock()
    opener = Mock()
    opener.open.return_value = response
    monkeypatch.setattr(ci.urllib.request, 'build_opener', Mock(return_value=opener))
    monkeypatch.setattr(ci.json, 'load', Mock(side_effect=TimeoutError('body read timed out')))
    with pytest.raises(TimeoutError):
        ci.read_appium('/status', log=run.note, report=run.report)
    assert 'HTTP body /status' in (run.report / 'diagnostic-traceback.log').read_text()


def test_http_refused_is_unavailable_but_permission_error_is_not(run, monkeypatch):
    opener = Mock()
    monkeypatch.setattr(ci.urllib.request, 'build_opener', Mock(return_value=opener))
    opener.open.side_effect = urllib.error.URLError(ConnectionRefusedError())
    assert ci.read_appium('/status', log=run.note, report=run.report) is None
    opener.open.side_effect = urllib.error.URLError(PermissionError('access denied'))
    with pytest.raises(urllib.error.URLError):
        ci.read_appium('/status', log=run.note, report=run.report)


def test_port_probe_permission_error_does_not_start_server(run, monkeypatch):
    monkeypatch.setattr(ci, 'read_appium', lambda path, **kwargs: None)
    monkeypatch.setattr(ci, 'appium_port_available', Mock(side_effect=PermissionError('denied')))
    owned = Mock()
    with pytest.raises(PermissionError):
        run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()


def test_appium_ready_deadline_records_wait_context(run, monkeypatch):
    monkeypatch.setattr(ci, 'read_appium', lambda path, **kwargs: {'ready': False})
    monkeypatch.setattr(ci.time, 'monotonic', Mock(side_effect=[0, 61]))
    owned = Mock()
    with pytest.raises(TimeoutError, match='Appium did not return'):
        run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()
    assert 'Wait Appium ready timeout_s=60' in (run.report / 'diagnostic-traceback.log').read_text()


def test_subprocess_timeout_preserves_partial_output(run, monkeypatch):
    monkeypatch.setattr(ci.subprocess, 'run', Mock(side_effect=subprocess.TimeoutExpired(
        ['adb', 'devices'], 20, output=b'partial stdout', stderr=b'partial stderr')))
    with pytest.raises(subprocess.TimeoutExpired):
        run.command(['adb', 'devices'])
    log = (run.report / 'adb-tools.log').read_text()
    assert 'START adb devices' in log
    assert 'partial stdout' in log and 'partial stderr' in log
    assert 'TIMEOUT limit_s=20' in log
    assert 'TimeoutExpired' in (run.report / 'diagnostic-traceback.log').read_text()


@pytest.mark.parametrize('wrapped', [False, True])
def test_initial_timeout_free_port_starts_server_then_retries(run, monkeypatch, wrapped):
    error = TimeoutError('connect timed out')
    if wrapped:
        error = urllib.error.URLError(error)
    status = Mock(side_effect=[error, error, {'ready': False}, {'ready': True}])
    monkeypatch.setattr(ci, 'read_appium', status)
    probe = Mock(return_value=True)
    monkeypatch.setattr(ci, 'appium_port_available', probe)
    monkeypatch.setattr(ci.threading, 'Event', Mock())
    owned = Mock()
    owned.start.return_value.poll.return_value = None
    with ExitStack() as stack:
        run.prepare_appium(owned, stack, ['node', 'appium'])
    owned.start.assert_called_once()
    probe.assert_called_once()
    assert status.call_count == 4
    assert (run.report / 'appium.log').exists()


def test_timeout_occupied_port_retries_existing_server_without_duplicate(run, monkeypatch):
    monkeypatch.setattr(ci, 'read_appium', Mock(side_effect=[TimeoutError(), {'ready': True}]))
    monkeypatch.setattr(ci, 'appium_port_available', Mock(return_value=False))
    monkeypatch.setattr(ci.threading, 'Event', Mock())
    owned = Mock()
    run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()


def test_retry_timeout_uses_single_deadline_and_saves_traceback(run, monkeypatch):
    monkeypatch.setattr(ci, 'read_appium', Mock(side_effect=TimeoutError('connect timeout')))
    monkeypatch.setattr(ci, 'appium_port_available', Mock(return_value=False))
    monkeypatch.setattr(ci.time, 'monotonic', Mock(side_effect=[0, 0, 2, 59, 60]))
    monkeypatch.setattr(ci.threading, 'Event', Mock())
    owned = Mock()
    with pytest.raises(TimeoutError, match='within 60s'):
        run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()
    assert 'Traceback' in (run.report / 'diagnostic-traceback.log').read_text()


def test_owned_appium_exit_does_not_restart_or_kill_other_server(run, monkeypatch):
    monkeypatch.setattr(ci, 'read_appium', Mock(return_value=None))
    monkeypatch.setattr(ci, 'appium_port_available', Mock(return_value=True))
    monkeypatch.setattr(ci.threading, 'Event', Mock())
    owned = Mock()
    owned.start.return_value.poll.return_value = 1
    owned.start.return_value.returncode = 1
    with ExitStack() as stack, pytest.raises(RuntimeError, match='exited with 1'):
        run.prepare_appium(owned, stack, ['node', 'appium'])
    owned.start.assert_called_once()


def test_existing_server_not_ready_yet_is_reused_after_wait(run, monkeypatch):
    monkeypatch.setattr(ci, 'read_appium', Mock(side_effect=[{'ready': False}, {'ready': True}]))
    probe = Mock()
    monkeypatch.setattr(ci, 'appium_port_available', probe)
    monkeypatch.setattr(ci.threading, 'Event', Mock())
    owned = Mock()
    run.prepare_appium(owned, Mock(), ['node', 'appium'])
    probe.assert_not_called()
    owned.start.assert_not_called()


def test_owned_server_never_ready_fails_with_logs_and_no_second_start(run, monkeypatch):
    monkeypatch.setattr(ci, 'read_appium', Mock(return_value=None))
    monkeypatch.setattr(ci, 'appium_port_available', Mock(return_value=True))
    monkeypatch.setattr(ci.time, 'monotonic', Mock(side_effect=[0, 0, 2, 59, 60]))
    monkeypatch.setattr(ci.threading, 'Event', Mock())
    owned = Mock()
    owned.start.return_value.poll.return_value = None
    with ExitStack() as stack, pytest.raises(TimeoutError):
        run.prepare_appium(owned, stack, ['node', 'appium'])
    owned.start.assert_called_once()
    assert (run.report / 'appium.log').exists()
    assert 'TimeoutError' in (run.report / 'diagnostic-traceback.log').read_text()


def test_ready_response_after_deadline_is_not_accepted(run, monkeypatch):
    status = Mock(return_value={'ready': True})
    monkeypatch.setattr(ci, 'read_appium', status)
    monkeypatch.setattr(ci.time, 'monotonic', Mock(side_effect=[0, 59, 61, 61]))
    owned = Mock()
    with pytest.raises(TimeoutError):
        run.prepare_appium(owned, Mock(), ['node', 'appium'])
    assert status.call_args.kwargs['timeout'] == 1
    owned.start.assert_not_called()


def test_bad_status_route_does_not_start_appium(run, monkeypatch):
    monkeypatch.setattr(ci, 'read_appium', Mock(side_effect=RuntimeError('HTTP 404')))
    owned = Mock()
    with pytest.raises(RuntimeError, match='404'):
        run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()


@pytest.mark.parametrize('failure,available', [(None, True), (OSError(ci.errno.EADDRINUSE, 'busy'), False),
                                            (PermissionError('denied'), None)])
def test_exclusive_bind_probe_closes_socket_and_never_listens(monkeypatch, failure, available):
    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.bind.side_effect = failure
    monkeypatch.setattr(ci.socket, 'socket', Mock(return_value=probe))
    if available is None:
        with pytest.raises(PermissionError):
            ci.appium_port_available()
    else:
        assert ci.appium_port_available() is available
    probe.bind.assert_called_once_with(('127.0.0.1', 4723))
    probe.listen.assert_not_called()
    probe.__exit__.assert_called_once()


@pytest.mark.parametrize('cleanup_error', [False, True])
def test_main_saves_traceback_and_allure_attachment(tmp_path, monkeypatch, cleanup_error):
    report = tmp_path / 'main-failure'
    monkeypatch.setenv('REPORT_ROOT', str(report))
    monkeypatch.setattr(sys, 'argv', ['mobile_ci.py'])

    def fail(self):
        self.report.mkdir()
        self.owns_report = True
        try:
            with self.checking('Synthetic initial HTTP request'):
                raise TimeoutError('synthetic socket timeout')
        finally:
            if cleanup_error:
                raise RuntimeError('synthetic cleanup failure')

    monkeypatch.setattr(ci.MobileRun, 'execute', fail)
    assert ci.main() == 2
    trace = (report / 'diagnostic-traceback.log').read_text()
    assert 'Synthetic initial HTTP request' in trace and 'TimeoutError' in trace
    assert 'test_mobile_ci.py' in trace
    if cleanup_error:
        assert 'synthetic cleanup failure' in trace
    data = json.loads(next((report / 'allure-results').glob('*-result.json')).read_text())
    attachment = next(a for a in data['attachments'] if 'diagnostic-traceback' in a['name'])
    assert 'TimeoutError' in (report / 'allure-results' / attachment['source']).read_text()


def test_readiness_timeout_is_finite(monkeypatch):
    monkeypatch.setattr(ci.time, 'monotonic', Mock(side_effect=[0, 2]))
    with pytest.raises(TimeoutError):
        ci.wait_until(lambda: False, 1, 'test readiness')


def test_owned_server_exit_stops_wait_immediately():
    process = Mock(returncode=3)
    process.poll.return_value = 3
    with pytest.raises(RuntimeError, match='exited with 3'):
        ci.wait_until(lambda: True, 60, 'Appium', process)


def test_infrastructure_failure_does_not_invent_six_tests(run):
    ci.infrastructure_report(run.report, 'ADB unavailable')
    suite = ET.parse(run.report / 'junit.xml').getroot()
    assert suite.attrib['tests'] == suite.attrib['errors'] == '1'
    data = json.loads(next((run.report / 'allure-results').glob('*-result.json')).read_text())
    assert data['status'] == 'broken'


def test_existing_junit_is_preserved(run):
    xml = run.report / 'junit.xml'
    xml.write_text('<testsuite tests="6"/>')
    ci.infrastructure_report(run.report, 'late failure')
    assert xml.read_text() == '<testsuite tests="6"/>'
    assert not (run.report / 'allure-results').exists()


def test_failure_logs_preserve_existing_allure_steps_and_attachments(run):
    results = run.report / 'allure-results'
    results.mkdir()
    record = {'uuid': 'test', 'status': 'failed', 'labels': [{'name': 'feature', 'value': 'Mobile'}],
              'steps': [{'name': 'existing step'}], 'attachments': [{'name': 'screenshot'}]}
    path = results / 'test-result.json'
    path.write_text(json.dumps(record))
    (run.report / 'environment.log').write_text('synthetic diagnostic')
    ci.attach_failure_logs(run.report)
    updated = json.loads(path.read_text())
    assert updated['labels'] == record['labels']
    assert updated['steps'] == record['steps']
    assert updated['attachments'][0] == record['attachments'][0]
    assert (results / updated['attachments'][1]['source']).read_text() == 'synthetic diagnostic'


@pytest.mark.parametrize('owned_emulator', [False, True])
def test_failure_cleans_owned_resources_but_not_existing_emulator(tmp_path, monkeypatch, owned_emulator):
    sdk = tmp_path / 'sdk'
    (sdk / 'platform-tools').mkdir(parents=True)
    (sdk / 'platform-tools/adb.exe').touch()
    monkeypatch.setenv('ANDROID_HOME', str(sdk))
    monkeypatch.delenv('ANDROID_SDK_ROOT', raising=False)
    mobile = ci.MobileRun(tmp_path / 'report')
    mobile.command = Mock(return_value=result('{"uiautomator2": {}}'))
    emulator = Mock() if owned_emulator else None
    if emulator is not None:
        emulator.poll.return_value = None
    mobile.prepare_device = Mock(return_value=emulator)
    mobile.prepare_appium = Mock(side_effect=RuntimeError('Appium failed'))
    closed = []

    @contextmanager
    def resource_scope():
        try:
            yield Mock()
        finally:
            closed.append(True)

    monkeypatch.setattr(ci, 'DeviceLock', nullcontext)
    monkeypatch.setattr(ci, 'OwnedProcesses', resource_scope)
    monkeypatch.setattr(ci, 'appium_command', lambda: ['node', 'appium'])
    with pytest.raises(RuntimeError, match='Appium failed'):
        mobile.execute()
    assert closed == [True]
    kill_calls = [call for call in mobile.command.call_args_list if 'kill' in call.args[0]]
    assert kill_calls == []  # Cleanup uses the owned Job Object, never an ADB serial.


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows Job Object integration')
def test_job_closes_only_its_gated_process(tmp_path):
    # No Android/Appium process: exercise actual Windows ownership and kill-on-close.
    import ctypes
    from ctypes import wintypes
    import os
    from windows_resources import kernel

    dll = kernel()
    dll.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    dll.OpenProcess.restype = wintypes.HANDLE
    marker = tmp_path / 'child.pid'
    target_handle = None
    with (tmp_path / 'child.log').open('wb') as log:
        try:
            with OwnedProcesses() as owned:
                process = owned.start(
                    [sys.executable, '-c',
                     'import os,sys,threading; from pathlib import Path; '
                     'Path(sys.argv[1]).write_text(str(os.getpid())); threading.Event().wait(60)', str(marker)],
                    log, os.environ.copy())
                ci.wait_until(marker.exists, 5, 'synthetic child started', process)
                target_handle = dll.OpenProcess(0x100000, False, int(marker.read_text()))
                assert target_handle
                assert dll.WaitForSingleObject(target_handle, 0) == 0x102  # still running
            assert process.poll() is not None
            assert dll.WaitForSingleObject(target_handle, 5000) == 0  # real descendant terminated
        finally:
            if target_handle:
                dll.CloseHandle(target_handle)


def test_failed_job_assignment_never_opens_the_child_gate(monkeypatch):
    process = Mock(_handle=123)
    monkeypatch.setattr('windows_resources.subprocess.Popen', Mock(return_value=process))
    monkeypatch.setattr('windows_resources.ctypes.get_last_error', lambda: 5)
    owned = OwnedProcesses()
    owned.dll = Mock()
    owned.dll.AssignProcessToJobObject.return_value = False
    owned.handle = 42
    owned.children = []
    with pytest.raises(OSError):
        owned.start(['unused'], Mock(), {})
    process.stdin.write.assert_not_called()
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=10)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows device lock')
def test_device_lock_rejects_a_second_process(tmp_path):
    # A mutex is reentrant within one thread, so test contention in another process.
    with DeviceLock():
        command = [sys.executable, '-c',
                   'from windows_resources import DeviceLock; DeviceLock().__enter__()']
        other = subprocess.run(command, cwd=Path(ci.__file__).parent,
                               capture_output=True, timeout=10)
        assert other.returncode != 0
        assert b'Mobile device is busy' in other.stderr

@pytest.fixture
def android_setup(run, monkeypatch, tmp_path):
    run.sdk = tmp_path / 'sdk'
    binary = run.sdk / 'emulator/emulator.exe'
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(ci.socket, 'socket', MagicMock())
    monkeypatch.setattr(ci.threading, 'Event', Mock())

    def configure(states, boots=None, pm=None, avds='Pixel_4\n'):
        state_values = iter(states)
        boot_values = iter(boots or ['1'])
        pm_values = iter(pm or [result('package:/system/framework/framework-res.apk')])
        latest = {'state': states[-1], 'boot': '1', 'pm': result('package:/system/framework/framework-res.apk')}

        def command(args, **kwargs):
            if 'devices' in args:
                latest['state'] = next(state_values, latest['state'])
                return result('List of devices attached\n' + latest['state'])
            if '-list-avds' in args:
                return result(avds)
            if 'get-current-user' in args:
                return result('0\n')
            if 'start' in args:
                return result('Status: ok\n')
            if 'getprop' in args:
                latest['boot'] = next(boot_values, latest['boot'])
                return result(latest['boot'])
            if args[-3:] == ['pm', 'path', 'android']:
                latest['pm'] = next(pm_values, latest['pm'])
                return latest['pm']
            if 'resolve-activity' in args:
                return result(ci.PACKAGE + '/' + ci.APP_ACTIVITY)
            return result('package:/data/app/material-files/base.apk')

        run.command = Mock(side_effect=command)
        owned = Mock()
        owned.start.return_value.poll.return_value = None
        return owned
    return configure


def test_absent_emulator_autostarts_existing_avd(run, android_setup):
    owned = android_setup(['', '', 'emulator-5554 offline\n', 'emulator-5554 device\n'])
    with ExitStack() as stack:
        assert run.prepare_device(owned, stack) is owned.start.return_value
    owned.start.assert_called_once()
    args = owned.start.call_args.args[0]
    assert args[args.index('-avd') + 1] == 'Pixel_4'
    assert '-no-window' in args and '-no-snapshot-save' in args
    assert '-wipe-data' not in args
    assert (run.report / 'emulator.log').exists()


@pytest.mark.parametrize('initial', ['emulator-5554 device\n', 'emulator-5554 offline\n'])
def test_slow_boot_and_package_manager_are_waited_for(run, android_setup, initial):
    owned = android_setup([initial, initial, 'emulator-5554 device\n'],
                          boots=['0', '1'], pm=[result('', 1), result('package:/system/framework/framework-res.apk')])
    run.prepare_device(owned, Mock())
    owned.start.assert_not_called()
    assert len([call for call in run.command.call_args_list if 'getprop' in call.args[0]]) >= 3


@pytest.mark.parametrize('states', [['emulator-5554 unauthorized\n'],
                                  ['emulator-5554 offline\n', 'emulator-5554 unauthorized\n']])
def test_unauthorized_is_immediate_error_without_reset(run, android_setup, states):
    owned = android_setup(states)
    with pytest.raises(RuntimeError, match='unauthorized'):
        run.prepare_device(owned, Mock())
    owned.start.assert_not_called()


def test_multiple_devices_use_explicit_target_without_start(run, android_setup):
    owned = android_setup(['physical123 device\nemulator-5554 device\nemulator-5556 device\n'])
    run.prepare_device(owned, Mock())
    owned.start.assert_not_called()
    for call in run.command.call_args_list:
        if 'shell' in call.args[0]:
            assert call.args[0][1:3] == ['-s', 'emulator-5554']


def test_other_emulator_prevents_duplicate(run, android_setup):
    owned = android_setup(['emulator-5556 device\n'])
    with pytest.raises(RuntimeError, match='Another emulator'):
        run.prepare_device(owned, Mock())
    owned.start.assert_not_called()


@pytest.mark.parametrize('failure', ['start', 'exit', 'missing-avd', 'port'])
def test_emulator_start_failures_are_reported(run, android_setup, monkeypatch, failure):
    owned = android_setup([''], avds='' if failure == 'missing-avd' else 'Pixel_4\n')
    if failure == 'start':
        owned.start.side_effect = OSError('cannot start emulator')
    elif failure == 'exit':
        owned.start.return_value.poll.return_value = 1
        owned.start.return_value.returncode = 1
    elif failure == 'port':
        probe = MagicMock()
        probe.__enter__.return_value.bind.side_effect = OSError('port occupied')
        monkeypatch.setattr(ci.socket, 'socket', Mock(return_value=probe))
    with ExitStack() as stack, pytest.raises((OSError, RuntimeError)):
        run.prepare_device(owned, stack)
    if failure in ('missing-avd', 'port'):
        owned.start.assert_not_called()


def test_android_boot_deadline_is_shared_with_commands(run, android_setup, monkeypatch):
    owned = android_setup(['emulator-5554 offline\n'])
    ticks = iter(range(0, 1000, 20))
    monkeypatch.setattr(ci.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(TimeoutError):
        with run.checking('Android readiness'):
            run.prepare_device(owned, Mock())
    assert 'TimeoutError' in (run.report / 'diagnostic-traceback.log').read_text()
    assert all(0 < call.kwargs['timeout'] <= 20 for call in run.command.call_args_list)
    owned.start.assert_not_called()


def test_repeated_ci_run_reuses_emulator_without_new_start(run, android_setup):
    owned = android_setup(['emulator-5554 device\n'])
    run.prepare_device(owned, Mock())
    run.prepare_device(owned, Mock())
    owned.start.assert_not_called()


def test_check_mode_missing_emulator_never_starts(run, android_setup):
    run.check_only = True
    owned = android_setup([''])
    with pytest.raises(RuntimeError, match='never starts'):
        run.prepare_device(owned, Mock())
    owned.start.assert_not_called()

@pytest.fixture
def application(run):
    def setup(package=None, launcher=None, launch=None, explicit=None, user='10'):
        def command(args, **kwargs):
            if 'get-current-user' in args:
                return result(user + '\n')
            if 'resolve-activity' in args:
                if '-n' in args:
                    return explicit if explicit is not None else result(ci.PACKAGE + '/' + ci.APP_ACTIVITY)
                return launcher if launcher is not None else result(ci.PACKAGE + '/' + ci.APP_ACTIVITY)
            if 'start' in args:
                return launch if launch is not None else result('Starting: Intent { ... }\nStatus: ok\n')
            return package if package is not None else result('package:/data/app/base.apk\npackage:/data/app/split.apk\n')
        return Mock(side_effect=command)
    return setup


@pytest.mark.parametrize('activity', [ci.APP_ACTIVITY, ci.PACKAGE + ci.APP_ACTIVITY])
def test_material_files_installed_launcher_and_launch_confirmed(run, application, activity):
    command = application(launcher=result(ci.PACKAGE + '/' + activity))
    run.prepare_application(command)
    calls = [call.args[0] for call in command.call_args_list]
    resolve = next(args for args in calls if 'resolve-activity' in args)
    assert resolve[resolve.index('--user') + 1] == '10'
    assert ['-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER'] == resolve[-6:-2]
    assert resolve[-2:] == ['-p', ci.PACKAGE]
    assert '--user' in next(args for args in calls if 'path' in args)
    start = next(args for args in calls if 'start' in args)
    assert start[-1] == ci.PACKAGE + '/' + ci.PACKAGE + ci.APP_ACTIVITY
    assert '-S' not in start and 'clear' not in start
    assert 'launch verified Status=ok' in (run.report / 'environment.log').read_text()


def test_material_files_absent_stops_before_resolution_or_launch(run, application):
    command = application(package=result(''))
    with pytest.raises(RuntimeError, match='package absent'):
        run.prepare_application(command)
    assert len(command.call_args_list) == 2


@pytest.mark.parametrize('output', ['No activity found\n', '', 'priority=0 preferredOrder=0\n'])
def test_installed_app_without_launcher_is_not_ready(run, application, output, monkeypatch):
    command = application(launcher=result(output))

    def expire(check, *args, **kwargs):
        assert check() is None
        raise TimeoutError('No launcher within deadline')

    monkeypatch.setattr(ci, 'wait_until', expire)
    with pytest.raises(TimeoutError):
        run.prepare_application(command)
    assert not any('start' in call.args[0] for call in command.call_args_list)


@pytest.mark.parametrize('phase', ['package', 'launcher', 'launch'])
def test_application_pm_and_launch_errors_are_diagnosed(run, application, phase):
    command = application(**{phase: subprocess.CompletedProcess([], 1, '', 'SecurityException: denied')})
    with pytest.raises(RuntimeError, match='SecurityException'):
        run.prepare_application(command)
    assert 'reason=SecurityException' in (run.report / 'environment.log').read_text()


@pytest.mark.parametrize('output', ['Error type 3\nError: Activity class does not exist',
                                  'Status: timeout\n', 'Permission Denial: not exported'])
def test_am_start_zero_exit_is_not_enough(run, application, output):
    command = application(launch=result(output))
    with pytest.raises(RuntimeError):
        run.prepare_application(command)


def test_launcher_alias_requires_confirmation_of_configured_appium_activity(run, application):
    command = application(launcher=result(ci.PACKAGE + '/.LauncherAlias'))
    run.prepare_application(command)
    explicit = [call for call in command.call_args_list
                if 'resolve-activity' in call.args[0] and '-n' in call.args[0]]
    assert len(explicit) == 1


def test_launcher_does_not_mask_invalid_appium_activity(run, application):
    command = application(launcher=result(ci.PACKAGE + '/.LauncherAlias'), explicit=result('No activity found'))
    with pytest.raises(RuntimeError):
        run.prepare_application(command)
    assert not any('start' in call.args[0] for call in command.call_args_list)


def test_application_check_only_does_not_launch(run, application):
    run.check_only = True
    command = application()
    run.prepare_application(command)
    assert not any('start' in call.args[0] for call in command.call_args_list)


def test_component_parser_rejects_substrings_and_other_output():
    assert ci.activity_component('Error: me.zhanghai.android.files/.filelist.FileListActivity missing') is None
    assert ci.activity_component('No activity found') is None
    assert ci.activity_component(ci.PACKAGE + '/' + ci.APP_ACTIVITY) == ci.PACKAGE + '/' + ci.PACKAGE + ci.APP_ACTIVITY


def test_launcher_resolution_retries_after_first_boot(run, application, monkeypatch):
    base = application()
    attempts = 0

    def command(args, **kwargs):
        nonlocal attempts
        if 'resolve-activity' in args:
            attempts += 1
            if attempts == 1:
                return result('No activity found\n')
        return base(args, **kwargs)

    monkeypatch.setattr(ci.threading, 'Event', Mock())
    run.prepare_application(command)
    assert attempts == 2
