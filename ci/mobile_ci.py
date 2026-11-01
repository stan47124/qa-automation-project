"""Bounded Mobile preflight, Appium ownership and pytest execution for Windows CI."""

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from uuid import uuid4
import xml.etree.ElementTree as ET

from windows_resources import DeviceLock, OwnedProcesses

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests/mobile'))
from mobile_config import APP_ACTIVITY, APPIUM_URL, BASE_DIRECTORY, DEVICE, PACKAGE  # noqa: E402


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def save_traceback(report, description, error):
    if report is not None:
        with (Path(report) / 'diagnostic-traceback.log').open('a', encoding='utf-8') as output:
            output.write(f'\n[{timestamp()}] {description}\n')
            output.writelines(traceback.format_exception(error))


def is_timeout(error):
    pending, seen = [error], set()
    while pending:
        item = pending.pop()
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, (TimeoutError, subprocess.TimeoutExpired)):
            return True
        pending.extend([getattr(item, '__cause__', None), getattr(item, '__context__', None),
                        getattr(item, 'reason', None)])
    return False


@contextmanager
def operation(description, *, log=None, report=None):
    emit = log or (lambda message: print(f'[{timestamp()}] {message}', flush=True))
    started = time.perf_counter()
    emit(f'START {description}')
    try:
        yield
    except BaseException as error:
        emit(f'END {description} status=ERROR elapsed_s={time.perf_counter() - started:.3f} '
             f'exception={type(error).__name__}')
        if is_timeout(error):
            # Save before cleanup can raise another exception and mask the initiating timeout.
            save_traceback(report, description, error)
        raise
    else:
        emit(f'END {description} status=OK elapsed_s={time.perf_counter() - started:.3f}')


def wait_until(check, timeout, description, process=None, *, log=None, report=None):
    with operation(f'Wait {description} timeout_s={timeout}', log=log, report=report):
        deadline = time.monotonic() + timeout
        attempt = 0
        while True:
            if process is not None and process.poll() is not None:
                raise RuntimeError(f'{description}: owned process exited with {process.returncode}')
            attempt += 1
            with operation(f'{description} poll={attempt}', log=log, report=report):
                value = check()
            remaining = deadline - time.monotonic()
            if log:
                log(f'{description} poll={attempt} ready={bool(value)} remaining_s={remaining:.3f}')
            if remaining < 0 or (remaining == 0 and not value):
                raise TimeoutError(f'Timed out waiting for {description} (limit={timeout}s, polls={attempt})')
            if value:
                return value
            threading.Event().wait(min(1, remaining))


def read_appium(path, *, log=None, report=None, timeout=2):
    # No proxy, credentials or external URL: only the configured local Appium.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with operation(f'Appium GET {path} socket_timeout_s={timeout}', log=log, report=report):
        try:
            with operation(f'HTTP open {path}', log=log, report=report):
                response = opener.open(APPIUM_URL + path, timeout=timeout)
            with response:
                with operation(f'HTTP body {path}', log=log, report=report):
                    value = json.load(response)['value']
            return value
        except urllib.error.HTTPError as error:
            if log:
                log(f'Appium GET {path}: HTTP status={error.code}')
            raise RuntimeError(f'Appium endpoint {path} returned HTTP {error.code}') from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, ConnectionRefusedError):
                if log:
                    log(f'Appium GET {path}: connection refused; server unavailable')
                return None
            # A transport timeout or permission error is not proof of an absent server.
            raise


def device_states(output):
    return {parts[0]: parts[1] for line in output.splitlines()
            if len(parts := line.split()) >= 2 and parts[0] != 'List'}


def appium_command():
    node = shutil.which('node.exe')
    shim = shutil.which('appium.cmd')
    if not node or not shim:
        raise RuntimeError('Node.js and appium.cmd must be available in the agent PATH.')
    package = Path(shim).parent / 'node_modules/appium/package.json'
    if not package.is_file():
        raise RuntimeError('Cannot resolve the installed npm Appium CLI; inspect appium.cmd installation.')
    metadata = json.loads(package.read_text(encoding='utf-8'))
    entry = metadata['bin']
    entry = entry['appium'] if isinstance(entry, dict) else entry
    return [node, str(package.parent / entry)]


class MobileRun:
    def __init__(self, report, start_emulator=False, avd='Pixel_4', check_only=False):
        self.report = Path(report).resolve()
        self.start_emulator = start_emulator
        self.avd = avd
        self.check_only = check_only
        self.owns_report = False
        self.env = os.environ.copy()
        sdk = self.env.get('ANDROID_HOME') or self.env.get('ANDROID_SDK_ROOT')
        sdk = sdk or str(Path(self.env.get('LOCALAPPDATA', '')) / 'Android/Sdk')
        self.sdk = Path(sdk)
        other = self.env.get('ANDROID_SDK_ROOT')
        self.sdk_conflict = bool(other and Path(other).resolve() != self.sdk.resolve())
        self.env['ANDROID_HOME'] = self.env['ANDROID_SDK_ROOT'] = str(self.sdk)
        self.env['PATH'] = str(self.sdk / 'platform-tools') + os.pathsep + self.env.get('PATH', '')
        self.adb = str(self.sdk / 'platform-tools/adb.exe')

    def note(self, message):
        message = f'[{timestamp()}] {message}'
        print(message, flush=True)
        with (self.report / 'environment.log').open('a', encoding='utf-8') as output:
            output.write(message + '\n')

    def checking(self, description):
        return operation(description, log=self.note, report=self.report)

    def command(self, args, timeout=20, check=True):
        command_line = subprocess.list2cmdline(list(map(str, args)))
        with self.checking(f'Command {command_line} timeout_s={timeout}'):
            with (self.report / 'adb-tools.log').open('a', encoding='utf-8') as output:
                output.write(f'[{timestamp()}] START {command_line}\n')
                try:
                    result = subprocess.run(args, env=self.env, capture_output=True, text=True,
                                            encoding='utf-8', errors='replace', timeout=timeout)
                except subprocess.TimeoutExpired as error:
                    for partial in (error.stdout, error.stderr):
                        if partial:
                            output.write(partial.decode('utf-8', errors='replace') if isinstance(partial, bytes) else partial)
                    output.write(f'\n[{timestamp()}] TIMEOUT limit_s={timeout}\n')
                    raise
                output.write(result.stdout + result.stderr + '\n')
                output.write(f'[{timestamp()}] END exit={result.returncode}\n')
            if check and result.returncode:
                raise RuntimeError(f'{Path(args[0]).name} failed with exit {result.returncode}; see adb-tools.log')
            return result

    def prepare_device(self, owned, stack):
        devices = device_states(self.command([self.adb, 'devices', '-l']).stdout)
        emulator = None
        if DEVICE not in devices:
            if any(name.startswith('emulator-') for name in devices):
                raise RuntimeError('Another emulator exists; refusing to launch an additional instance.')
            if not self.start_emulator or self.check_only:
                raise RuntimeError(f'{DEVICE} is absent; start the existing AVD or opt in to START_ANDROID_EMULATOR.')
            binary = self.sdk / 'emulator/emulator.exe'
            avds = self.command([str(binary), '-list-avds']).stdout.splitlines()
            if self.avd not in avds:
                raise RuntimeError(f'AVD {self.avd} is not installed; no AVD is created automatically.')
            log = stack.enter_context((self.report / 'emulator.log').open('wb'))
            emulator = owned.start([str(binary), '-avd', self.avd, '-port', '5554',
                                    '-no-window', '-no-snapshot-save'], log, self.env)
            self.note('Started an owned emulator; it will be stopped after this run.')
        elif devices[DEVICE] not in ('device', 'offline'):
            raise RuntimeError(f'{DEVICE} is {devices[DEVICE]}; user action is required.')
        else:
            self.note('Reusing existing emulator; it will not be stopped.')

        def booted():
            states = device_states(self.command([self.adb, 'devices', '-l']).stdout)
            if states.get(DEVICE) != 'device':
                return False
            return self.command([self.adb, '-s', DEVICE, 'shell', 'getprop', 'sys.boot_completed'],
                                check=False).stdout.strip() == '1'

        wait_until(booted, 180, 'Android boot_completed=1', emulator, log=self.note, report=self.report)
        self.command([self.adb, '-s', DEVICE, 'shell', 'pm', 'path', PACKAGE])
        activity = self.command([self.adb, '-s', DEVICE, 'shell', 'cmd', 'package',
                                 'resolve-activity', '--brief', PACKAGE]).stdout
        if not any(name in activity for name in (PACKAGE + '/' + APP_ACTIVITY,
                                                 PACKAGE + '/' + PACKAGE + APP_ACTIVITY)):
            raise RuntimeError('Material Files activity is not installed or cannot be resolved.')
        self.command([self.adb, '-s', DEVICE, 'shell', 'test', '-d', str(BASE_DIRECTORY)])
        return emulator

    def prepare_appium(self, owned, stack, cli):
        status = read_appium('/status', log=self.note, report=self.report)
        server = None
        if status is None:
            if self.check_only:
                raise RuntimeError('Appium is unavailable; Check never starts processes.')
            with self.checking('Appium TCP port probe 127.0.0.1:4723 timeout_s=2'):
                try:
                    with socket.create_connection(('127.0.0.1', 4723), timeout=2):
                        raise RuntimeError('Port 4723 is occupied without a valid Appium status; no process stopped.')
                except ConnectionRefusedError:
                    pass
            log = stack.enter_context((self.report / 'appium.log').open('wb'))
            with self.checking('Start owned Appium'):
                server = owned.start(cli + ['--address', '127.0.0.1', '--port', '4723', '--base-path', '/',
                                             '--log-level', 'info', '--log-no-colors', '--log-timestamp'], log, self.env)
            self.note('Started an owned Appium server.')
        else:
            self.note('Reusing existing Appium; its process and logs are not modified.')
        wait_until(lambda: (read_appium('/status', log=self.note, report=self.report) or {}).get('ready') is True,
                   60, 'Appium ready', server, log=self.note, report=self.report)
        # GET /sessions is not a portable Appium endpoint. DeviceLock, held by
        # execute() throughout preflight, pytest and cleanup, coordinates runners.
        # Manual/non-cooperating clients must not use this device during CI.
        self.note('Appium ready; device concurrency is controlled by DeviceLock, not GET /sessions.')

    def execute(self):
        if os.name != 'nt':
            raise RuntimeError('Mobile CI requires a Windows agent.')
        self.report.mkdir(parents=True, exist_ok=False)
        self.owns_report = True
        self.note(f'Mobile device: {DEVICE}; Appium: {APPIUM_URL}')
        if self.sdk_conflict:
            raise RuntimeError('ANDROID_HOME and ANDROID_SDK_ROOT refer to different SDK directories.')
        with self.checking('Mobile resource scope'), ExitStack() as stack:
            with self.checking(f'Acquire DeviceLock {DEVICE}'):
                stack.enter_context(DeviceLock())
            if not Path(self.adb).is_file():
                raise RuntimeError('Android platform-tools/adb.exe is missing.')
            with self.checking('Resolve installed Appium CLI'):
                cli = appium_command()
            self.command(['java', '-version'])
            self.command([cli[0], '--version'])
            self.command(cli + ['--version'])
            drivers = json.loads(self.command(cli + ['driver', 'list', '--installed', '--json'], timeout=45).stdout)
            if 'uiautomator2' not in drivers:
                raise RuntimeError('UiAutomator2 must be installed manually; CI will not install drivers.')
            # ADB failure stops here, before starting any managed process.
            self.command([self.adb, 'devices', '-l'])
            with self.checking('Initialize owned process scope'):
                owned = stack.enter_context(OwnedProcesses())
            emulator = None
            try:
                with self.checking('Android readiness and application checks'):
                    emulator = self.prepare_device(owned, stack)
                with self.checking('Appium preflight'):
                    self.prepare_appium(owned, stack, cli)
                if self.check_only:
                    self.note('Mobile preflight passed; tests were not started.')
                    return 0
                self.note('Running only tests/mobile with noReset=True; no data reset requested.')
                log = stack.enter_context((self.report / 'pytest-console.log').open('wb'))
                with self.checking('Start Mobile pytest'):
                    process = owned.start(
                        [sys.executable, '-m', 'pytest', 'tests/mobile', '-v',
                         f'--basetemp={self.report}/pytest-tmp',
                         f'--junitxml={self.report}/junit.xml',
                         f'--alluredir={self.report}/allure-results'], log, self.env)
                with self.checking('Wait Mobile pytest timeout_s=600'):
                    code = process.wait(timeout=600)
                self.note(f'Mobile pytest exit={code}; see pytest-console.log and JUnit.')
                return code
            finally:
                if emulator is not None and emulator.poll() is None:
                    with self.checking('Stop owned emulator'):
                        self.command([self.adb, '-s', DEVICE, 'emu', 'kill'], check=False)


def infrastructure_report(report, message):
    """Report setup failure honestly, without inventing six executed tests."""
    if not report.is_dir():
        return
    xml = report / 'junit.xml'
    if xml.exists():
        return
    suite = ET.Element('testsuite', name='Mobile infrastructure', tests='1', errors='1', failures='0', skipped='0')
    case = ET.SubElement(suite, 'testcase', name='Mobile environment readiness', classname='mobile.ci')
    ET.SubElement(case, 'error', message=message).text = message
    ET.ElementTree(suite).write(xml, encoding='utf-8', xml_declaration=True)
    results = report / 'allure-results'
    results.mkdir(exist_ok=True)
    identity = uuid4().hex
    (results / f'{identity}-result.json').write_text(json.dumps({
        'uuid': identity, 'name': 'Mobile environment readiness', 'fullName': 'mobile.ci.environment',
        'status': 'broken', 'stage': 'finished', 'statusDetails': {'message': message},
        'labels': [{'name': 'feature', 'value': 'Mobile CI infrastructure'}],
    }), encoding='utf-8')


def attach_failure_logs(report):
    """Append only this runner's logs; preserve test labels, steps and screenshots."""
    results = report / 'allure-results'
    failures = []
    for path in results.glob('*-result.json'):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue  # Interrupted result stays in the archive for inspection.
        if record.get('status') in ('broken', 'failed'):
            failures.append((path, record))
    if not failures:
        return
    attachments = []
    for name in ('environment.log', 'adb-tools.log', 'appium.log', 'emulator.log', 'diagnostic-traceback.log'):
        source = report / name
        if source.is_file():
            target = uuid4().hex + '-' + name
            shutil.copyfile(source, results / target)
            attachments.append({'name': 'Mobile CI: ' + name, 'source': target, 'type': 'text/plain'})
    for path, record in failures:
        record.setdefault('attachments', []).extend(attachments)
        path.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    destination = os.environ.get('REPORT_ROOT')
    if not destination:
        parser.error('REPORT_ROOT must specify a new Mobile report directory.')
    report = Path(destination).resolve()
    if report.exists():
        parser.error('Mobile report directory already exists; choose a new run.')
    run = None
    try:
        run = MobileRun(report, os.getenv('START_ANDROID_EMULATOR', 'false').lower() == 'true',
                        os.getenv('ANDROID_AVD', 'Pixel_4'), args.check)
        code = run.execute()
        attach_failure_logs(report)
        return code
    except (Exception, KeyboardInterrupt) as error:
        message = f'{type(error).__name__}: {error}'
        print(message, file=sys.stderr)
        if run is not None and run.owns_report:
            save_traceback(report, 'Mobile runner failure (including cleanup)', error)
            infrastructure_report(report, message)
            attach_failure_logs(report)
        return 2


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '_child':
        # Parent closes stdin without approval when Job Object assignment fails.
        if sys.stdin.buffer.readline() != b'go\n':
            sys.exit(2)
        sys.exit(subprocess.call(sys.argv[2:]))
    os.chdir(ROOT)
    sys.exit(main())
