"""Bounded read-only Android observations. Never start apps/instrumentation here."""
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

SERVICES = ('activity', 'activity_task', 'package', 'window', 'input', 'accessibility')


def safe_error(error):
    name = type(error).__name__
    return name if name in {'TimeoutExpired', 'OSError', 'FileNotFoundError',
                            'PermissionError', 'RuntimeError', 'ValueError'} else 'OtherError'


class HostSampler:
    def __init__(self):
        self.previous = None

    def sample(self):
        try:
            idle, total, memory_total, memory_available = self.read()
            cpu = None
            if self.previous is not None:
                old_idle, old_total = self.previous
                if total > old_total:
                    cpu = round(max(0, min(100, 100 * (1-(idle-old_idle)/(total-old_total)))), 2)
            self.previous = idle, total
            return {'cpu_percent_since_previous_sample': cpu,
                    'ram_total_bytes': memory_total, 'ram_available_bytes': memory_available}
        except Exception as error:
            return {'error_type': safe_error(error)}

    @staticmethod
    def read():
        if os.name == 'nt':
            class FileTime(ctypes.Structure):
                _fields_ = [('low', ctypes.c_uint32), ('high', ctypes.c_uint32)]
                def number(self):
                    return self.low + (self.high << 32)

            class Memory(ctypes.Structure):
                _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
                    (name, ctypes.c_uint64) for name in
                    ['total', 'available', 'page_total', 'page_available',
                     'virtual_total', 'virtual_available', 'extended']]

            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            idle, system, user = FileTime(), FileTime(), FileTime()
            memory = Memory()
            memory.length = ctypes.sizeof(memory)
            if not kernel.GetSystemTimes(ctypes.byref(idle), ctypes.byref(system), ctypes.byref(user)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):
                raise ctypes.WinError(ctypes.get_last_error())
            return idle.number(), system.number()+user.number(), memory.total, memory.available
        counters = [int(value) for value in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
        memory = parse_meminfo(Path('/proc/meminfo').read_text())
        return sum(counters[3:5]), sum(counters[:8]), memory['MemTotal_kb']*1024, memory['MemAvailable_kb']*1024


def parse_meminfo(text):
    return {name+'_kb': int(value) for name, value in
            re.findall(r'^(MemTotal|MemAvailable):\s*(\d+)\s+kB\s*$', text, re.M)}


def parse_load(text):
    values = text.split()
    if len(values) < 3 or not all(re.fullmatch(r'\d+(?:\.\d+)?', value) for value in values[:3]):
        return {}
    return {'load_1m': float(values[0]), 'load_5m': float(values[1]), 'load_15m': float(values[2])}


def boot_summary(path=None, *, reused=False):
    result = {'mode': 'already_running' if reused else 'started_unknown',
              'boot_completed_ms': None, 'snapshot_load_failed': None}
    if reused or path is None:
        return result
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell()-65536))
            text = stream.read(65536).decode('utf-8', errors='replace')
        result['snapshot_load_failed'] = 'Failed to load snapshot' in text
        if 'starting from scratch' in text:
            result['mode'] = 'cold'
        elif re.search(r'(?:Successfully loaded|Loaded) snapshot', text, re.I):
            result['mode'] = 'snapshot'
        duration = re.search(r'Boot completed in (\d+) ms', text)
        if duration:
            result['boot_completed_ms'] = int(duration[1])
    except Exception as error:
        result['error_type'] = safe_error(error)
    return result


def probe_android(adb, device, *, deadline, package, activity, run=subprocess.run,
                  clock=time.monotonic, command_timeout=20, metrics=False):
    started = clock()
    observations = []
    values = {}

    def check(name, args, predicate, *, required=True):
        remaining = deadline-clock()
        entry = {'check': name, 'required': required, 'status': 'deadline_exhausted', 'duration_s': 0}
        observations.append(entry)
        if remaining <= 0:
            return None
        begin = clock()
        try:
            response = run([adb, '-s', device, *args], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=min(command_timeout, remaining))
            if response.returncode:
                entry.update(status='nonzero_exit', exit_code=response.returncode)
                return None
            text = response.stdout[:32768]
            if not predicate(text):
                entry['status'] = 'not_ready'
                return None
            entry['status'] = 'ok'
            return text
        except subprocess.TimeoutExpired:
            entry['status'] = 'timeout'
        except Exception as error:
            entry.update(status='exception', error_type=safe_error(error))
        finally:
            entry['duration_s'] = round(clock()-begin, 3)
            if clock() > deadline:
                entry['status'] = 'deadline_exhausted'
        return None

    state = check('adb_state', ['get-state'], lambda text: text.strip() == 'device')
    if state is not None:
        boot = check('boot_completed', ['shell', 'getprop', 'sys.boot_completed'], lambda text: text.strip() == '1')
        if boot is not None:
            for service in SERVICES:
                check('service.'+service, ['shell', 'service', 'check', service],
                      lambda text, name=service: bool(re.fullmatch(r'Service\s+'+name+r':\s+found\s*', text.strip())))
            user = check('activity_response', ['shell', 'am', 'get-current-user'],
                         lambda text: bool(re.fullmatch(r'\d+', text.strip())))
            check('package_response', ['shell', 'pm', 'path', 'android'],
                  lambda text: any(line.startswith('package:') for line in text.splitlines()))
            check('window_response', ['shell', 'wm', 'size'],
                  lambda text: bool(re.search(r'(?:Physical|Override) size:\s*\d+x\d+', text)))
            check('input_response', ['shell', 'dumpsys', 'input'], lambda text: 'INPUT MANAGER' in text.upper())
            check('accessibility_response', ['shell', 'dumpsys', 'accessibility'],
                  lambda text: 'ACCESSIBILITY MANAGER' in text.upper())
            if user is not None:
                current_user = user.strip()
                check('app_package', ['shell', 'pm', 'path', '--user', current_user, package],
                      lambda text: any(line.startswith('package:') for line in text.splitlines()))
                check('app_launcher', ['shell', 'cmd', 'package', 'resolve-activity', '--brief', '--user',
                                      current_user, '-a', 'android.intent.action.MAIN', '-c',
                                      'android.intent.category.LAUNCHER', '-p', package],
                      lambda text: any(line.strip().startswith(package+'/') for line in text.splitlines()))
                component = package+'/'+activity
                check('app_activity', ['shell', 'cmd', 'package', 'resolve-activity', '--brief',
                                      '--user', current_user, '-n', component],
                      lambda text: any(line.strip() in {component, package+'/'+package+activity}
                                       for line in text.splitlines()))
    # No resource threshold is a readiness condition. No raw dumpsys is retained.
    required = [entry for entry in observations if entry['required']]
    ready = bool(required) and all(entry['status'] == 'ok' for entry in required)
    if metrics:
        memory = check('meminfo', ['shell', 'cat', '/proc/meminfo'],
                       lambda text: 'MemAvailable_kb' in parse_meminfo(text), required=False)
        load = check('loadavg', ['shell', 'cat', '/proc/loadavg'], lambda text: bool(parse_load(text)), required=False)
        values.update(android_memory=parse_meminfo(memory or ''), android_load=parse_load(load or ''))
    return {'ready': ready, 'captured_utc': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
            'elapsed_s': round(clock()-started, 3),
            'checks': observations, **values}


def wait_android_ready(adb, device, *, deadline, package, activity, run=subprocess.run,
                       clock=time.monotonic, wait=None, observe=None, sampler=None):
    wait = wait or threading.Event().wait
    started = clock()
    attempts = 0
    while clock() < deadline:
        attempts += 1
        snapshot = probe_android(adb, device, deadline=deadline, package=package,
                                 activity=activity, run=run, clock=clock)
        snapshot.update(phase='preflight', attempt=attempts)
        if sampler is not None:
            snapshot['host'] = sampler.sample()
        if observe is not None:
            observe(snapshot)
        remaining = deadline-clock()
        if snapshot['ready'] and remaining >= 0:
            return {'ready': True, 'attempts': attempts, 'elapsed_s': round(clock()-started, 3)}
        if remaining <= 0:
            break
        wait(min(1, remaining))
    raise TimeoutError('Android services readiness deadline exceeded; see android-readiness.jsonl')


def safe_attach(attach, document, name, attachment_type):
    try:
        attach(json.dumps(document), name=name, attachment_type=attachment_type)
    except Exception:
        pass
