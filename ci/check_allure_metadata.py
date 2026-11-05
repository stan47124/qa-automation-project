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


UI_CASES = {
    'test_home_page': 'Home page',
    'test_products_navigation': 'Products navigation',
    'test_product_details': 'Product details',
    'test_add_product_to_cart': 'Add to cart',
    'test_cart_product_and_quantity': 'Cart contents',
    'test_selected_quantity_is_kept_in_cart': 'Select product quantity',
    'test_search_for_existing_product': 'Product search',
    'test_contact_us_file_upload': 'Attach TXT without submission',
}


def compare_identities(current, previous, allow_web_replacement=False):
    errors = []
    old = {r['fullName']: r for r in previous}
    new = {r['fullName']: r for r in current}
    if len(old) != 22 or len(new) != 22:
        errors.append('Identity comparison requires exactly 22 distinct records per launch.')
    if allow_web_replacement:
        unchanged = [r for r in current if r['labels'].get('parentSuite') != 'Web UI']
        old_web = {r['fullName'] for r in previous if dict((v['name'],v['value']) for v in r.get('labels',[])).get('parentSuite') == 'Web UI'}
        new_web = {r['fullName'] for r in current if r['labels'].get('parentSuite') == 'Web UI'}
        if len(unchanged) != 14 or len(old_web) != 8 or len(new_web) != 8 or old_web & new_web:
            errors.append('Migration must replace exactly 8 Web UI identities and preserve 14 others.')
        compared = unchanged
    else:
        compared = current
        if set(old) != set(new):
            errors.append('Changed test set; use migration mode only for the approved replacement.')
    for record in compared:
        before = old.get(record['fullName'], {})
        if any(before.get(key) != record[key] for key in ['testCaseId', 'historyId']):
            errors.append('Changed/missing identity: ' + record['fullName'])
    return errors


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
            if item.name in UI_CASES:
                expected['story'] = UI_CASES[item.name]
            for label, value in expected.items():
                values = [actual for name, actual in labels if name == label]
                if values != [value]:
                    self.errors.append(f'{item.nodeid}: incorrect {label}')
            if not record['labels'].get('story') or hasattr(item, 'callspec'):
                self.errors.append(f'{item.nodeid}: missing story or unexpected parametrization')
        if len(session.items) != 22 or {item.name for item in session.items} != CRITICAL | NORMAL | MINOR:
            self.errors.append('Expected exactly the 22 known application tests.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, help='Existing real allure-results directory')
    parser.add_argument('--allow-web-replacement', action='store_true', help='One-time comparison against the old 8 UI identities; all 14 others must match.')
    parser.add_argument('--output', type=Path, help='New metadata JSON outside Allure history')
    args = parser.parse_args()
    if args.allow_web_replacement and not args.baseline:
        parser.error('--allow-web-replacement requires a real baseline')
    audit = MetadataAudit()
    code = pytest.main(['tests', '--collect-only', '-q'], plugins=[audit])
    if code:
        return int(code)
    severity = Counter(getattr(result['labels']['severity'], 'value', result['labels']['severity'])
                       for result in audit.results)
    if severity != {'critical': 12, 'normal': 9, 'minor': 1}:
        audit.errors.append('Incorrect severity totals.')
    if args.baseline:
        previous = [json.loads(file.read_text(encoding='utf-8')) for file in args.baseline.glob('*-result.json')]
        audit.errors.extend(compare_identities(audit.results, previous, args.allow_web_replacement))
        print('Compared identities with the supplied real baseline.')
    if args.output:
        if args.output.exists():
            parser.error('Metadata output already exists')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(audit.results, indent=2), encoding='utf-8')
    print('Severity:', dict(severity))
    print('Metadata errors:', audit.errors)
    return int(bool(audit.errors))


if __name__ == '__main__':
    raise SystemExit(main())
