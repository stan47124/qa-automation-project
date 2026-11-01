"""Poll SCM orchestration. Job XML and CLI credentials never go to terminal/logs."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
JOB = 'qa-automation-project'
SCHEDULE = 'H/5 * * * *'


class PollingError(RuntimeError):
    pass


class XmlTool:
    def __init__(self, command=None):
        self.command = command or ['java', '-Dstdout.encoding=UTF-8', '-Dstderr.encoding=UTF-8',
                                   str(ROOT / 'ci/JenkinsScmXml.java')]

    def invoke(self, mode, text):
        try:
            result = subprocess.run(self.command + [mode], input=text.encode('utf-8'),
                                    capture_output=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            raise PollingError('Local Java XML processor failed; no raw XML displayed.') from None
        if result.returncode:
            raise PollingError('XML parse/round-trip/settings validation rejected the configuration; no write allowed.')
        return result.stdout.decode('utf-8')

    def inspect(self, text):
        data = json.loads(self.invoke('inspect', text))
        data['schedule'] = base64.b64decode(data.pop('scheduleBase64')).decode('utf-8')
        return data

    def patch(self, text):
        return self.invoke('patch', text)


class JenkinsCli:
    def __init__(self):
        profile = Path(os.environ['USERPROFILE'])
        self.auth = profile / '.jenkins-cli/codex-ci-auth.txt'
        self.jar = Path(tempfile.gettempdir()) / 'jenkins-cli.jar'
        if not self.auth.is_file() or not self.jar.is_file():
            raise PollingError('codex-ci auth file or Jenkins CLI jar is unavailable; no fallback token is used.')
        self.base = ['java', '-Dfile.encoding=UTF-8', '-Dstdout.encoding=UTF-8', '-Dstderr.encoding=UTF-8',
                     '-jar', str(self.jar), '-s', 'http://127.0.0.1:8080/', '-http', '-auth', '@' + str(self.auth)]

    def invoke(self, command, text=None):
        try:
            response = subprocess.run(self.base + list(command), capture_output=True,
                                      input=None if text is None else text.encode('utf-8'), timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            raise PollingError(f'Jenkins CLI {command[0]} transport failure; server state must be checked.') from None
        if response.returncode:
            category = 'authorization/access denied' if re.search(
                rb'AccessDenied|Forbidden|HTTP 403|permission|Unauthorized', response.stderr, re.I) else 'command failed'
            raise PollingError(f'Jenkins CLI {command[0]}: {category}, exit={response.returncode}; raw output withheld.')
        return response.stdout.decode('utf-8')


def read_acl(path):
    # Metadata only: no ACL changes or file contents.
    script = """
$ErrorActionPreference='Stop'
$acl=Get-Acl -LiteralPath $env:JENKINS_POLLING_BACKUP_CHECK
$raw=[Security.AccessControl.RawSecurityDescriptor]::new($acl.GetSecurityDescriptorBinaryForm(),0)
$rules=@($acl.Access | ForEach-Object {
    [pscustomobject]@{sid=$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value;
                    allow=($_.AccessControlType -eq 'Allow')}
})
[pscustomobject]@{current=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
 owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;
 nullDacl=($null -eq $raw.DiscretionaryAcl); rules=$rules} | ConvertTo-Json -Depth 4 -Compress
"""
    env = os.environ.copy()
    env['JENKINS_POLLING_BACKUP_CHECK'] = str(path)
    try:
        result = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, env=env, timeout=20)
        if result.returncode:
            raise ValueError('ACL query failed')
        return json.loads(result.stdout.decode('utf-8-sig'))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise PollingError('Cannot validate backup ACL. Stop; no permissions were changed.') from None


class SecureBackup:
    def __init__(self, directory, repo=ROOT, acl_reader=read_acl):
        self.directory = Path(directory)
        self.repo = Path(repo).resolve()
        self.acl_reader = acl_reader

    def validate(self, path):
        data = self.acl_reader(path)
        if data.get('nullDacl') is not False:
            raise PollingError('Backup has a null or unverifiable DACL; no sensitive data will be written.')
        allowed = {data['current'], 'S-1-5-18', 'S-1-5-32-544'}
        if data['owner'] not in allowed or any(r['allow'] and r['sid'] not in allowed for r in data['rules']):
            raise PollingError('Backup location is not restricted to current user/SYSTEM/Administrators. No ACL changed.')

    def create(self, original):
        directory = self.directory.absolute()
        if not directory.is_dir():
            raise PollingError('Provide an existing restricted backup directory outside the repository.')
        if any(p.is_symlink() or p.is_junction() for p in [directory, *directory.parents]):
            raise PollingError('Backup path must not contain symlinks or junctions.')
        directory = directory.resolve()
        if directory == self.repo or directory.is_relative_to(self.repo):
            raise PollingError('Backup must be outside the Git repository.')
        self.validate(directory)
        path = directory / ('qa-automation-project-before-polling-' + uuid4().hex + '.xml')
        raw = original.encode('utf-8')
        try:
            with path.open('xb') as output:
                self.validate(path)
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(raw).digest():
                raise PollingError('Backup integrity verification failed; no Job update allowed.')
        except OSError:
            raise PollingError('Backup could not be written; no Job update allowed.') from None
        return path


def valid_poll(info):
    return info['pollCount'] == info['canonicalCount'] == 1 and info['schedule'] == SCHEDULE


def configure(cli, xml_tool, backup, verify_only=False):
    identity = cli.invoke(['who-am-i'])
    if not re.search(r'^Authenticated as:\s*codex-ci\s*$', identity, re.M):
        raise PollingError('Expected codex-ci. No write allowed; do not use an administrator token.')
    original = cli.invoke(['get-job', JOB])
    before = xml_tool.inspect(original)
    if verify_only:
        if not valid_poll(before):
            raise PollingError('VerifyOnly: expected one canonical Poll SCM with H/5 * * * *. No settings changed.')
        return {'changed': False, 'verified': True, 'backup': None, 'otherTriggers': before['otherCount']}
    if valid_poll(before):
        return {'changed': False, 'verified': True, 'backup': None, 'otherTriggers': before['otherCount']}
    updated = xml_tool.patch(original)
    planned = xml_tool.inspect(updated)
    if (not valid_poll(planned) or planned['settingsHash'] != before['settingsHash']
            or planned['version'] != before['version'] or planned['otherCount'] != before['otherCount']):
        raise PollingError('Pre-write validation failed. Job is unchanged.')
    backup_path = backup.create(original)
    if cli.invoke(['get-job', JOB]) != original:
        raise PollingError(f'Concurrent Job edit detected; no update sent. Backup: {backup_path}')
    try:
        cli.invoke(['update-job', JOB], updated)
        saved = xml_tool.inspect(cli.invoke(['get-job', JOB]))
        if (not valid_poll(saved) or saved['settingsHash'] != before['settingsHash']
                or saved['version'] != before['version'] or saved['otherCount'] != before['otherCount']
                or saved['pollHash'] != planned['pollHash']):
            raise PollingError('Saved configuration differs from the validated plan.')
    except PollingError as error:
        raise PollingError(f'{error} Server state may have changed; inspect before retry/restore. Backup: {backup_path}') from None
    return {'changed': True, 'verified': True, 'backup': str(backup_path), 'otherTriggers': saved['otherCount']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--backup-directory', type=Path,
                        default=Path(os.environ.get('USERPROFILE', '~')) / '.jenkins-cli')
    args = parser.parse_args()
    try:
        result = configure(JenkinsCli(), XmlTool(), SecureBackup(args.backup_directory), args.verify_only)
    except PollingError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Local polling preparation failed ({type(error).__name__}); raw data withheld. Check state before retry.',
              file=sys.stderr)
        return 2
    print(f'Verified: {JOB} Poll SCM = {SCHEDULE}; one SCM trigger; other settings preserved.')
    print(f'Changed={result["changed"]}; existing other triggers preserved={result["otherTriggers"]}')
    if result['backup']:
        print('Backup: ' + result['backup'])
    print('No build was requested. No Credentials, ACL or global Jenkins changes were requested.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
