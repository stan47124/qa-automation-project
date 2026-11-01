"""CI safety checks, separate from the 22 application tests in tests/."""

import json
from contextlib import contextmanager, nullcontext
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
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
        result('1\n'), result('package:/data/app/material-files/base.apk'),
        result(ci.PACKAGE + '/' + ci.APP_ACTIVITY), result(),
    ])
    assert run.prepare_device(owned, Mock()) is None
    owned.start.assert_not_called()
    assert not any('kill' in call.args[0] for call in run.command.call_args_list)


@pytest.mark.parametrize('devices', ['List of devices attached\n',
                                   'List of devices attached\nemulator-5556 device\n'])
def test_missing_or_other_emulator_does_not_start_by_default(run, devices):
    owned = Mock()
    run.command = Mock(return_value=result(devices))
    with pytest.raises(RuntimeError):
        run.prepare_device(owned, Mock())
    owned.start.assert_not_called()


def test_existing_appium_is_not_owned(run, monkeypatch):
    owned = Mock()
    monkeypatch.setattr(ci, 'read_appium', lambda path: [] if path == '/sessions' else {'ready': True})
    run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()


def test_busy_appium_is_rejected_without_stopping_it(run, monkeypatch):
    owned = Mock()
    monkeypatch.setattr(ci, 'read_appium', lambda path: [{}] if path == '/sessions' else {'ready': True})
    with pytest.raises(RuntimeError, match='sessions'):
        run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()


def test_check_mode_never_starts_appium(run, monkeypatch):
    run.check_only = True
    owned = Mock()
    monkeypatch.setattr(ci, 'read_appium', lambda path: None)
    with pytest.raises(RuntimeError, match='Check never starts'):
        run.prepare_appium(owned, Mock(), ['node', 'appium'])
    owned.start.assert_not_called()


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
    assert len(kill_calls) == int(owned_emulator)


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
