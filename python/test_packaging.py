"""Isolierte Paketprüfung; keine Installation oder Änderung echter Benutzerordner."""
import importlib.util,hashlib,json,os,subprocess,tempfile,zipfile
from pathlib import Path
from unittest.mock import patch
import runtime_paths
ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
build=load('build',ROOT/'packaging/build.py')
life=load('lifecycle',ROOT/'packaging/desktop_lifecycle.py')
with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
 root=Path(folder)
 with patch.object(build,'ROOT',root):
  for invalid in ('','v0.3.0','0.3','1.2.3.4'):
   (root/'VERSION').write_text(invalid)
   try:build.version()
   except ValueError:pass
   else:raise AssertionError('Ungültige Version akzeptiert')
  (root/'VERSION').write_text('0.3.0');assert build.version()=='0.3.0'
  (root/'VERSION').unlink()
  try:build.version()
  except FileNotFoundError:pass
  else:raise AssertionError('Fehlende Version akzeptiert')
 home=root/'home';home.mkdir();config=home/'.config';config.mkdir()
 desktop=home/'Mein Desktop';desktop.mkdir();(config/'user-dirs.dirs').write_text('XDG_DESKTOP_DIR="$HOME/Mein Desktop"\n')
 with patch.dict(os.environ,{},clear=True),patch.object(life.shutil,'which',return_value=None):
  assert life.user_action('configure',home);assert life.user_action('configure',home)
  shortcut=desktop/'docscan.desktop';assert shortcut.exists() and shortcut.stat().st_mode&0o777==0o755
  state=config/'docscan';state.mkdir();(state/'settings.json').write_text('{}')
  assert life.user_action('upgrade',home);assert state.exists()
  assert life.user_action('configure',home);assert state.exists()
  foreign=desktop/'personal.desktop';foreign.write_text('[Desktop Entry]\nName=Personal\nExec=docscan --config-dir /other\n')
  (desktop/'managed.desktop').write_text(life.MANAGED.replace('Exec=docscan','Exec=env LANG=de /usr/bin/docscan'))
  custom=root/'custom';custom.mkdir()
  with patch.object(Path,'home',return_value=home),patch.dict(os.environ,{'XDG_CONFIG_HOME':str(custom)}):
   assert runtime_paths.default_config(Path('/usr/share/docscan'))==custom/'docscan'
   runtime_paths.remember_installed_location(Path('/usr/share/docscan'))
  (custom/'docscan').mkdir();(custom/'docscan/private').write_text('private')
  assert life.user_action('remove',home)
  assert not state.exists() and not (custom/'docscan').exists() and foreign.exists()
  assert not shortcut.exists() and not (desktop/'managed.desktop').exists()
  assert life.user_action('purge',home)
  outside=root/'outside';outside.mkdir();(outside/'keep').write_text('keep')
  state.symlink_to(outside,target_is_directory=True);life.user_action('remove',home)
  assert (outside/'keep').read_text()=='keep'
  stage=root/'stage';build.stage_package(stage)
  for hook,args in [('postinst',['upgrade']),('prerm',['upgrade']),('postrm',['remove'])]:
   subprocess.run(['/usr/bin/python3','-B',str(stage/'DEBIAN'/hook),*args],check=True)
  deb=ROOT/'dist'/f'docscan_{build.version()}_all.deb';unpacked=root/'unpacked'
  subprocess.run(['dpkg-deb','-x',str(deb),str(unpacked)],check=True)
  for name in build.files():assert (unpacked/'usr/share/docscan'/name).read_bytes()==(ROOT/name).read_bytes()
  assert '/usr/share/docscan/python/docscan.py' in (unpacked/'usr/bin/docscan').read_text()
  subprocess.run(['/usr/bin/python3','-B',str(unpacked/'usr/share/docscan/python/docscan.py'),'--version'],check=True)
  for package in (ROOT/'dist').glob('*'):
   if package.suffix=='.sha256':continue
   expected=package.with_name(package.name+'.sha256').read_text().split()[0]
   assert hashlib.sha256(package.read_bytes()).hexdigest()==expected
   if package.suffix=='.zip':
    with zipfile.ZipFile(package) as archive:
     assert archive.testzip() is None
     assert not any('/.config/' in n or n.endswith(('.log','.pyc')) for n in archive.namelist())
print('BESTANDEN: Paketinhalt/Quellvergleich, Prüfsummen, ZIP, Version, Desktop/Neuinstallation, Upgrade-Erhalt, Entfernung/Purge, registrierter XDG-Pfad, fremde Starter und Symlink-Schutz. Paket-Hook-Verteilung simuliert; keine echte Installation.')
