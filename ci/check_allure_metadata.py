"""Collect application tests without fixtures; validate metadata and optional real-run IDs."""

import argparse
from collections import Counter
import json
from pathlib import Path

import pytest


CRITICAL = {
    'test_create_pet', 'test_get_pet_by_id', 'test_update_pet', 'test_delete_pet',
    'test_product_details', 'test_add_product_to_cart', 'test_cart_product_and_quantity',
    'test_selected_quantity_is_kept_in_cart', 'test_material_files_main_screen',
    'test_create_folder', 'test_copy_file', 'test_delete_file',
}
NORMAL = {
    'test_find_pets_by_status', 'test_upload_pet_image', 'test_reject_non_numeric_pet_id',
    'test_reject_invalid_status', 'test_home_page', 'test_products_navigation',
    'test_search_for_existing_product', 'test_open_qa_guru_folder', 'test_rename_file',
}
MINOR = {'test_contact_us_file_upload'}
SYSTEMS = {'api': ('API', 'Swagger Petstore v3'),
           'ui': ('Web UI', 'Automation Exercise'), 'mobile': ('Mobile', 'Material Files')}


class MetadataAudit:
    def __init__(self):
        self.results = []
        self.errors = []

    def pytest_collection_finish(self, session):
        # Import after pytest has registered assertion rewriting for its plugins.
        from allure_commons.utils import md5
        from allure_pytest.utils import allure_full_name, allure_labels, get_history_id

        for item in session.items:
            labels = list(allure_labels(item))
            full_name = allure_full_name(item)
            record = {'fullName': full_name, 'testCaseId': md5(full_name),
                      'historyId': get_history_id(full_name, [], {}),
                      'labels': dict(labels)}
            self.results.append(record)
            parent, suite = SYSTEMS[item.path.parent.name]
            expected_severity = ('critical' if item.name in CRITICAL else
                                 'normal' if item.name in NORMAL else 'minor')
            expected = {'epic': 'QA.Guru graduation project', 'feature': f'{parent}: {suite}',
                        'parentSuite': parent, 'suite': suite, 'severity': expected_severity}
            for label, value in expected.items():
                values = [actual for name, actual in labels if name == label]
                if values != [value]:
                    self.errors.append(f'{item.nodeid}: incorrect {label}')
            if not record['labels'].get('story') or hasattr(item, 'callspec'):
                self.errors.append(f'{item.nodeid}: missing story or unexpected parametrization')
        if {item.name for item in session.items} != CRITICAL | NORMAL | MINOR:
            self.errors.append('Expected exactly the 22 known application tests.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, help='Existing real allure-results directory')
    args = parser.parse_args()
    audit = MetadataAudit()
    code = pytest.main(['tests', '--collect-only', '-q'], plugins=[audit])
    if code:
        return int(code)
    severity = Counter(getattr(result['labels']['severity'], 'value', result['labels']['severity'])
                       for result in audit.results)
    if severity != {'critical': 12, 'normal': 9, 'minor': 1}:
        audit.errors.append('Incorrect severity totals.')
    if args.baseline:
        old = {r['fullName']: r for file in args.baseline.glob('*-result.json')
               for r in [json.loads(file.read_text(encoding='utf-8'))]}
        for record in audit.results:
            previous = old.get(record['fullName'], {})
            if any(previous.get(key) != record[key] for key in ['testCaseId', 'historyId']):
                audit.errors.append(f"Changed/missing identity: {record['fullName']}")
        if len(old) != len(audit.results):
            audit.errors.append('Baseline contains a different number of tests.')
        print('Compared identities with the supplied real baseline.')
    print('Severity:', dict(severity))
    print('Metadata errors:', audit.errors)
    return int(bool(audit.errors))


if __name__ == '__main__':
    raise SystemExit(main())
