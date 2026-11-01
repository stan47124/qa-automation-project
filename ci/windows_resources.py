"""Own child process trees without PID-based cleanup or administrator privileges."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ('ProcessTime', ctypes.c_int64), ('JobTime', ctypes.c_int64),
        ('LimitFlags', wintypes.DWORD), ('MinWorkingSet', ctypes.c_size_t),
        ('MaxWorkingSet', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
        ('Affinity', ctypes.c_size_t), ('Priority', wintypes.DWORD),
        ('SchedulingClass', wintypes.DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('Basic', BasicLimits), ('Io', IoCounters)] + [
        (name, ctypes.c_size_t) for name in
        ('ProcessMemory', 'JobMemory', 'PeakProcessMemory', 'PeakJobMemory')
    ]


def kernel():
    dll = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        'CreateMutexW': ([ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        'ReleaseMutex': ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        getattr(dll, name).argtypes = args
        getattr(dll, name).restype = result
    return dll


class DeviceLock:
    """One cooperating runner per device across workspaces and logon sessions."""

    def __enter__(self):
        self.dll = kernel()
        self.handle = self.dll.CreateMutexW(None, False, 'Global\\QAGuru-emulator-5554')
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        result = self.dll.WaitForSingleObject(self.handle, 0)
        if result not in (0, 0x80):  # acquired, or acquired an abandoned mutex
            self.dll.CloseHandle(self.handle)
            raise RuntimeError('Mobile device is busy or its lock is inaccessible; no tests started.')
        return self

    def __exit__(self, *args):
        self.dll.ReleaseMutex(self.handle)
        self.dll.CloseHandle(self.handle)


class OwnedProcesses:
    """Kill-on-close Job Object; never adopts an existing Appium or emulator."""

    def __enter__(self):
        self.dll = kernel()
        self.handle = self.dll.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.children = []
        limits = ExtendedLimits()
        limits.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.dll.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            self.dll.CloseHandle(self.handle)
            raise ctypes.WinError(error)
        return self

    def start(self, command, output, env):
        # The gate cannot spawn the real command until it belongs to this job.
        gate = Path(__file__).with_name('mobile_ci.py')
        process = subprocess.Popen(
            [sys.executable, str(gate), '_child', *map(str, command)],
            stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT,
            env=env, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            if not self.dll.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process._handle))):
                raise ctypes.WinError(ctypes.get_last_error())
            self.children.append(process)
            process.stdin.write(b'go\n')
            process.stdin.close()
            return process
        except BaseException:
            process.stdin.close()
            process.terminate()
            process.wait(timeout=10)
            raise

    def __exit__(self, *args):
        # Also happens when Windows closes our handle after termination/abort.
        self.dll.CloseHandle(self.handle)
        for process in self.children:
            process.wait(timeout=10)
