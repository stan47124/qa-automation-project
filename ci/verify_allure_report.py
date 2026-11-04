"""Generate reports from copies of two REAL launches; never manufacture test results."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

from allure_history import HistoryStore, read_lines

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(directory):
    return {str(file.relative_to(directory)): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in directory.rglob('*') if file.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first', type=Path, required=True)
    parser.add_argument('--second', type=Path, required=True)
    parser.add_argument('--cli', type=Path, required=True)
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    originals = [fingerprint(source) for source in [args.first, args.second]]
    if not all(originals):
        parser.error('Provide two existing real allure-results directories.')
    report = ROOT / 'artifacts' / ('allure-verification-' + uuid4().hex)
    report.mkdir(parents=True)
    persistent = Path(tempfile.mkdtemp(prefix='qa-allure-history-validation-'))
    store = HistoryStore(persistent, 'offline-validation', 'main')
    store.probe()
    counts = []
    for index, (source, run) in enumerate([(args.first, 'real-first'),
                                          (args.second, 'real-second'),
                                          (args.second, 'real-second')], 1):
        copy = report / f'input-{index}'
        shutil.copytree(source, copy)
        output = report / f'report-{index}'
        result = subprocess.run([
            sys.executable, str(ROOT / 'ci/allure_history.py'), 'generate',
            '--root', str(persistent), '--job', 'offline-validation', '--branch', 'main',
            '--server', 'local', '--run-id', run, '--results', str(copy),
            '--cli', str(args.cli.resolve()), '--output', str(output),
            '--node', args.node,
        ], capture_output=True, env={**os.environ, 'PYTHONUTF8': '1'}, timeout=180)
        (report / f'generation-{index}.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            print(f'Generation {index} failed; inspect local log in {report}.')
            return result.returncode
        _, _, raw = store.current()
        counts.append(len(read_lines(raw)))
        assert (output / 'index.html').is_file()
        charts = json.loads((output / 'widgets/charts.json').read_text(encoding='utf-8'))['general']
        types = {chart['type'] for chart in charts.values()}
        assert len(types) == 9, types
        assert all(chart.get('title') for chart in charts.values())
        status = next(chart['data'] for chart in charts.values() if chart['type'] == 'currentStatus')
        inputs = [json.loads(file.read_text(encoding='utf-8')) for file in copy.glob('*-result.json')]
        assert status['total'] == len(inputs) == 22
        expected_statuses = Counter(record['status'] for record in inputs)
        assert {key: value for key, value in status.items() if key != 'total' and value} == dict(expected_statuses)
        tree = json.loads((output / 'widgets/tree.json').read_text(encoding='utf-8'))
        assert len(tree['root']['groups']) == 3
        assert len(tree['leavesById']) == 22
        if index == 2:
            committed_before_repeat = store.current()
        if index == 3:
            assert store.current() == committed_before_repeat
    assert counts == [1, 2, 2], counts
    assert originals == [fingerprint(source) for source in [args.first, args.second]]
    summary = {'allureVersion': '3.16.0', 'launchesInHistory': counts,
               'testsPerReport': 22, 'featureGroups': 3, 'chartTypes': sorted(types),
               'stabilityRequiresPreviousLaunches': 5,
               'sourceResultsUnchanged': True, 'historyRoot': str(persistent)}
    (report / 'verification.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print('Validation artifacts:', report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
