"""Transactional Allure 3 history. Never edit a committed JSONL in place.

Allure generates against a disposable copy; an atomic pointer publishes a sealed
snapshot. Old snapshots are recovery points, not input results for the next run.
"""

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 20


class HistoryError(RuntimeError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')


def durable_file(path, raw):
    """Exclusive creation: an existing snapshot/backup is never overwritten."""
    with Path(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def replace_pointer(source, destination):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        move = ctypes.WinDLL('kernel32', use_last_error=True).MoveFileExW
        move.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        move.restype = wintypes.BOOL
        # Same-volume atomic rename, with write-through. Source is already fsynced.
        if not move(str(source), str(destination), 0x1 | 0x8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(source, destination)
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


@contextmanager
def commit_lock(directory):
    """OS lock is released even when its process is killed; no stale lock removal."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'commit.lock').open('a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise HistoryError('History is busy; retry publication later.') from None
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise HistoryError('History is busy; retry publication later.') from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def read_lines(raw):
    records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    if any(not isinstance(item, dict) or not isinstance(item.get('testResults'), dict)
           or not isinstance(item.get('knownTestCaseIds'), list) or not item.get('uuid')
           for item in records):
        raise HistoryError('Invalid history format; restore a verified snapshot.')
    if len({record['uuid'] for record in records}) != len(records):
        raise HistoryError('Duplicate launches in history.')
    return records


def input_records(results):
    records = []
    for directory in results:
        for path in sorted(Path(directory).glob('*-result.json')):
            record = json.loads(path.read_text(encoding='utf-8'))
            records.append(record)
    if not records:
        raise HistoryError('No real Allure test results; no history entry created.')
    identities = [(r.get('historyId'), r.get('fullName')) for r in records]
    if any(not name for _, name in identities):
        # Infrastructure results may lack historyId but still need a stable fullName.
        raise HistoryError('Missing fullName in input results.')
    if len(set(identities)) != len(identities):
        raise HistoryError('Duplicate test identities; do not merge multiple launches.')
    return sorted(records, key=lambda r: (r['fullName'], r.get('uuid', '')))


class HistoryStore:
    def __init__(self, base, job, branch, server='local', workspace=ROOT):
        base = Path(base).absolute()
        if not job or not branch:
            raise HistoryError('Explicit Job and branch are required.')
        # Do not let a junction move persistent state into a disposable workspace.
        if any(p.is_symlink() or p.is_junction() for p in [base, *base.parents]):
            raise HistoryError('History root must not contain links/junctions.')
        base = base.resolve()
        workspace = Path(workspace).resolve()
        if base == workspace or base.is_relative_to(workspace):
            raise HistoryError('History root must be outside the workspace.')
        self.namespace = digest(encode([server, job, branch]))
        self.directory = base / self.namespace

    def snapshot(self, identity):
        if not re.fullmatch(r'[0-9a-f]{32}', identity):
            raise HistoryError('Invalid snapshot ID.')
        path = self.directory / 'snapshots' / identity
        manifest = json.loads((path / 'manifest.json').read_bytes())
        raw = (path / 'history.jsonl').read_bytes()
        if digest(raw) != manifest['sha256'] or manifest['namespace'] != self.namespace:
            raise HistoryError('Snapshot integrity check failed.')
        read_lines(raw)
        return path, manifest, raw

    def current(self):
        pointer = self.directory / 'current.json'
        if not pointer.exists():
            # Existing snapshots with a missing pointer indicate a lost pointer,
            # not a new history. Require an explicit restore to avoid silent reset.
            if list((self.directory / 'snapshots').glob('*/manifest.json')):
                raise HistoryError('History pointer missing; restore a snapshot explicitly.')
            return None, {'runs': {}}, b''
        identity = json.loads(pointer.read_bytes())['snapshot']
        _, manifest, raw = self.snapshot(identity)
        return identity, manifest, raw

    def prepare(self, run_id, results):
        records = input_records(results)
        fingerprint = digest(encode(records))
        run_key = digest(run_id.encode('utf-8'))
        with commit_lock(self.directory):
            parent, manifest, raw = self.current()
            existing = manifest['runs'].get(run_key)
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise HistoryError('Same run ID with changed results; refusing another launch.')
                # Regenerate against the original previous history, not against self.
                raw = self.snapshot(existing['parent'])[2] if existing['parent'] else b''
            transaction = self.directory / 'transactions' / uuid4().hex
            transaction.mkdir(parents=True)
            durable_file(transaction / 'history.jsonl', raw)
            durable_file(transaction / 'transaction.json', encode({
                'namespace': self.namespace, 'parent': parent, 'run': run_key,
                'fingerprint': fingerprint, 'before': digest(raw),
                'results': [str(Path(p).resolve()) for p in results],
            }))
        return transaction

    def publish_pointer(self, identity):
        current = self.directory / 'current.json'
        if current.exists():
            backup = self.directory / 'backups'
            backup.mkdir(exist_ok=True)
            durable_file(backup / (uuid4().hex + '.json'), current.read_bytes())
        temporary = self.directory / ('pointer-' + uuid4().hex + '.tmp')
        durable_file(temporary, encode({'snapshot': identity}))
        replace_pointer(temporary, current)

    def commit(self, transaction):
        transaction = Path(transaction).resolve()
        if transaction.parent != (self.directory / 'transactions').resolve():
            raise HistoryError('Transaction belongs to another history namespace.')
        plan = json.loads((transaction / 'transaction.json').read_bytes())
        if plan['namespace'] != self.namespace:
            raise HistoryError('Transaction namespace mismatch.')
        records = input_records(plan['results'])
        if digest(encode(records)) != plan['fingerprint']:
            raise HistoryError('Results changed during generation; history not committed.')
        generated = (transaction / 'history.jsonl').read_bytes()
        lines = read_lines(generated)
        with commit_lock(self.directory):
            parent, manifest, _ = self.current()
            existing = manifest['runs'].get(plan['run'])
            if existing:
                if existing['fingerprint'] != plan['fingerprint']:
                    raise HistoryError('Conflicting repeat publication.')
                return {'committed': False, 'snapshot': existing['snapshot']}
            if parent != plan['parent']:
                raise HistoryError('Another publication committed first; prepare again.')
            before = self.snapshot(parent)[2] if parent else b''
            if digest(before) != plan['before']:
                raise HistoryError('Previous history changed.')
            # Verify exactly one new entry, including at the retention boundary.
            previous = read_lines(before)[-(LIMIT - 1):]
            if len(lines) != len(previous) + 1 or lines[:-1] != previous:
                raise HistoryError('Generator did not append exactly one launch.')
            expected = Counter((r['fullName'], r['status']) for r in records if r.get('historyId'))
            actual = Counter((r['fullName'], r['status']) for r in lines[-1]['testResults'].values())
            if expected != actual:
                raise HistoryError('Generated history differs from real test results.')
            identity = uuid4().hex
            snapshot = self.directory / 'snapshots' / identity
            snapshot.mkdir(parents=True)
            runs = dict(manifest['runs'])
            runs[plan['run']] = {'fingerprint': plan['fingerprint'],
                                 'parent': parent, 'snapshot': identity}
            durable_file(snapshot / 'history.jsonl', generated)
            durable_file(snapshot / 'manifest.json', encode({
                'namespace': self.namespace, 'sha256': digest(generated), 'runs': runs,
            }))
            self.publish_pointer(identity)
        return {'committed': True, 'snapshot': identity}

    def restore(self, identity):
        with commit_lock(self.directory):
            self.snapshot(identity)  # integrity first; current pointer need not be valid
            self.publish_pointer(identity)

    def export(self, output):
        identity, _, _ = self.current()
        output = Path(output)
        if not identity or output.exists():
            raise HistoryError('Export requires a committed snapshot and a new output directory.')
        source = self.snapshot(identity)[0]
        output.mkdir(parents=True)
        for name in ['history.jsonl', 'manifest.json']:
            shutil.copyfile(source / name, output / name)
        durable_file(output / 'snapshot.json', encode({'snapshot': identity,
                                                      'namespace': self.namespace}))

    def probe(self):
        """Check actual create/fsync/rename rights of the account running this command."""
        with commit_lock(self.directory):
            source = self.directory / ('probe-' + uuid4().hex + '.tmp')
            destination = source.with_suffix('.check')
            try:
                durable_file(source, b'Allure history permission probe\n')
                replace_pointer(source, destination)
                if destination.read_bytes() != b'Allure history permission probe\n':
                    raise HistoryError('Permission probe verification failed.')
            finally:
                source.unlink(missing_ok=True)
                destination.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['default-root', 'probe', 'prepare', 'commit', 'restore', 'export', 'generate'])
    parser.add_argument('--root', default=os.getenv('ALLURE_HISTORY_DIR'), type=Path)
    parser.add_argument('--job', default=os.getenv('JOB_NAME'))
    parser.add_argument('--branch', default=os.getenv('QA_HISTORY_BRANCH') or os.getenv('BRANCH_NAME') or os.getenv('GIT_BRANCH'))
    parser.add_argument('--server', default=os.getenv('JENKINS_URL', 'local'))
    parser.add_argument('--run-id', default=os.getenv('BUILD_TAG'))
    parser.add_argument('--results', nargs='+', type=Path)
    parser.add_argument('--transaction', type=Path)
    parser.add_argument('--snapshot')
    parser.add_argument('--cli', type=Path, help='Allure 3.16.0 JavaScript CLI entry point')
    parser.add_argument('--node', default='node', help='Node.js executable; use the Jenkins tool runtime when available')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT / 'allurerc.mjs')
    args = parser.parse_args()
    if args.action == 'default-root':
        if not os.getenv('LOCALAPPDATA'):
            parser.error('LOCALAPPDATA is unavailable; configure ALLURE_HISTORY_DIR explicitly')
        print(Path(os.environ['LOCALAPPDATA']) / 'QA-Guru' / 'allure-history')
        return 0
    if not args.root:
        parser.error('--root / ALLURE_HISTORY_DIR is required; no implicit storage path')
    try:
        store = HistoryStore(args.root, args.job, args.branch, args.server,
                             workspace=os.getenv('WORKSPACE', str(ROOT)))
        if args.action == 'probe':
            store.probe()
            print('History create/fsync/atomic rename: OK (current account only; ACL unchanged)')
        elif args.action == 'restore':
            store.restore(args.snapshot or '')
            print('Verified history snapshot restored; previous pointer backed up.')
        elif args.action == 'commit':
            print(json.dumps(store.commit(args.transaction)))
        elif args.action == 'export':
            if not args.output:
                parser.error('export requires --output')
            store.export(args.output)
            print('Verified snapshot exported for build archiving.')
        else:
            if not args.run_id or not args.results:
                parser.error('--run-id and --results are required')
            if args.action == 'generate':
                if not args.cli or not args.output:
                    parser.error('generate requires --cli and --output')
                if args.output.exists():
                    raise HistoryError('Output already exists; choose a new report directory.')
                version = subprocess.run([args.node, str(args.cli), '--version'],
                                         capture_output=True, text=True, check=True).stdout.strip()
                if version != '3.16.0':
                    raise HistoryError('Expected Allure CLI 3.16.0.')
            transaction = store.prepare(args.run_id, args.results)
            if args.action == 'prepare':
                print(transaction / 'history.jsonl')
                return 0
            env = os.environ.copy()
            env['ALLURE_HISTORY_PATH'] = str(transaction / 'history.jsonl')
            subprocess.run([args.node, str(args.cli), 'generate', *map(str, args.results),
                            '--config', str(args.config.resolve()), '--output', str(args.output)],
                           env=env, check=True)
            print(json.dumps(store.commit(transaction)))
        return 0
    except (HistoryError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        # Do not print generated logs/JSON/tracebacks that may contain private test data.
        detail = str(error) if isinstance(error, HistoryError) else type(error).__name__
        print(f'History operation failed: {detail}. '
              'Committed snapshots are preserved; see docs/allure-report.md.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
