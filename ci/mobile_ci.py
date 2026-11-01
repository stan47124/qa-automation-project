"""Bounded Mobile preflight, Appium ownership and pytest execution for Windows CI."""

import argparse
import errno
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import json
import os
import re
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


def appium_port_available():
    """Check absence even when Windows connect() times out instead of refusing.

    Never listen or adopt an existing socket. A bind race is handled by the owned
    Appium failing to start; its process tree alone is cleaned by OwnedProcesses.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == 'nt':
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(('127.0.0.1', 4723))
        except OSError as error:
            if error.errno == errno.EADDRINUSE or getattr(error, 'winerror', None) == 10048:
                return False
            raise  # Permission failures are not evidence of an absent server.
    return True


def device_states(output):
    return {parts[0]: parts[1] for line in output.splitlines()
            if len(parts := line.split()) >= 2 and parts[0] != 'List'}


def activity_component(output):
    """Read a component line, not a substring of a Package Manager diagnostic."""
    for line in output.splitlines():
        match = re.fullmatch(r'([\w.]+)/([\w.$]+)', line.strip(), flags=re.ASCII)
        if match:
            package, activity = match.groups()
            if activity.startswith('.'):
                activity = package + activity
            return package + '/' + activity
    return None


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
    def __init__(self, report, start_emulator=True, avd='Pixel_4', check_only=False):
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
        deadline = time.monotonic() + 180

        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise TimeoutError('Android readiness exceeded 180s; see emulator.log and adb-tools.log.')
            return value

        def command(args, **kwargs):
            return self.command(args, timeout=min(20, remaining()), **kwargs)

        devices = device_states(command([self.adb, 'devices', '-l']).stdout)
        emulator = None
        if DEVICE not in devices:
            if any(name.startswith('emulator-') for name in devices):
                raise RuntimeError('Another emulator exists; refusing to launch an additional instance.')
            if not self.start_emulator or self.check_only:
                raise RuntimeError(f'{DEVICE} is absent; Check/disabled autostart never starts an emulator.')
            binary = self.sdk / 'emulator/emulator.exe'
            if not binary.is_file():
                raise RuntimeError(f'Android Emulator executable missing: {binary}')
            avds = command([str(binary), '-list-avds']).stdout.splitlines()
            if self.avd not in avds:
                raise RuntimeError(f'AVD {self.avd} is not installed; no AVD is created automatically.')
            # Native AVD locking also prevents the same AVD being opened elsewhere.
            # Check fixed console/ADB ports before starting; never kill their owners.
            for port in (5554, 5555):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    try:
                        probe.bind(('127.0.0.1', port))
                    except OSError as error:
                        raise RuntimeError(f'Emulator port {port} unavailable; no duplicate started.') from error
            log = stack.enter_context((self.report / 'emulator.log').open('wb'))
            emulator = owned.start([str(binary), '-avd', self.avd, '-port', '5554',
                                    '-no-window', '-no-snapshot-save'], log, self.env)
            self.note('Started an owned emulator; it will be stopped after this run.')
        elif devices[DEVICE] not in ('device', 'offline'):
            raise RuntimeError(f'{DEVICE} is {devices[DEVICE]}; user action is required.')
        else:
            self.note('Reusing existing emulator; it will not be stopped.')

        def booted():
            states = device_states(command([self.adb, 'devices', '-l']).stdout)
            state = states.get(DEVICE)
            self.note(f'Android {DEVICE} adb_state={state or "absent"}')
            if state not in (None, 'offline', 'device'):
                raise RuntimeError(f'{DEVICE} is {state}; authorize/fix the device manually; no reset performed.')
            if state != 'device':
                return False
            try:
                boot = command([self.adb, '-s', DEVICE, 'shell', 'getprop', 'sys.boot_completed'], check=False)
                if boot.returncode or boot.stdout.strip() != '1':
                    return False
                pm = command([self.adb, '-s', DEVICE, 'shell', 'pm', 'path', 'android'], check=False)
                return pm.returncode == 0 and any(line.startswith('package:') for line in pm.stdout.splitlines())
            except subprocess.TimeoutExpired:
                self.note('Android shell readiness command timed out; retry within the shared deadline.')
                return False

        wait_until(booted, remaining(), 'Android boot_completed=1 and Package Manager ready',
                   emulator, log=self.note, report=self.report)
        self.prepare_application(command)
        command([self.adb, '-s', DEVICE, 'shell', 'test', '-d', str(BASE_DIRECTORY)])
        self.note(f'Android {DEVICE} ready for Mobile tests; AVD={self.avd}; owned={emulator is not None}.')
        return emulator

    def prepare_application(self, command):
        shell = [self.adb, '-s', DEVICE, 'shell']

        def checked(phase, args, *, allow_missing=False):
            response = command(shell + args, check=False)
            text = response.stdout + '\n' + response.stderr
            reason = next((name for name in ('SecurityException', 'Permission Denial', 'Error type 3',
                                             'Error:', 'Exception', 'Failure', 'No activity found')
                           if name in text), None)
            self.note(f'Material Files {phase}: exit={response.returncode}; reason={reason or "none"}')
            if response.returncode or (reason and not (allow_missing and reason == 'No activity found')):
                raise RuntimeError(f'Material Files {phase} failed: exit={response.returncode}; '
                                   f'reason={reason or "command failure"}; see adb-tools.log.')
            return response.stdout

        with self.checking('Material Files package installation'):
            user = checked('Android user', ['am', 'get-current-user']).strip()
            if not re.fullmatch(r'[0-9]+', user):
                raise RuntimeError('Cannot determine current Android user; see adb-tools.log.')
            self.note(f'Material Files Android user={user}')
            package = checked('package lookup', ['pm', 'path', '--user', user, PACKAGE])
            paths = [line for line in package.splitlines() if line.startswith('package:')]
            self.note(f'Material Files installed={bool(paths)} apk_paths={len(paths)} user={user}')
            if not paths:
                raise RuntimeError(f'Material Files package absent for Android user {user}; no install/reset performed.')

        intent = ['-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER']
        resolve = ['cmd', 'package', 'resolve-activity', '--brief', '--user', user]
        with self.checking('Material Files launcher Activity resolution'):
            def find_launcher():
                output = checked('MAIN/LAUNCHER lookup', resolve + intent + ['-p', PACKAGE], allow_missing=True)
                component = activity_component(output)
                self.note(f'Material Files launcher={component or "unresolved"}')
                if component and component.split('/')[0] != PACKAGE:
                    raise RuntimeError('Resolved launcher belongs to an unexpected package; see adb-tools.log.')
                return component

            # Package Manager can answer pm path before resolving launcher intents
            # after boot. All commands still share prepare_device's 180s budget.
            launcher = wait_until(find_launcher, 30, 'Material Files MAIN/LAUNCHER Activity (package installed)',
                                  log=self.note, report=self.report)
            configured = activity_component(PACKAGE + '/' + APP_ACTIVITY)
            if not configured:
                raise RuntimeError('Appium APP_ACTIVITY is not a valid component.')
            # A launcher alias may differ from Appium's explicit Activity. Confirm
            # that target from the installed package rather than guessing a name.
            if configured != launcher:
                explicit = activity_component(checked('Appium Activity lookup', resolve + ['-n', configured]))
                if explicit != configured:
                    raise RuntimeError('Installed launcher differs from Appium APP_ACTIVITY and configured '
                                       'Activity cannot be resolved; see adb-tools.log.')
            self.note(f'Material Files Appium component confirmed={configured}')

        if self.check_only:
            self.note('Check mode: launcher resolved; application launch is deferred to Test mode.')
            return
        with self.checking('Material Files launch verification'):
            launch = checked('launch', ['am', 'start', '-W', '--user', user, *intent, '-n', configured])
            if not re.search(r'^Status:\s*ok\s*$', launch, re.MULTILINE):
                raise RuntimeError('Material Files launch did not report Status: ok; see adb-tools.log.')
            self.note('Material Files launch verified Status=ok; data preserved; Appium may now start.')

    def prepare_appium(self, owned, stack, cli):
        # One deadline covers discovery, startup and readiness (including retries).
        deadline = time.monotonic() + 60
        server = None
        attempt = 0
        with self.checking('Wait Appium ready timeout_s=60'):
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Appium did not return /status ready=True within 60s; '
                                       'see environment.log, appium.log (if owned), diagnostic-traceback.log. '
                                       'Existing processes were not stopped.')
                if server is not None and server.poll() is not None:
                    raise RuntimeError(f'Owned Appium exited with {server.returncode}; see appium.log.')
                attempt += 1
                status = None
                try:
                    status = read_appium('/status', log=self.note, report=self.report,
                                         timeout=min(2, remaining))
                except (TimeoutError, urllib.error.URLError) as error:
                    if not is_timeout(error):
                        raise
                    # Timeout alone does not prove absence. Test exclusive bind below.
                    self.note(f'Appium poll={attempt} transport timeout exception={type(error).__name__}; retrying.')
                if status is not None and not isinstance(status, dict):
                    raise RuntimeError('Appium /status value must be a JSON object.')
                if time.monotonic() >= deadline:
                    continue
                if status is not None and status.get('ready') is True:
                    self.note('Owned Appium ready.' if server is not None else
                              'Reusing existing Appium; its process and logs are not modified.')
                    break
                if status is None and server is None and not self.check_only:
                    with self.checking('Appium exclusive bind probe 127.0.0.1:4723'):
                        free = appium_port_available()
                    if free:
                        log = stack.enter_context((self.report / 'appium.log').open('wb'))
                        with self.checking('Start owned Appium'):
                            server = owned.start(cli + ['--address', '127.0.0.1', '--port', '4723',
                                                        '--base-path', '/', '--log-level', 'info',
                                                        '--log-no-colors', '--log-timestamp'], log, self.env)
                        self.note('Started an owned Appium server; waiting for /status ready=True.')
                    else:
                        self.note('Port 4723 occupied; waiting for existing server, no duplicate started.')
                if self.check_only and status is None:
                    self.note('Appium unavailable; Check never starts processes; retrying status only.')
                remaining = deadline - time.monotonic()
                self.note(f'Appium poll={attempt} ready=False remaining_s={max(0, remaining):.3f}')
                if remaining > 0:
                    threading.Event().wait(min(1, remaining))
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
                self.note('Closing owned process scope; only this run\'s process trees will be stopped. '
                          'Existing emulator and Appium are preserved.')


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
        run = MobileRun(report, os.getenv('START_ANDROID_EMULATOR', 'true').lower() == 'true',
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
