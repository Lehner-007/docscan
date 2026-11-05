"""Schreibbare Einstellungen der installierten Anwendung und Bereinigungsregister."""
import json,os,logging
from pathlib import Path


def default_config(root):
    if root!=Path('/usr/share/docscan'):return root/'.config'
    value=os.environ.get('XDG_CONFIG_HOME','')
    return (Path(value) if value and Path(value).is_absolute() else Path.home()/'.config')/'docscan'


def remember_installed_location(root):
    if root!=Path('/usr/share/docscan'):return
    try:
        registry=Path.home()/'.local/state/docscan-locations.json'
        if any(p.is_symlink() for p in (registry,*registry.parents)):
            raise OSError('Verlinktes Bereinigungsregister')
        locations=set()
        if registry.exists():
            old=json.loads(registry.read_text())
            if not isinstance(old,dict) or old.get('program_id')!='docscan' or not isinstance(old.get('locations'),list):
                raise ValueError('Ungültiges Bereinigungsregister')
            locations.update(v for v in old['locations'] if isinstance(v,str) and Path(v).is_absolute() and Path(v).name=='docscan')
        locations.add(str(default_config(root)))
        registry.parent.mkdir(parents=True,exist_ok=True)
        temporary=registry.with_suffix('.tmp')
        # Exklusives Anlegen vermeidet das Folgen fremder temporärer Symlinks.
        with temporary.open('x') as stream:
            os.chmod(temporary,0o600)
            json.dump({'program_id':'docscan','locations':sorted(locations)},stream)
        os.replace(temporary,registry)
    except (OSError,ValueError):
        logging.warning('Docscan-Speicherort konnte nicht vorgemerkt werden.',exc_info=True)
