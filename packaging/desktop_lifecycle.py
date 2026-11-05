#!/usr/bin/python3
"""Manage Docscan desktop entries and private runtime data, as their owner."""
import os
import json
import re
import configparser
import shlex
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

DESKTOP = '[Desktop Entry]\nType=Application\nName=Docscan\nGenericName=Document scanner\nGenericName[de]=Dokument-Scanner\nComment=Scan documents and save PDF files\nComment[de]=Dokument-Scanner erfassen\nExec=docscan\nIcon=/usr/share/docscan/assets/docscan.svg\nTerminal=false\nCategories=Graphics;Scanning;\nKeywords=Scanner;SANE;PDF;\nStartupNotify=true\n'
MANAGED = DESKTOP + 'X-Docscan-Managed=true\n'


def desktop_dir(home):
    value = os.environ.get('XDG_CONFIG_HOME', '')
    config = (Path(value) if value and Path(value).is_absolute() else home / '.config') / 'user-dirs.dirs'
    try:
        for line in config.read_text().splitlines():
            if line.startswith('XDG_DESKTOP_DIR='):
                value = line.split('=', 1)[1].strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
                    if value == '$HOME':
                        return None  # Disabled desktop directory.
                    value = value.replace('${HOME}', str(home)).replace('$HOME', str(home))
                    target = Path(value)
                    if target.is_absolute() and target != home and target.is_dir():
                        return target
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError) as exc:
        print('Docscan: Desktop-Einstellung nicht lesbar:', config, exc, file=sys.stderr)
        return None
    return next((home / n for n in ('Schreibtisch', 'Desktop') if (home / n).is_dir()), None)


def is_shortcut(path):
    if path.is_symlink():
        try:
            return os.readlink(path) == '/usr/share/applications/docscan.desktop'
        except OSError as exc:
            print('Docscan: Starter nicht lesbar:', path, exc, file=sys.stderr)
            return False
    if not path.is_file():
        return False
    try:
        cfg = configparser.ConfigParser(interpolation=None, strict=False)
        cfg.read_string(path.read_text())
        command = shlex.split(cfg.get('Desktop Entry', 'Exec', fallback=''))
        if command and command[0] in ('env', '/usr/bin/env'):
            command = command[1:]
            while command and (command[0] == '--' or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', command[0])):
                command = command[1:]
        if not command or command[0] not in ('docscan', '/usr/bin/docscan'):
            return False
        if cfg.get('Desktop Entry', 'X-Docscan-Managed', fallback='').lower() == 'true':
            return True
        # Only the exact old package template is migrated. Personal launchers
        # with other arguments, names, icons or options remain untouched.
        expected = configparser.ConfigParser(interpolation=None)
        expected.read_string(DESKTOP)
        return dict(cfg['Desktop Entry']) == dict(expected['Desktop Entry'])
    except (OSError, UnicodeError, ValueError, configparser.Error) as exc:
        print('Docscan: Starter bleibt erhalten, nicht sicher lesbar:', path, exc, file=sys.stderr)
        return False


def safe_parents(path,include_self=False):
    path=Path(os.path.abspath(path))
    candidates=[path,*path.parents] if include_self else path.parents
    if any(parent.is_symlink() for parent in candidates):
        print('Docscan: verlinkter Speicherort bleibt erhalten:',path,file=sys.stderr)
        return False
    return True


def remove_tree(path):
    # Never follow a directory symlink into unrelated user files.
    if not safe_parents(path):
        return
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def user_action(action, home):
    failures = []
    def attempt(path, operation):
        try:
            operation()
            return True
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            failures.append(str(path))
            print('Docscan: nicht bearbeitet:', path, exc, file=sys.stderr)
            return False
    attempt(home, lambda: _user_action(action, home, attempt))
    print('Docscan:', action, 'für', home, 'abgeschlossen;' if not failures else 'unvollständig;',
          'Standardpfade und vorgemerkte XDG-Pfade geprüft. Verlinkte Eltern bleiben erhalten.', file=sys.stderr)
    return not failures


def _user_action(action, home, attempt):
    desktop = desktop_dir(home)
    if action == 'configure':
        if desktop is None:
            return
        target = desktop / 'docscan.desktop'
        if (target.exists() or target.is_symlink()) and not is_shortcut(target):
            print('Docscan: eigene Desktop-Datei bleibt erhalten:', target, file=sys.stderr)
            return
        if target.is_symlink():
            target.unlink()
        # Run as user, never as root; no privilege escalation via user paths.
        if not safe_parents(target):return
        target.write_text(MANAGED)
        target.chmod(0o755)
        if shutil.which('gio'):
            subprocess.run(['gio', 'set', str(target), 'metadata::trusted', 'true'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return
    if action not in ('remove', 'purge'):
        return
    for folder in filter(None, [desktop, home / '.local/share/applications', home / '.config/autostart']):
        if safe_parents(folder,include_self=True) and folder.is_dir():
            for target in folder.glob('*.desktop'):
                if is_shortcut(target):
                    attempt(target, target.unlink)
    trash = home / '.local/share/Trash'
    if safe_parents(trash / 'files',include_self=True) and (trash / 'files').is_dir():
        for target in (trash / 'files').glob('*.desktop'):
            if is_shortcut(target):
                attempt(target, target.unlink)
                info=trash / 'info' / (target.name + '.trashinfo')
                if safe_parents(info):attempt(info, lambda: info.unlink(missing_ok=True))
    # App-owned XDG directories only; never the development project or arbitrary reports.
    locations = [home / '.config', home / '.cache', home / '.local/share', home / '.local/state']
    for var in ('XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME'):
        value = os.environ.get(var)
        if value and Path(value).is_absolute():
            locations.append(Path(value))
    targets = {base / 'docscan' for base in locations}
    registry = home / '.local/state/docscan-locations.json'
    registry_ok = safe_parents(registry) and not registry.is_symlink()
    if safe_parents(registry) and registry.exists() and not registry.is_symlink():
        def registered():
            data = json.loads(registry.read_text())
            if not isinstance(data, dict) or data.get('program_id') != 'docscan' or not isinstance(data.get('locations'), list):
                raise ValueError('Ungültiges Speicherortverzeichnis')
            for value in data['locations']:
                if not isinstance(value, str) or not Path(value).is_absolute() or Path(value).name != 'docscan':
                    raise ValueError('Ungültiger Speicherort')
                targets.add(Path(value))
        registry_ok = attempt(registry, registered)
    for target in sorted(targets):
        attempt(target, lambda: remove_tree(target))
    # Keep the registry for a later retry/purge if a target was protected or failed.
    if registry_ok and all(not target.exists() and not target.is_symlink() for target in targets):
        attempt(registry, lambda: registry.unlink(missing_ok=True))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--user':
        if os.geteuid() == 0:
            raise SystemExit('Benutzerbereinigung darf nicht als root laufen.')
        if sys.argv[2] not in ('configure', 'remove', 'purge'):
            raise SystemExit('Aktion: configure, remove oder purge')
        success = user_action(sys.argv[2], Path(pwd.getpwuid(os.geteuid()).pw_dir))
        raise SystemExit(0 if success else 1)
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action not in ('configure', 'remove', 'purge'):
        return  # No deletion on upgrade, failed upgrade, or deconfigure.
    if os.geteuid() != 0:
        raise SystemExit('Paketverwaltung benötigt root.')
    failed = []
    skipped = []
    for user in pwd.getpwall():
        if not 1000 <= user.pw_uid < 65534 or user.pw_shell.endswith(('/nologin', '/false')):
            skipped.append(user.pw_name)
            continue
        if not Path(user.pw_dir).is_dir():
            print('Docscan: Benutzerordner nicht erreichbar:',user.pw_name,file=sys.stderr)
            continue
        # Root-XDG-Pfade gehören nicht zum Zielbenutzer.
        environment=os.environ.copy()
        for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME'):
            environment.pop(key,None)
        try:
            result = subprocess.run(['/usr/sbin/runuser', '-u', user.pw_name, '--',
                                     '/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--user', action],
                                    env=environment, timeout=120)
            if result.returncode:
                failed.append(user.pw_name)
        except (OSError, subprocess.SubprocessError) as exc:
            failed.append(user.pw_name)
            print('Docscan: Benutzerwechsel fehlgeschlagen:', user.pw_name, exc, file=sys.stderr)
    if failed:
        print('Docscan-Benutzerdateien nicht vollständig bearbeitet: ' + ', '.join(failed), file=sys.stderr)
    if skipped:
        print('Docscan: ausgelassene Konten (root/System/deaktiviert): ' + ', '.join(skipped), file=sys.stderr)
    # Optional user maintenance must not leave dpkg half-configured/removed.


if __name__ == '__main__':
    main()
