"""Unit checks for the copy visibility race and read-only failure evidence."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
import selenium.webdriver.support.wait as wait_module

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/mobile'))
from material_files import FilesScreen, resource
from mobile_config import PACKAGE
import copy_diagnostics as diagnostics

WORKSPACE = 'test_' + 'a' * 32
VALID_STATE = 'root_directory\n0|file|38\n1|directory|-\n2|file|38\n'


@pytest.fixture
def screen(monkeypatch):
    # Exercise the real Selenium wait without elapsed wall time or real sleeps.
    ticks = iter(n / 4 for n in range(100))
    monkeypatch.setattr(wait_module, 'time', SimpleNamespace(monotonic=lambda: next(ticks), sleep=Mock()))
    result = FilesScreen(Mock())
    result.wait._timeout = 1
    return result


def test_visibility_is_polled_with_fresh_elements_and_no_extra_displayed_call(screen):
    hidden = Mock()
    hidden.is_displayed.return_value = False
    visible = Mock()
    visible.is_displayed.side_effect = [True, AssertionError('Repeated displayed call outside wait')]
    screen.driver.find_element.side_effect = [hidden, visible]
    locator = resource('nameText')
    assert screen.wait_visible(locator) is True
    assert screen.driver.find_element.call_args_list == [call(*locator), call(*locator)]
    hidden.is_displayed.assert_called_once_with()
    visible.is_displayed.assert_called_once_with()


def test_stale_element_is_discarded_and_current_element_is_found(screen):
    stale = Mock()
    stale.is_displayed.side_effect = StaleElementReferenceException()
    visible = Mock()
    visible.is_displayed.return_value = True
    screen.driver.find_element.side_effect = [stale, visible]
    assert screen.wait_visible(resource('nameText')) is True
    assert screen.driver.find_element.call_count == 2


def test_missing_element_is_awaited_not_treated_as_visible(screen):
    visible = Mock()
    visible.is_displayed.return_value = True
    screen.driver.find_element.side_effect = [NoSuchElementException(), visible]
    assert screen.wait_visible(resource('nameText')) is True
    assert screen.driver.find_element.call_count == 2


def test_permanent_invisibility_raises_timeout(screen):
    screen.driver.find_element.return_value.is_displayed.return_value = False
    with pytest.raises(TimeoutException):
        screen.wait_visible(resource('nameText'))
    assert screen.driver.find_element.call_count > 1


def test_hierarchy_is_filtered_bounded_and_keeps_structure():
    xml = f'''<hierarchy><node package="{PACKAGE}" resource-id="{PACKAGE}:id/recyclerView" bounds="[0,0][1080,2280]">
    <node package="{PACKAGE}" resource-id="{PACKAGE}:id/nameText" text="sample.txt" displayed="true" content-desc="unit-secret"/>
    <node package="{PACKAGE}" resource-id="{PACKAGE}:id/nameText" text="unit-secret"/>
    <node package="other.app" resource-id="{PACKAGE}:id/nameText" text="unit-secret"/>
    <node package="{PACKAGE}" resource-id="{PACKAGE}:id/unknown" text="unit-secret"/>
    </node></hierarchy>'''
    clean = diagnostics.clean_hierarchy(xml, WORKSPACE)
    assert 'unit-secret' not in clean
    tree = ET.fromstring(clean)
    assert tree.find('node/node').get('text') == 'sample.txt'
    assert tree.find('node/node').get('displayed') == 'true'
    assert len(tree.findall('.//node')) == 3
    large = '<hierarchy>' + f'<node package="{PACKAGE}" resource-id="{PACKAGE}:id/nameText"/>' * 100 + '</hierarchy>'
    tree = ET.fromstring(diagnostics.clean_hierarchy(large, WORKSPACE))
    assert len(tree.findall('.//node')) == 80
    assert tree.get('truncated') == 'true'


@pytest.mark.parametrize('source', ['x' * 200001, '<!DOCTYPE x><hierarchy/>', '<broken'])
def test_invalid_or_oversized_hierarchy_is_rejected(source):
    with pytest.raises((ValueError, ET.ParseError)):
        diagnostics.clean_hierarchy(source, WORKSPACE)


@pytest.mark.parametrize('workspace', ['../other', '/sdcard/Download', 'test_not_uuid', '', None])
def test_workspace_outside_owned_scope_is_rejected_before_adb(workspace):
    run = Mock()
    with pytest.raises(ValueError):
        diagnostics.workspace_state(workspace, adb='adb', device='device', run=run)
    run.assert_not_called()


def test_workspace_snapshot_reads_only_expected_paths_and_no_contents():
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=VALID_STATE))
    state = diagnostics.workspace_state(WORKSPACE, adb='adb', device='device', run=run)
    assert state['entries'] == [
        {'name': 'sample.txt', 'state': 'file', 'size_bytes': 38},
        {'name': 'destination', 'state': 'directory', 'size_bytes': None},
        {'name': 'destination/sample.txt', 'state': 'file', 'size_bytes': 38},
    ]
    command = run.call_args.args[0]
    assert command[:4] == ['adb', '-s', 'device', 'shell']
    script = command[4]
    assert f'/sdcard/Download/qa_guru/{WORKSPACE}' in script
    assert 'cat ' not in script and 'find ' not in script and 'rm ' not in script
    assert '[ -L "$root" ]' in script
    assert '[ ! -L "$root/destination" ] && [ -d "$root/destination" ]' in script
    assert run.call_args.kwargs['timeout'] == 5


@pytest.mark.parametrize('output', ['unsafe_root\n', 'missing_root\n',
    'root_directory\n0|symlink|-\n1|symlink|-\n2|unavailable|-\n',
    'root_directory\n0|file|38\n1|directory|-\n2|missing|-\n'])
def test_missing_and_symlink_states_are_explicit_without_contents(output):
    state = diagnostics.workspace_state(WORKSPACE, adb='adb', device='device',
        run=Mock(return_value=SimpleNamespace(returncode=0, stdout=output)))
    assert 'content' not in json.dumps(state)
    assert state['root_state'] in {'unsafe_root', 'missing_root', 'directory'}


@pytest.mark.parametrize('output', ['unit-secret', VALID_STATE.replace('38', 'unit-secret'),
                                  VALID_STATE + 'unit-secret\n', 'x' * 513])
def test_unexpected_adb_output_is_never_attached(output):
    attach = Mock()
    driver = SimpleNamespace(page_source='<hierarchy/>')
    diagnostics.attach_copy_failure(driver, WORKSPACE, adb='adb', device='device', attach=attach,
        run=Mock(return_value=SimpleNamespace(returncode=0, stdout=output)))
    assert len(attach.call_args_list) == 2
    assert all('unit-secret' not in call.args[0] for call in attach.call_args_list)
    assert json.loads(attach.call_args.args[0]) == {'diagnostic_error_type': 'ValueError'}


def test_collectors_are_independent_and_cannot_replace_original_failure():
    class BrokenDriver:
        @property
        def page_source(self):
            raise RuntimeError('unit-secret')
    run = Mock(side_effect=OSError('unit-secret'))
    attach = Mock(side_effect=RuntimeError('unit-secret'))
    original = AssertionError('original copy assertion')
    with pytest.raises(AssertionError) as captured:
        try:
            raise original
        finally:
            diagnostics.attach_copy_failure(BrokenDriver(), WORKSPACE, adb='adb', device='device', run=run, attach=attach)
    assert captured.value is original
    run.assert_called_once()
    assert len(attach.call_args_list) == 2
    assert all('unit-secret' not in call.args[0] for call in attach.call_args_list)


def test_copy_diagnostics_registered_and_executed_before_resource_teardown(tmp_path):
    # A nested, deliberately failing unit fixture exercises real pytest hook /
    # teardown ordering. Its results never enter application reporting/history.
    (tmp_path / 'conftest.py').write_text((ROOT / 'conftest.py').read_text(encoding='utf-8'), encoding='utf-8')
    source = '''
import importlib.util
from pathlib import Path
import sys
import pytest
sys.path.insert(0, MOBILE)
spec = importlib.util.spec_from_file_location('mobile_fixtures', Path(MOBILE) / 'conftest.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
def record(event):
    with Path('events.txt').open('a') as stream:
        stream.write(event + '\\n')
fixtures.attach_copy_failure = lambda *a, **k: record('copy diagnostics')
copy_failure_diagnostics = fixtures.copy_failure_diagnostics
@pytest.fixture
def mobile_workspace():
    yield WORKSPACE
    record('workspace cleanup')
@pytest.fixture
def mobile_driver(request):
    class Driver:
        session_id = 'unit-session'
        def get_screenshot_as_png(self):
            record('screenshot')
            return b''  # screenshot failure must also preserve the assertion
    driver = Driver()
    request.node._qa_drivers = {'Android': driver}
    yield driver
    record('driver quit')
@pytest.mark.usefixtures('copy_failure_diagnostics')
def test_expected_unit_failure():
    raise AssertionError('original copy assertion')
'''
    source = 'MOBILE = ' + repr(str(ROOT / 'tests/mobile')) + '\nWORKSPACE = ' + repr(WORKSPACE) + '\n' + source
    (tmp_path / 'test_lifecycle.py').write_text(source, encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'pytest', 'test_lifecycle.py', '-q',
                             '--confcutdir=.', '--alluredir=results', '--junitxml=junit.xml'],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'original copy assertion' in result.stdout
    assert (tmp_path / 'events.txt').read_text().splitlines() == [
        'copy diagnostics', 'screenshot', 'driver quit', 'workspace cleanup']


def test_successful_collectors_emit_sanitized_xml_and_json():
    attach = Mock()
    driver = SimpleNamespace(page_source=f'<node package="{PACKAGE}" resource-id="{PACKAGE}:id/nameText" text="sample.txt"/>')
    diagnostics.attach_copy_failure(driver, WORKSPACE, adb='adb', device='device', attach=attach,
        run=Mock(return_value=SimpleNamespace(returncode=0, stdout=VALID_STATE)))
    xml, state = attach.call_args_list
    assert ET.fromstring(xml.args[0]).find('node').get('text') == 'sample.txt'
    assert xml.kwargs['attachment_type'].value[1] == 'xml'
    assert json.loads(state.args[0])['entries'][2] == {
        'name': 'destination/sample.txt', 'state': 'file', 'size_bytes': 38}
