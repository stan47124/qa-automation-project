"""Opt-in Web UI command metadata; never persist command parameters or responses."""
from datetime import datetime, timezone
import ctypes
from ctypes import wintypes
import functools
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from uuid import uuid4

import pytest
from selenium.common import exceptions
from selenium.webdriver.remote.command import Command
from selenium.webdriver.remote.webelement import WebElement

ENVIRONMENT = 'QA_WEBDRIVER_DIAGNOSTICS'
MAX_EVENTS = 10000
COMMANDS = {value for key, value in vars(Command).items()
            if key.isupper() and isinstance(value, str)}
ERROR_TYPES = {value for value in vars(exceptions).values()
               if isinstance(value, type) and issubclass(value, BaseException)}
ERROR_TYPES.update({OSError, RuntimeError, ValueError, TypeError, TimeoutError,
                    KeyboardInterrupt, SystemExit, AssertionError})
OPERATIONS = {
    '#first-name': 'checkout.first_name', '#last-name': 'checkout.last_name',
    '#postal-code': 'checkout.postal_code',
    '[data-test="checkout"]': 'cart.checkout',
    '[data-test="continue"]': 'checkout.continue',
    '[data-test="finish"]': 'checkout.finish',
}
TESTS = {'test_successful_login', 'test_invalid_credentials', 'test_locked_out_user',
         'test_sort_products_by_price', 'test_add_product_to_cart',
         'test_remove_product_from_cart', 'test_complete_checkout',
         'test_checkout_required_fields'}


def anonymous(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]


def error_type(error):
    return type(error).__name__ if type(error) in ERROR_TYPES else 'OtherException'


def windows_context():
    """Query this Python token/session; do not spawn a shell or retain a raw SID."""
    result = {'user_id': None, 'session_id': None, 'session_type': 'unknown',
              'process_id': os.getpid(),
              'captured_utc': datetime.now(timezone.utc).isoformat(timespec='milliseconds')}
    if os.name != 'nt':
        return result
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                         wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    token = wintypes.HANDLE()
    sid_text = wintypes.LPWSTR()
    try:
        session = wintypes.DWORD()
        if kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
            result['session_id'] = session.value
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise ctypes.WinError(ctypes.get_last_error())
        result['user_id'] = anonymous(sid_text.value)

        class Flags(ctypes.Structure):
            _fields_ = [('inherit', wintypes.BOOL), ('reserved', wintypes.BOOL),
                        ('flags', wintypes.DWORD)]

        user.GetProcessWindowStation.restype = wintypes.HANDLE
        user.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                  wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        flags = Flags()
        if user.GetUserObjectInformationW(user.GetProcessWindowStation(), 1, ctypes.byref(flags),
                                          ctypes.sizeof(flags), ctypes.byref(size)):
            result['session_type'] = ('interactive_window_station' if flags.flags & 1
                                      else 'noninteractive_window_station')
    except Exception as error:
        result['error_type'] = error_type(error)
    finally:
        if sid_text:
            kernel.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        if token:
            kernel.CloseHandle(token)
    return result


def directory_context(path, workspace):
    if not path:
        return {'available': False}
    try:
        directory = Path(path).resolve()
        return {'path_id': anonymous(os.path.normcase(str(directory))),
                'inside_workspace': directory.is_relative_to(workspace.resolve()),
                'exists': directory.is_dir(), 'read_access_hint': os.access(directory, os.R_OK),
                'write_access_hint': os.access(directory, os.W_OK),
                'write_probe_performed': False, 'effective_acl_verified': False}
    except Exception as error:
        return {'available': False, 'error_type': error_type(error)}


def safe_version(value):
    if not isinstance(value, str):
        return None
    version = value.split(' ')[0]
    return version if re.fullmatch(r'\d+(?:\.\d+){0,3}', version) else None


def safe_capabilities(capabilities):
    safe = {'browserVersion': safe_version(capabilities.get('browserVersion'))}
    for key, choices in {
        'browserName': {'chrome', 'chromium'},
        'platformName': {'windows', 'linux', 'mac', 'macos'},
        'pageLoadStrategy': {'normal', 'eager', 'none'},
        'unhandledPromptBehavior': {'dismiss', 'accept', 'dismiss and notify', 'accept and notify', 'ignore'},
    }.items():
        value = capabilities.get(key)
        if isinstance(value, str) and value.lower() in choices:
            safe[key] = value.lower()
    for key in ['acceptInsecureCerts', 'setWindowRect', 'strictFileInteractability']:
        if type(capabilities.get(key)) is bool:
            safe[key] = capabilities[key]
    chrome = capabilities.get('chrome', {})
    if isinstance(chrome, dict):
        safe['chromedriverVersion'] = safe_version(chrome.get('chromedriverVersion'))
    return safe


def browser_context(driver, workspace, basetemp):
    """One setup-only read before recording/user interactions; never retry it."""
    capabilities = driver.capabilities if isinstance(driver.capabilities, dict) else {}
    context = {'capabilities': safe_capabilities(capabilities),
               'headless_requested': os.getenv('HEADLESS', '').strip().lower() in {'true', '1', 'yes'},
               'profile_id': None, 'temporary_profile_name': None,
               'profile_under_temp_candidate': None,
               'pytest_temp': directory_context(basetemp, workspace),
               'os_temp_candidate': directory_context(os.getenv('TEMP') or os.getenv('TMP'), workspace),
               'os_temp_source': 'TEMP_or_TMP_environment_candidate',
               'viewport': None, 'headless_observed': None, 'setup_probe_commands': 1}
    chrome = capabilities.get('chrome')
    profile = chrome.get('userDataDir') if isinstance(chrome, dict) else None
    if isinstance(profile, str) and profile:
        context['profile_id'] = anonymous(os.path.normcase(os.path.abspath(profile)))
        context['temporary_profile_name'] = bool(re.fullmatch(r'scoped_dir[\w.-]+', Path(profile).name))
        candidate = os.getenv('TEMP') or os.getenv('TMP')
        if candidate:
            context['profile_under_temp_candidate'] = Path(profile).resolve().is_relative_to(Path(candidate).resolve())
    try:
        observed = driver.execute_script('''return {
            width: window.innerWidth, height: window.innerHeight,
            dpr: window.devicePixelRatio,
            headless: navigator.userAgent.includes('HeadlessChrome')
        };''')
        if isinstance(observed, dict):
            numbers = {key: observed.get(key) for key in ['width', 'height', 'dpr']}
            if all(type(value) in (int, float) and math.isfinite(value) and 0 < value <= 32768
                   for value in numbers.values()):
                context['viewport'] = numbers
            if type(observed.get('headless')) is bool:
                context['headless_observed'] = observed['headless']
    except Exception as error:
        context['probe_error_type'] = error_type(error)
    return context


class Recorder:
    def __init__(self, driver, test_name, context):
        self.driver, self.context = driver, context
        self.test = test_name if test_name in TESTS else 'other_ui_test'
        self.original = driver.execute
        self.had_instance_execute = 'execute' in driver.__dict__
        self.instance_execute = driver.__dict__.get('execute')
        self.events, self.elements = [], {}
        self.sequence = self.dropped = self.diagnostic_errors = 0
        self.closed = False

        @functools.wraps(self.original)
        def traced(driver_command, params=None):
            event = None
            try:
                self.sequence += 1
                operation = self.elements.get(params.get('id')) if isinstance(params, dict) else None
                event = {'sequence': self.sequence,
                         'command': driver_command if isinstance(driver_command, str) and driver_command in COMMANDS else 'other',
                         'operation': operation, 'started_utc': datetime.now(timezone.utc).isoformat(timespec='microseconds')}
                started = time.perf_counter_ns()
            except Exception:
                self.diagnostic_errors += 1
            try:
                response = self.original(driver_command, params)
            except BaseException as error:
                try:
                    self.record(event, started, error)
                except Exception:
                    self.diagnostic_errors += 1
                raise
            else:
                try:
                    self.record(event, started, None)
                except Exception:
                    self.diagnostic_errors += 1
                try:
                    self.remember(driver_command, params, response)
                except Exception:
                    self.diagnostic_errors += 1
                return response

        self.wrapper = traced
        driver.execute = traced

    def remember(self, command, params, response):
        if command not in {'findElement', 'findChildElement'} or not isinstance(params, dict):
            return
        operation = OPERATIONS.get(params.get('value')) if params.get('using') == 'css selector' else None
        value = response.get('value') if isinstance(response, dict) else None
        if operation and isinstance(value, WebElement) and len(self.elements) < 128:
            self.elements[value.id] = operation

    def record(self, event, started, error):
        if event is None:
            return
        event['duration_ms'] = round((time.perf_counter_ns() - started) / 1000000, 4)
        event['outcome'] = 'ok' if error is None else 'exception'
        if error is not None:
            event['exception_type'] = error_type(error)
        if len(self.events) < MAX_EVENTS:
            self.events.append(event)
        else:
            self.dropped += 1

    def restore(self):
        if self.driver.execute is self.wrapper:
            if self.had_instance_execute:
                self.driver.execute = self.instance_execute
            else:
                del self.driver.execute

    def document(self):
        return {'schema': 1, 'test': self.test, 'context': self.context, 'commands': self.events,
                'dropped_commands': self.dropped, 'diagnostic_errors': self.diagnostic_errors}


class Monitor:
    def __init__(self, config, output):
        self.config, self.output = config, Path(output)
        self.active, self.profiles = {}, set()
        self.completed = self.failed = 0

    def attach(self, node, browser):
        recorder = None
        try:
            root = Path(self.config.rootpath).resolve()
            output = self.output.resolve()
            artifacts = (root / 'artifacts').resolve()
            if not artifacts.is_relative_to(root) or not output.is_relative_to(artifacts):
                raise ValueError('Diagnostic output must be inside artifacts')
            output.mkdir(parents=True, exist_ok=True)
            context = browser_context(browser.config.driver, root, self.config.getoption('basetemp'))
            context['pytest_process'] = windows_context()
            profile = context.get('profile_id')
            context['profile_unique_in_run'] = profile not in self.profiles if profile else None
            temp = context['profile_under_temp_candidate']
            context['isolated_temporary_profile'] = (
                bool(context['temporary_profile_name'] and temp and context['profile_unique_in_run'])
                if profile and temp is not None else None)
            if profile:
                self.profiles.add(profile)
            recorder = Recorder(browser.config.driver, node.name, context)
            self.active[node.nodeid] = (recorder, output / ('browser-' + uuid4().hex + '.json'))
        except Exception:
            if recorder is not None:
                recorder.restore()
            self.failed += 1

    def close(self, key):
        item = self.active.pop(key, None)
        if item is None:
            return
        recorder, destination = item
        try:
            recorder.restore()
            with destination.open('x', encoding='utf-8') as stream:
                json.dump(recorder.document(), stream, ensure_ascii=True)
            self.completed += 1
        except Exception:
            self.failed += 1


def pytest_configure(config):
    output = os.getenv(ENVIRONMENT)
    if output and not config.option.collectonly:
        config._qa_webdriver_monitor = Monitor(config, output)


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    outcome = yield
    monitor = getattr(request.config, '_qa_webdriver_monitor', None)
    if monitor is None or fixturedef.argname != 'ui_browser' or outcome.excinfo is not None:
        return
    try:
        root = Path(request.config.rootpath).resolve() / 'tests' / 'ui'
        if Path(request.node.path).resolve().is_relative_to(root):
            monitor.attach(request.node, outcome.get_result())
    except Exception:
        monitor.failed += 1


def pytest_fixture_post_finalizer(fixturedef, request):
    monitor = getattr(request.config, '_qa_webdriver_monitor', None)
    if monitor is not None and fixturedef.argname == 'ui_browser':
        monitor.close(request.node.nodeid)


def pytest_sessionfinish(session):
    monitor = getattr(session.config, '_qa_webdriver_monitor', None)
    if monitor is not None:
        for key in list(monitor.active):
            monitor.close(key)


def pytest_unconfigure(config):
    monitor = getattr(config, '_qa_webdriver_monitor', None)
    if monitor is not None:
        for key in list(monitor.active):
            monitor.close(key)


def pytest_terminal_summary(terminalreporter):
    monitor = getattr(terminalreporter.config, '_qa_webdriver_monitor', None)
    if monitor is not None:
        terminalreporter.write_line(f'WebDriver diagnostics: {monitor.completed} session files; {monitor.failed} unavailable outputs')
