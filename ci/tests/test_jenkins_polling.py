"""Offline tests: real JDK XML 1.1 parser, mocked Jenkins and backup ACL metadata."""

from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jenkins_polling as polling

PROPERTY = 'org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty'


def config(poll=None, other='', version='1.1', description='original description'):
    trigger = '' if poll is None else (
        '<hudson.triggers.SCMTrigger><spec>' + poll + '</spec>'
        '<ignorePostCommitHooks>true</ignorePostCommitHooks></hudson.triggers.SCMTrigger>')
    return ('<?xml version="' + version + '" encoding="UTF-8"?>'
            '<flow-definition><description>' + description + '</description><properties>'
            '<hudson.model.ParametersDefinitionProperty><parameterDefinitions><string>'
            '<name>PYTHON_EXE</name><defaultValue>C:\\Python\\python.exe</defaultValue>'
            '<description>Параметр диплома</description></string></parameterDefinitions>'
            '</hudson.model.ParametersDefinitionProperty><' + PROPERTY + '><triggers>' + trigger + other +
            '</triggers></' + PROPERTY + '></properties><definition '
            'class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps@test">'
            '<scm class="hudson.plugins.git.GitSCM"><url>https://github.com/stan47124/qa-automation-project</url>'
            '<credentialsId>synthetic-github-id</credentialsId><branches><name>*/main</name></branches></scm>'
            '<scriptPath>Jenkinsfile</scriptPath><lightweight>true</lightweight></definition>'
            '<disabled>false</disabled><!--keep comment--></flow-definition>')


@pytest.fixture(scope='session')
def xml_tool(tmp_path_factory):
    classes = tmp_path_factory.mktemp('polling-java-classes')
    source = Path(polling.__file__).with_name('JenkinsScmXml.java')
    result = subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(classes), str(source)],
                            capture_output=True, timeout=45)
    assert result.returncode == 0, 'JDK XML helper compilation failed'
    return polling.XmlTool(['java', '-Dstdout.encoding=UTF-8', '-cp', str(classes), 'JenkinsScmXml'])


class FakeCli:
    def __init__(self, text, identity='codex-ci', fail_save=False):
        self.text = text
        self.identity = identity
        self.fail_save = fail_save
        self.calls = []

    def invoke(self, command, text=None):
        self.calls.append(command[0])
        if command[0] == 'who-am-i':
            return 'Authenticated as: ' + self.identity + '\nAuthorities: read, configure\n'
        if command[0] == 'get-job':
            return self.text
        assert command == ['update-job', polling.JOB]
        if self.fail_save:
            raise polling.PollingError('synthetic update failure')
        self.text = text
        return ''


@pytest.fixture
def backup(tmp_path):
    mock = Mock()
    mock.create.return_value = tmp_path / 'restricted-synthetic-backup.xml'
    return mock


@pytest.mark.parametrize('version', ['1.0', '1.1'])
def test_native_xml_version_preserved(xml_tool, version):
    original = config(version=version)
    updated = xml_tool.patch(original)
    assert xml_tool.inspect(updated)['version'] == version
    assert xml_tool.inspect(updated)['settingsHash'] == xml_tool.inspect(original)['settingsHash']
    assert polling.valid_poll(xml_tool.inspect(updated))


def test_source_launcher_used_in_production_handles_xml11():
    assert polling.XmlTool().inspect(config())['version'] == '1.1'


@pytest.mark.parametrize('description', ['line1\u0085line2\u2028line3',
                                          'value&#x1;end', 'value&#x7F;&#x85;&#x2028;end',
                                          '<![CDATA[ a < b & c ]]>'])
def test_xml11_constructs_round_trip_without_xml10_conversion(xml_tool, description):
    original = config(description=description)
    updated = xml_tool.patch(original)
    assert xml_tool.inspect(updated)['version'] == '1.1'
    assert xml_tool.inspect(updated)['settingsHash'] == xml_tool.inspect(original)['settingsHash']


def test_existing_poll_and_idempotent_restart(xml_tool, backup):
    cli = FakeCli(config())
    first = polling.configure(cli, xml_tool, backup)
    second = polling.configure(cli, xml_tool, backup)
    assert first['changed'] and not second['changed']
    assert cli.calls.count('update-job') == 1
    backup.create.assert_called_once_with(config())


@pytest.mark.parametrize('remove_all_properties', [False, True])
def test_missing_trigger_property_or_properties_container(xml_tool, backup, remove_all_properties):
    original = config()
    if remove_all_properties:
        original = re.sub(r'<properties>.*?</properties>', '', original)
    else:
        original = original.replace('<' + PROPERTY + '><triggers></triggers></' + PROPERTY + '>', '')
    cli = FakeCli(original)
    assert polling.configure(cli, xml_tool, backup)['changed']
    assert polling.valid_poll(xml_tool.inspect(cli.text))
    assert xml_tool.inspect(cli.text)['settingsHash'] == xml_tool.inspect(original)['settingsHash']


def test_legacy_poll_is_moved_without_duplicate(xml_tool, backup):
    original = config().replace('<' + PROPERTY + '><triggers></triggers></' + PROPERTY + '>', '')
    original = original.replace('<flow-definition>', '<flow-definition><triggers>'
                                '<hudson.triggers.SCMTrigger><spec>H/20 * * * *</spec>'
                                '</hudson.triggers.SCMTrigger></triggers>')
    cli = FakeCli(original)
    assert polling.configure(cli, xml_tool, backup)['changed']
    assert polling.valid_poll(xml_tool.inspect(cli.text))


def test_existing_correct_poll_has_no_backup_or_update(xml_tool, backup):
    cli = FakeCli(config(polling.SCHEDULE))
    assert not polling.configure(cli, xml_tool, backup)['changed']
    assert 'update-job' not in cli.calls
    backup.create.assert_not_called()


def test_update_schedule_preserves_other_trigger_scm_and_credentials(xml_tool, backup):
    other = '<hudson.triggers.TimerTrigger><spec>H 1 * * *</spec></hudson.triggers.TimerTrigger>'
    original = config('H/30 * * * *', other=other)
    cli = FakeCli(original)
    result = polling.configure(cli, xml_tool, backup)
    assert result['otherTriggers'] == 1
    assert other in cli.text
    assert '<credentialsId>synthetic-github-id</credentialsId>' in cli.text
    assert '<scriptPath>Jenkinsfile</scriptPath>' in cli.text
    assert '<name>*/main</name>' in cli.text
    assert '<ignorePostCommitHooks>true</ignorePostCommitHooks>' in cli.text
    assert 'Параметр диплома' in cli.text
    assert xml_tool.inspect(cli.text)['settingsHash'] == xml_tool.inspect(original)['settingsHash']


def test_verify_only_never_writes_or_creates_backup(xml_tool, backup):
    cli = FakeCli(config(polling.SCHEDULE))
    assert polling.configure(cli, xml_tool, backup, verify_only=True)['verified']
    assert cli.calls == ['who-am-i', 'get-job']
    backup.create.assert_not_called()
    cli = FakeCli(config())
    with pytest.raises(polling.PollingError, match='VerifyOnly'):
        polling.configure(cli, xml_tool, backup, verify_only=True)
    assert 'update-job' not in cli.calls
    backup.create.assert_not_called()


@pytest.mark.parametrize('xml', ['<?xml version="1.1"?><flow-definition>',
                                 config().replace('version="1.1"', 'version="2.0"'),
                                 config().replace('<flow-definition>',
                                     '<!DOCTYPE flow-definition [<!ENTITY test "synthetic">]><flow-definition>')])
def test_malformed_or_dtd_configuration_is_rejected(xml_tool, backup, xml):
    cli = FakeCli(xml)
    with pytest.raises(polling.PollingError, match='XML'):
        polling.configure(cli, xml_tool, backup)
    assert 'update-job' not in cli.calls
    backup.create.assert_not_called()


def test_duplicate_poll_rejected_before_backup(xml_tool, backup):
    cli = FakeCli(config('H/10 * * * *', other='<hudson.triggers.SCMTrigger><spec>H/5 * * * *</spec></hudson.triggers.SCMTrigger>'))
    with pytest.raises(polling.PollingError):
        polling.configure(cli, xml_tool, backup)
    assert 'update-job' not in cli.calls
    backup.create.assert_not_called()


def test_unrelated_prewrite_change_prevents_save(xml_tool, backup):
    bad = Mock(wraps=xml_tool)
    bad.patch.side_effect = lambda text: xml_tool.patch(text).replace('original description', 'unrelated edit')
    cli = FakeCli(config())
    with pytest.raises(polling.PollingError, match='Pre-write'):
        polling.configure(cli, bad, backup)
    backup.create.assert_not_called()
    assert 'update-job' not in cli.calls


def test_admin_identity_is_refused_before_get_job(xml_tool, backup):
    cli = FakeCli(config(), identity='administrator')
    with pytest.raises(polling.PollingError, match='codex-ci'):
        polling.configure(cli, xml_tool, backup)
    assert cli.calls == ['who-am-i']
    backup.create.assert_not_called()


def test_authentication_failure_does_not_write(xml_tool, backup):
    cli = Mock()
    cli.invoke.side_effect = polling.PollingError('authorization/access denied')
    with pytest.raises(polling.PollingError, match='authorization'):
        polling.configure(cli, xml_tool, backup)
    cli.invoke.assert_called_once_with(['who-am-i'])
    backup.create.assert_not_called()


def test_save_failure_reports_backup_and_does_not_rollback(xml_tool, backup):
    cli = FakeCli(config(), fail_save=True)
    with pytest.raises(polling.PollingError, match='Server state may have changed') as error:
        polling.configure(cli, xml_tool, backup)
    assert str(backup.create.return_value) in str(error.value)
    assert cli.calls.count('update-job') == 1
    assert cli.text == config()


def test_bad_readback_is_not_reported_as_success(xml_tool, backup):
    cli = FakeCli(config())
    original = cli.invoke

    def invoke(command, text=None):
        value = original(command, text)
        if command[0] == 'update-job':
            cli.text = cli.text.replace('original description', 'unexpected server edit')
        return value

    cli.invoke = invoke
    with pytest.raises(polling.PollingError, match='Saved configuration differs'):
        polling.configure(cli, xml_tool, backup)


def test_concurrent_edit_prevents_update(xml_tool, backup):
    cli = FakeCli(config())
    original = cli.invoke

    def invoke(command, text=None):
        if command[0] == 'get-job' and cli.calls.count('get-job') == 1:
            cli.text = config(description='concurrent edit')
        return original(command, text)

    cli.invoke = invoke
    with pytest.raises(polling.PollingError, match='Concurrent'):
        polling.configure(cli, xml_tool, backup)
    assert 'update-job' not in cli.calls


def test_saved_poll_options_must_match_the_plan(xml_tool, backup):
    cli = FakeCli(config('H/30 * * * *'))
    original = cli.invoke

    def invoke(command, text=None):
        value = original(command, text)
        if command[0] == 'update-job':
            cli.text = cli.text.replace('<ignorePostCommitHooks>true</ignorePostCommitHooks>',
                                        '<ignorePostCommitHooks>false</ignorePostCommitHooks>')
        return value

    cli.invoke = invoke
    with pytest.raises(polling.PollingError, match='Saved configuration differs'):
        polling.configure(cli, xml_tool, backup)


def safe_acl(path):
    return {'current': 'synthetic-current-user', 'owner': 'synthetic-current-user',
            'nullDacl': False,
            'rules': [{'sid': 'synthetic-current-user', 'allow': True}, {'sid': 'S-1-5-18', 'allow': True}]}


def test_protected_backup_preserves_exact_xml11(tmp_path):
    directory = tmp_path / 'restricted'
    directory.mkdir()
    backup = polling.SecureBackup(directory, repo=tmp_path / 'repo', acl_reader=safe_acl)
    original = config() + '\r\n'
    path = backup.create(original)
    assert path.read_bytes() == original.encode('utf-8')


def test_backup_inside_repository_is_rejected(tmp_path):
    directory = tmp_path / 'repo'
    directory.mkdir()
    with pytest.raises(polling.PollingError, match='outside'):
        polling.SecureBackup(directory, repo=directory, acl_reader=safe_acl).create(config())
    assert list(directory.iterdir()) == []


def test_weak_backup_acl_is_rejected_without_changes(tmp_path):
    def weak(path):
        data = safe_acl(path)
        data['rules'].append({'sid': 'S-1-1-0', 'allow': True})
        return data

    with pytest.raises(polling.PollingError, match='restricted'):
        polling.SecureBackup(tmp_path, repo=tmp_path / 'repo', acl_reader=weak).create(config())
    assert list(tmp_path.iterdir()) == []


def test_file_acl_checked_before_sensitive_data_written(tmp_path):
    def acl(path):
        data = safe_acl(path)
        if path.is_file():
            data['owner'] = 'untrusted-owner'
        return data

    with pytest.raises(polling.PollingError, match='restricted'):
        polling.SecureBackup(tmp_path, repo=tmp_path / 'repo', acl_reader=acl).create(config())
    assert all(path.stat().st_size == 0 for path in tmp_path.iterdir())


def test_null_dacl_backup_is_refused(tmp_path):
    def unsafe(path):
        data = safe_acl(path)
        data['nullDacl'] = True
        data['rules'] = []
        return data

    with pytest.raises(polling.PollingError, match='DACL'):
        polling.SecureBackup(tmp_path, repo=tmp_path / 'repo', acl_reader=unsafe).create(config())
    assert list(tmp_path.iterdir()) == []


def test_backup_failure_prevents_update(xml_tool):
    backup = Mock()
    backup.create.side_effect = polling.PollingError('backup unavailable')
    cli = FakeCli(config())
    with pytest.raises(polling.PollingError, match='backup unavailable'):
        polling.configure(cli, xml_tool, backup)
    assert 'update-job' not in cli.calls


def test_cli_uses_http_and_dedicated_auth_file(tmp_path, monkeypatch):
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    monkeypatch.setattr(polling.tempfile, 'gettempdir', lambda: str(tmp_path))
    (tmp_path / '.jenkins-cli').mkdir()
    (tmp_path / '.jenkins-cli/codex-ci-auth.txt').write_text('synthetic-only')
    (tmp_path / 'jenkins-cli.jar').touch()
    cli = polling.JenkinsCli()
    assert '-http' in cli.base
    assert cli.base[cli.base.index('-auth') + 1] == '@' + str(tmp_path / '.jenkins-cli/codex-ci-auth.txt')
    denied = subprocess.CompletedProcess([], 1, b'', b'HTTP 403 synthetic private output')
    monkeypatch.setattr(polling.subprocess, 'run', Mock(return_value=denied))
    with pytest.raises(polling.PollingError, match='authorization') as error:
        cli.invoke(['who-am-i'])
    assert 'synthetic private output' not in str(error.value)
