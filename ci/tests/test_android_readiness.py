"""Readiness/metrics contract tests. No real ADB, app or device is contacted."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tests/mobile'))
import android_readiness as android
import mobile_session as session
from mobile_config import PACKAGE, APP_ACTIVITY


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def wait(self, seconds):
        self.now += seconds


class Phone:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.boots = ['1']
        self.missing = None
        self.hung = None

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        self.clock.now += 0.01
        if self.hung and self.hung in args:
            self.clock.now += kwargs['timeout']
            raise subprocess.TimeoutExpired('private-command', kwargs['timeout'])
        if args[-1] == 'get-state':
            out = 'device'
        elif 'getprop' in args:
            out = self.boots.pop(0) if len(self.boots)>1 else self.boots[0]
        elif 'service' in args:
            out = f'Service {args[-1]}: '+('not found' if args[-1]==self.missing else 'found')
        elif 'get-current-user' in args:
            out = '0'
        elif 'path' in args:
            out = 'package:/private-user-path/base.apk'
        elif 'resolve-activity' in args:
            out = PACKAGE+'/'+PACKAGE+APP_ACTIVITY
        elif 'wm' in args:
            out = 'Physical size: 1080x2280'
        elif 'dumpsys' in args:
            out = args[-1].upper()+' MANAGER\nprivate-user-payload'
        elif args[-1]=='/proc/meminfo':
            out = 'MemTotal: 2048 kB\nMemAvailable: 1024 kB\nprivate-user-payload'
        elif args[-1]=='/proc/loadavg':
            out = '0.50 0.25 0.10 1/50 1234'
        elif 'date' in args:
            out = '11-05T12:00:00.000'
        else:
            raise AssertionError('Unexpected probe command')
        return SimpleNamespace(returncode=0, stdout=out, stderr='')


def probe(phone, clock, **kwargs):
    return android.probe_android('private-adb-path','emulator-5554',deadline=clock()+10,
                                  package=PACKAGE,activity=APP_ACTIVITY,run=phone,clock=clock,**kwargs)


def test_warm_device_is_ready_on_first_scan_and_raw_data_is_not_retained():
    clock=Clock();phone=Phone(clock)
    result=probe(phone,clock,metrics=True)
    assert result['ready']
    assert all(item['status']=='ok' for item in result['checks'])
    assert result['android_memory']=={'MemTotal_kb':2048,'MemAvailable_kb':1024}
    assert result['android_load']['load_1m']==0.5
    assert 'private-' not in json.dumps(result)
    assert all('start' not in args and 'instrument' not in args for args,_ in phone.calls)


@pytest.mark.parametrize('service',android.SERVICES)
def test_missing_service_is_not_ready(service):
    clock=Clock();phone=Phone(clock);phone.missing=service
    result=probe(phone,clock)
    assert not result['ready']
    assert next(item for item in result['checks'] if item['check']=='service.'+service)['status']=='not_ready'


def test_registered_but_unresponsive_service_is_not_ready():
    clock=Clock();phone=Phone(clock);phone.hung='dumpsys'
    result=probe(phone,clock,command_timeout=2)
    assert not result['ready']
    assert next(item for item in result['checks'] if item['check']=='service.input')['status']=='ok'
    assert next(item for item in result['checks'] if item['check']=='input_response')['status']=='timeout'


def test_one_deadline_caps_all_commands_and_rejects_a_late_result():
    clock=Clock();phone=Phone(clock);phone.hung='service'
    deadline=clock()+0.5
    result=android.probe_android('adb','device',deadline=deadline,package=PACKAGE,
                                 activity=APP_ACTIVITY,run=phone,clock=clock)
    assert not result['ready']
    assert len(phone.calls)==3  # state, boot, first service; no commands after exhaustion
    assert phone.calls[-1][1]['timeout']<=0.5
    assert any(item['status']=='deadline_exhausted' for item in result['checks'])


def test_cold_device_waits_for_boot_condition_not_fixed_warmup():
    clock=Clock();phone=Phone(clock);phone.boots=['0','1'];seen=[]
    result=android.wait_android_ready('adb','device',deadline=clock()+10,package=PACKAGE,
                                      activity=APP_ACTIVITY,run=phone,clock=clock,
                                      wait=clock.wait,observe=seen.append)
    assert result['attempts']==2
    assert not seen[0]['ready'] and seen[1]['ready']
    assert result['elapsed_s']<3


def test_warm_wait_does_not_add_poll_or_delay():
    clock=Clock();phone=Phone(clock);wait=Mock()
    result=android.wait_android_ready('adb','device',deadline=clock()+10,package=PACKAGE,
                                      activity=APP_ACTIVITY,run=phone,clock=clock,wait=wait)
    assert result['attempts']==1
    wait.assert_not_called()


def test_unready_device_has_bounded_wait_and_no_session_factory():
    clock=Clock();phone=Phone(clock);phone.boots=['0']
    with pytest.raises(TimeoutError):
        android.wait_android_ready('adb','device',deadline=clock()+2,package=PACKAGE,
                                    activity=APP_ACTIVITY,run=phone,clock=clock,wait=clock.wait)
    assert clock()<=102.1


@pytest.mark.parametrize('stdout,code,status',[
    ('11-05T12:00:00.000\n',0,'ok'),('02-29T00:00:00.000',0,'ok'),
    ('11-05 12:00:00.000',0,'invalid_format'),('13-05T12:00:00.000',0,'invalid_format'),
    ('11-05T25:00:00.000',0,'invalid_format'),('private-payload',1,'nonzero_exit'),
])
def test_device_time_format_status_and_safe_result(stdout,code,status):
    run=Mock(return_value=SimpleNamespace(returncode=code,stdout=stdout,stderr='private-error'))
    result=session.device_time('private-adb-path','device',run)
    assert result['status']==status
    assert 'private-' not in json.dumps(result)
    # Model ADB's documented joining before POSIX shell tokenization.
    remote=shlex.split(' '.join(run.call_args.args[0][4:]))
    assert remote==['date','+%m-%dT%H:%M:%S.000']
    if status=='ok':
        assert 'T' not in result['marker']


def test_device_time_timeout_is_distinct():
    run=Mock(side_effect=subprocess.TimeoutExpired('private-command',5))
    result=session.device_time('adb','device',run)
    assert result=={'status':'timeout','marker':None,'error_type':'TimeoutExpired'}


def test_failed_marker_is_explicitly_unscoped():
    assert session.logcat_summary('',None)['time_scope']=='unscoped_recent_events'


def test_host_cpu_uses_natural_samples_without_sleep(monkeypatch):
    sampler=android.HostSampler()
    monkeypatch.setattr(sampler,'read',Mock(side_effect=[(10,100,1000,500),(15,120,1000,400)]))
    assert sampler.sample()['cpu_percent_since_previous_sample'] is None
    assert sampler.sample()=={'cpu_percent_since_previous_sample':75.0,'ram_total_bytes':1000,'ram_available_bytes':400}


def test_resource_failure_is_safe_and_not_a_readiness_threshold(monkeypatch):
    sampler=android.HostSampler()
    monkeypatch.setattr(sampler,'read',Mock(side_effect=OSError('private-path')))
    assert sampler.sample()=={'error_type':'OSError'}
    clock=Clock();phone=Phone(clock)
    result=android.wait_android_ready('adb','device',deadline=clock()+10,package=PACKAGE,
                                      activity=APP_ACTIVITY,run=phone,clock=clock,
                                      wait=Mock(),sampler=sampler)
    assert result['ready']


def test_boot_metrics_are_classified_without_retaining_raw_paths(tmp_path):
    log=tmp_path/'emulator.log'
    log.write_text('private-user-path\nFailed to load snapshot\nThe emulator is starting from scratch\nBoot completed in 94804 ms')
    assert android.boot_summary(log)=={'mode':'cold','boot_completed_ms':94804,'snapshot_load_failed':True}
    log.write_text('Successfully loaded snapshot default_boot')
    assert android.boot_summary(log)['mode']=='snapshot'


def test_reused_device_does_not_invent_boot_duration():
    assert android.boot_summary(reused=True)=={'mode':'already_running','boot_completed_ms':None,'snapshot_load_failed':None}


def test_session_probe_is_diagnostic_only_and_original_factory_error_survives(monkeypatch):
    health=Mock(return_value={'ready':False,'diagnostic_only':True})
    monkeypatch.setattr(session,'session_health',health)
    original=RuntimeError('original Appium error')
    factory=Mock(side_effect=original)
    attach=Mock(side_effect=OSError('private-path'))
    with pytest.raises(RuntimeError) as captured:
        session.create_session(factory,adb='adb',device='device',launch_timeout_ms=60000,
            run=Mock(side_effect=OSError('private-command')),clock=Mock(side_effect=[1,2]),attach=attach)
    assert captured.value is original
    factory.assert_called_once_with()
    health.assert_called_once()
