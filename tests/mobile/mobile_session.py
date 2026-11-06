"""One Appium session attempt with bounded, allowlisted startup diagnostics."""

import json
import re
import subprocess
import time

import allure

LOGCAT_LIMIT = 400
LOGCAT_FILTERS = ['AndroidRuntime:E', 'ActivityManager:I', 'TestRunner:I',
                  'Instrumentation:I', 'UiAutomator2:I', 'appium:I', '*:S']


def device_time(adb, device, run):
    response = run([adb, '-s', device, 'shell', 'date', '+%m-%d %H:%M:%S.000'],
                   capture_output=True, text=True, timeout=5)
    value = response.stdout.strip()
    return value if response.returncode == 0 and re.fullmatch(r'\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.000', value) else None


def logcat_summary(raw, since=None):
    events = []
    lines = raw.splitlines()[-LOGCAT_LIMIT:]
    for line in lines:
        stamp = re.match(r'^(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s', line)
        if not stamp or (since and stamp[1] < since):
            continue
        # Arbitrary Android messages can contain credentials or personal data.
        # Retain classifications and known Java exception types, never raw text.
        if 'io.appium.uiautomator2' not in line:
            continue
        kind = ('appium_anr' if 'ANR' in line else
                'appium_crash' if re.search(r'crash|fatal|died|killed', line, re.I) else
                'appium_instrumentation' if 'instrument' in line.lower() else 'appium_process')
        exceptions = re.findall(r'\b((?:java\.lang|android(?:\.\w+)*|io\.appium(?:\.\w+)*)\.[A-Za-z]+(?:Exception|Error))\b', line)
        events.append({'time': stamp[1], 'event': kind, 'exception_types': exceptions[:3]})
    return {'source': 'adb logcat: classified allowlisted summary', 'max_lines': LOGCAT_LIMIT,
            'since_device_time': since, 'examined_lines': len(lines), 'events': events[-80:]}


def create_session(factory, *, adb, device, launch_timeout_ms, run=subprocess.run,
                   clock=time.monotonic, attach=allure.attach):
    marker = None
    marker_error = None
    try:
        marker = device_time(adb, device, run)
    except Exception as error:
        marker_error = type(error).__name__
    started = clock()
    outcome = 'interrupted'
    error_type = None
    elapsed = None
    try:
        driver = factory()  # exactly one attempt; never retry a failed test/session
        outcome = 'created'
        return driver
    except Exception as error:
        outcome, error_type = 'failed', type(error).__name__
        elapsed = clock() - started
        try:
            response = run([adb, '-s', device, 'logcat', '-d', '-v', 'threadtime',
                            '-t', str(LOGCAT_LIMIT), *LOGCAT_FILTERS],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=10)
            diagnostic = logcat_summary(response.stdout, marker)
            diagnostic['command_exit'] = response.returncode
        except Exception as diagnostic_error:
            diagnostic = {'diagnostic_error_type': type(diagnostic_error).__name__}
        try:
            attach(json.dumps(diagnostic), name='Mobile: instrumentation logcat (allowlisted)',
                   attachment_type=allure.attachment_type.JSON)
        except Exception:
            pass  # retain the original session failure even if attachment fails
        raise
    finally:
        if elapsed is None:
            elapsed = clock() - started
        timing = {'outcome': outcome, 'session_create_seconds': round(elapsed, 3),
                  'uiautomator2_server_launch_timeout_ms': launch_timeout_ms,
                  'exception_type': error_type, 'device_clock_error_type': marker_error}
        try:
            attach(json.dumps(timing), name='Mobile: session initialization timing',
                   attachment_type=allure.attachment_type.JSON)
        except Exception:
            pass
