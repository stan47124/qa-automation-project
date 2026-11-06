"""Shared UI lifecycle and Allure identity checks; no real browser or site."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tests/ui'), str(ROOT / 'ci')]
from check_allure_metadata import compare_identities


def test_fixture_disables_automatic_evidence_and_always_quits(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('ui_fixtures', ROOT/'tests/ui/conftest.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    driver = Mock(capabilities={'browserVersion':'unit', 'chrome':{'chromedriverVersion':'unit','userDataDir':'unit'}})
    monkeypatch.setattr(fixtures.webdriver, 'Chrome', Mock(return_value=driver))
    attach = Mock()
    monkeypatch.setattr(fixtures.allure, 'attach', attach)
    node = SimpleNamespace()
    generator = fixtures.ui_browser.__wrapped__(tmp_path, SimpleNamespace(node=node))
    browser = next(generator)
    assert browser.config.save_screenshot_on_failure is False
    assert browser.config.save_page_source_on_failure is False
    assert browser.config.log_outer_html_on_failure is False
    assert not hasattr(node, '_qa_drivers')
    generator.close()
    driver.quit.assert_called_once_with()
    assert json.loads(attach.call_args.args[0])['closed'] is True



def identities():
    current=[];previous=[]
    for i in range(22):
        web = i>=14
        record={'fullName':f'new-{i}' if web else f'kept-{i}', 'testCaseId':f'case-{i}',
                'historyId':f'history-{i}', 'labels':{'parentSuite':'Web UI' if web else 'API'}}
        current.append(record)
        previous.append({**record, 'fullName':f'old-{i}' if web else record['fullName'],
                         'labels':[{'name':'parentSuite','value':'Web UI' if web else 'API'}]})
    return current,previous



def test_migration_requires_explicit_permission_and_preserves_all_14_ids():
    current,previous=identities()
    assert compare_identities(current,previous)
    assert compare_identities(current,previous,True)==[]
    current[0]['historyId']='changed'
    assert compare_identities(current,previous,True)



def test_migration_rejects_reusing_an_old_ui_identity():
    current,previous=identities()
    current[14]['fullName']=previous[14]['fullName']
    assert compare_identities(current,previous,True)
