"""History failure/concurrency tests with explicitly synthetic unit fixtures.

These records are never published as results of the 22 application tests.
"""

import json
import subprocess
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import allure_history as history


@pytest.fixture
def case(tmp_path):
    results = tmp_path / 'workspace' / 'results'
    results.mkdir(parents=True)
    record = {'uuid': 'unit-fixture', 'fullName': 'synthetic.unit.fixture',
              'historyId': 'unit-history-id', 'status': 'passed'}
    (results / 'unit-result.json').write_text(json.dumps(record), encoding='utf-8')
    store = history.HistoryStore(tmp_path / 'persistent', 'job', 'main',
                                 workspace=tmp_path / 'workspace')
    return store, results, record


def generated(store, results, record, run='run-1'):
    transaction = store.prepare(run, [results])
    path = transaction / 'history.jsonl'
    previous = history.read_lines(path.read_bytes())[-(history.LIMIT - 1):]
    previous.append({'uuid': transaction.name, 'knownTestCaseIds': ['unit-case'],
                     'testResults': {'unit-history-id': record}})
    path.write_bytes(b''.join(history.encode(item) + b'\n' for item in previous))
    return transaction


def test_first_run_does_not_require_old_reports(case):
    store, results, record = case
    transaction = generated(store, results, record)
    assert store.commit(transaction)['committed']
    assert len(history.read_lines(store.current()[2])) == 1


def test_repeat_is_idempotent_and_does_not_compare_with_self(case):
    store, results, record = case
    first = generated(store, results, record)
    identity = store.commit(first)['snapshot']
    again = generated(store, results, record)
    assert len(history.read_lines((again / 'history.jsonl').read_bytes())) == 1
    assert store.commit(again) == {'committed': False, 'snapshot': identity}
    assert len(history.read_lines(store.current()[2])) == 1


def test_same_run_changed_results_rejected(case):
    store, results, record = case
    store.commit(generated(store, results, record))
    record['status'] = 'failed'
    (results / 'unit-result.json').write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(history.HistoryError, match='changed results'):
        store.prepare('run-1', [results])


def test_failed_results_are_kept_without_status_changes(case):
    store, results, record = case
    record['status'] = 'failed'
    (results / 'unit-result.json').write_text(json.dumps(record), encoding='utf-8')
    store.commit(generated(store, results, record))
    assert next(iter(history.read_lines(store.current()[2])[0]['testResults'].values()))['status'] == 'failed'


def test_partial_generator_write_preserves_committed_history(case):
    store, results, record = case
    store.commit(generated(store, results, record))
    original = store.current()
    transaction = store.prepare('run-2', [results])
    (transaction / 'history.jsonl').write_bytes(b'{interrupted')
    with pytest.raises(ValueError):
        store.commit(transaction)
    assert store.current() == original


@pytest.mark.parametrize('failure', ['snapshot-write', 'pointer-replace'])
def test_write_failure_and_retry_preserve_previous_snapshot(case, failure):
    store, results, record = case
    store.commit(generated(store, results, record))
    original = store.current()
    transaction = generated(store, results, record, 'run-2')
    target = 'durable_file' if failure == 'snapshot-write' else 'replace_pointer'
    with patch.object(history, target, side_effect=OSError('unit simulated disk failure')):
        with pytest.raises(OSError):
            store.commit(transaction)
    assert store.current() == original
    assert store.commit(transaction)['committed']
    assert len(history.read_lines(store.current()[2])) == 2


def test_changed_inputs_between_generation_and_commit_rejected(case):
    store, results, record = case
    transaction = generated(store, results, record)
    record['status'] = 'broken'
    (results / 'unit-result.json').write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(history.HistoryError, match='changed during'):
        store.commit(transaction)
    assert not (store.directory / 'current.json').exists()


def test_overlapping_publications_do_not_lose_a_run(case):
    store, results, record = case
    first = generated(store, results, record, 'run-1')
    second = generated(store, results, record, 'run-2')
    store.commit(first)
    with pytest.raises(history.HistoryError, match='committed first'):
        store.commit(second)
    store.commit(generated(store, results, record, 'run-2'))
    assert len(history.read_lines(store.current()[2])) == 2


def test_retention_and_dedup_beyond_retention(case):
    store, results, record = case
    for number in range(history.LIMIT + 2):
        store.commit(generated(store, results, record, f'run-{number}'))
    assert len(history.read_lines(store.current()[2])) == history.LIMIT
    assert not store.commit(generated(store, results, record, 'run-0'))['committed']
    assert len(history.read_lines(store.current()[2])) == history.LIMIT


def test_restore_verifies_snapshot_and_backs_up_pointer(case):
    store, results, record = case
    old = store.commit(generated(store, results, record))['snapshot']
    store.commit(generated(store, results, record, 'run-2'))
    assert list((store.directory / 'backups').glob('*.json'))
    (store.directory / 'current.json').write_bytes(b'corrupted-pointer')
    store.restore(old)
    assert store.current()[0] == old
    assert len(history.read_lines(store.current()[2])) == 1


def test_corrupt_snapshot_cannot_be_restored(case):
    store, results, record = case
    identity = store.commit(generated(store, results, record))['snapshot']
    (store.directory / 'snapshots' / identity / 'history.jsonl').write_bytes(b'corrupted')
    with pytest.raises(history.HistoryError, match='integrity'):
        store.restore(identity)


def test_job_branch_and_controller_are_isolated(tmp_path):
    stores = [history.HistoryStore(tmp_path / 'persistent', job, branch, server,
                                   workspace=tmp_path / 'workspace')
              for job, branch, server in [('job', 'main', 'a'), ('job2', 'main', 'a'),
                                          ('job', 'feature/a', 'a'), ('job', 'feature_a', 'a'),
                                          ('job', 'main', 'b')]]
    assert len({store.directory for store in stores}) == len(stores)


def test_workspace_storage_rejected(tmp_path):
    with pytest.raises(history.HistoryError, match='outside'):
        history.HistoryStore(tmp_path / 'workspace' / 'history', 'job', 'main',
                             workspace=tmp_path / 'workspace')


def test_probe_leaves_no_probe_files_and_does_not_create_history(case):
    store, _, _ = case
    store.probe()
    assert not list(store.directory.glob('probe-*'))
    assert store.current()[2] == b''


def test_no_generated_history_cannot_be_committed(case):
    store, results, _ = case
    transaction = store.prepare('run-1', [results])
    with pytest.raises(history.HistoryError, match='exactly one'):
        store.commit(transaction)


def test_generator_may_not_alter_status(case):
    store, results, record = case
    transaction = generated(store, results, {**record, 'status': 'failed'})
    with pytest.raises(history.HistoryError, match='differs from real'):
        store.commit(transaction)


def test_missing_pointer_with_snapshots_does_not_reset_history(case):
    store, results, record = case
    store.commit(generated(store, results, record))
    (store.directory / 'current.json').unlink()
    with pytest.raises(history.HistoryError, match='pointer missing'):
        store.prepare('run-2', [results])


def test_abrupt_process_exit_releases_lock_and_preserves_pointer(case):
    store, results, record = case
    store.commit(generated(store, results, record))
    original = store.current()
    code = ('import sys,os; from pathlib import Path; '
            'sys.path.insert(0,sys.argv[1]); import allure_history as h; '
            'scope=h.commit_lock(Path(sys.argv[2])); scope.__enter__(); os._exit(7)')
    result = subprocess.run([sys.executable, '-c', code, str(Path(history.__file__).parent),
                             str(store.directory)], timeout=20)
    assert result.returncode == 7
    store.probe()
    assert store.current() == original


def test_other_process_cannot_commit_while_pointer_locked(case):
    store, results, record = case
    store.commit(generated(store, results, record))
    code = ('import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
            'import allure_history as h; '\
            '\ntry:\n with h.commit_lock(Path(sys.argv[2])): pass'\
            '\nexcept h.HistoryError: sys.exit(9)')
    with history.commit_lock(store.directory):
        result = subprocess.run([sys.executable, '-c', code, str(Path(history.__file__).parent),
                                 str(store.directory)], timeout=20)
    assert result.returncode == 9


def test_export_has_integrity_and_dedup_manifest(case, tmp_path):
    store, results, record = case
    identity = store.commit(generated(store, results, record))['snapshot']
    destination = tmp_path / 'export'
    store.export(destination)
    manifest = json.loads((destination / 'manifest.json').read_bytes())
    assert manifest['sha256'] == history.digest((destination / 'history.jsonl').read_bytes())
    assert len(manifest['runs']) == 1
    assert json.loads((destination / 'snapshot.json').read_bytes())['snapshot'] == identity
    with pytest.raises(history.HistoryError, match='new output'):
        store.export(destination)


def test_export_failure_does_not_change_committed_history(case, tmp_path):
    store, results, record = case
    store.commit(generated(store, results, record))
    original = store.current()
    with patch.object(history.shutil, 'copyfile', side_effect=OSError('unit disk failure')):
        with pytest.raises(OSError):
            store.export(tmp_path / 'export')
    assert store.current() == original
