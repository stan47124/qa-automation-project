"""Read-only copy failure evidence, restricted to known UI fields and owned paths."""

import json
import re
import shlex
import subprocess
import xml.etree.ElementTree as ET

import allure

from mobile_config import BASE_DIRECTORY, PACKAGE

MAX_SOURCE_CHARS = 200_000
MAX_NODES = 80
KNOWN_IDS = {'toolbar', 'recyclerView', 'itemLayout', 'nameText', 'text',
             'emptyView', 'action_paste'}
ENTRIES = ('sample.txt', 'destination', 'destination/sample.txt')


def validate_workspace(name):
    if not isinstance(name, str) or not re.fullmatch(r'test_[0-9a-f]{32}', name):
        raise ValueError('Expected an owned test workspace name')
    return BASE_DIRECTORY / name


def clean_hierarchy(source, workspace):
    validate_workspace(workspace)
    if len(source) > MAX_SOURCE_CHARS or '<!DOCTYPE' in source.upper() or '<!ENTITY' in source.upper():
        raise ValueError('Hierarchy exceeds limits or contains declarations')
    original = ET.fromstring(source)
    cleaned = ET.Element('hierarchy', sanitized='true')
    pending = [(original, cleaned)]
    kept = 0
    while pending:
        node, parent = pending.pop()
        identifier = node.get('resource-id', '')
        if node.get('package') == PACKAGE and identifier in {f'{PACKAGE}:id/{name}' for name in KNOWN_IDS}:
            if kept == MAX_NODES:
                cleaned.set('truncated', 'true')
                break
            attributes = {'resource-id': identifier}
            for key in ('displayed', 'visible-to-user', 'enabled', 'scrollable'):
                if node.get(key) in {'true', 'false'}:
                    attributes[key] = node.get(key)
            bounds = node.get('bounds', '')
            if re.fullmatch(r'\[\d{1,5},\d{1,5}\]\[\d{1,5},\d{1,5}\]', bounds):
                attributes['bounds'] = bounds
            text = node.get('text', '')
            if text:
                attributes['text'] = text if text in {'sample.txt', 'destination', workspace} else '[omitted]'
            parent = ET.SubElement(parent, 'node', attributes)
            kept += 1
        pending.extend((child, parent) for child in reversed(list(node)))
    return ET.tostring(cleaned, encoding='unicode')


def workspace_state(workspace, *, adb, device, run=subprocess.run):
    root = validate_workspace(workspace)
    # Never enumerate other directories or follow a link out of the owned tree.
    # Only fixed names and numeric sizes are returned, never file contents.
    script = f'''root={shlex.quote(str(root))}
if [ -L "$root" ]; then printf 'unsafe_root\\n'; exit 0; fi
if [ ! -d "$root" ]; then printf 'missing_root\\n'; exit 0; fi
printf 'root_directory\\n'
probe() {{
  if [ -L "$1" ]; then printf '%s|symlink|-\\n' "$2"
  elif [ -f "$1" ]; then
    size=$(stat -c %s -- "$1") || exit 1
    printf '%s|file|%s\\n' "$2" "$size"
  elif [ -d "$1" ]; then printf '%s|directory|-\\n' "$2"
  else printf '%s|missing|-\\n' "$2"; fi
}}
probe "$root/sample.txt" 0
probe "$root/destination" 1
if [ ! -L "$root/destination" ] && [ -d "$root/destination" ]; then
  probe "$root/destination/sample.txt" 2
else printf '2|unavailable|-\\n'; fi
'''
    response = run([adb, '-s', device, 'shell', script], capture_output=True,
                   text=True, encoding='utf-8', errors='replace', timeout=5)
    if response.returncode != 0 or len(response.stdout) > 512:
        raise ValueError('Workspace diagnostic unavailable')
    lines = response.stdout.splitlines()
    result = {'workspace': workspace, 'scope': 'fixed expected entries only', 'entries': []}
    if lines in (['unsafe_root'], ['missing_root']):
        result['root_state'] = lines[0]
        return result
    if len(lines) != 4 or lines[0] != 'root_directory':
        raise ValueError('Invalid workspace diagnostic response')
    result['root_state'] = 'directory'
    for index, (name, line) in enumerate(zip(ENTRIES, lines[1:])):
        match = re.fullmatch(rf'{index}\|(file|directory|symlink|missing|unavailable)\|(-|[0-9]{{1,19}})', line)
        if not match or (match[1] == 'file') != (match[2] != '-'):
            raise ValueError('Invalid workspace entry response')
        result['entries'].append({'name': name, 'state': match[1],
                                  'size_bytes': int(match[2]) if match[1] == 'file' else None})
    return result


def attach_copy_failure(driver, workspace, *, adb, device, run=subprocess.run, attach=allure.attach):
    collectors = [
        ('Mobile: copy UI hierarchy (sanitized)', allure.attachment_type.XML,
         lambda: clean_hierarchy(driver.page_source, workspace)),
        ('Mobile: copy workspace state', allure.attachment_type.JSON,
         lambda: json.dumps(workspace_state(workspace, adb=adb, device=device, run=run))),
    ]
    for name, kind, collect in collectors:
        try:
            body = collect()
        except Exception as error:
            body = json.dumps({'diagnostic_error_type': type(error).__name__})
            kind = allure.attachment_type.JSON
        try:
            attach(body, name=name, attachment_type=kind)
        except Exception:
            pass  # evidence collection must never replace the original failure
