"""Sprachpakete, Sicherheitsgrenzen und tatsächlicher GTK-Sprachwechsel."""
import copy,hashlib,json,os,tempfile,time
from pathlib import Path
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
import language_packs as lp
from docscan import App,Window,ROOT
from PIL import Image
BASE=ROOT/'publishing/languages'
catalog=json.loads((BASE/'catalog.json').read_text());assert len(catalog['languages'])==8
reference=json.loads((ROOT/'lang/en.json').read_text());assert set(reference)==set(json.loads((ROOT/'lang/de.json').read_text()))
packs={}
for entry in catalog['languages']:
 path=BASE/(entry['code']+'.json');assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
 data=lp.validate(json.loads(path.read_text()));packs[data['code']]=data
 assert set(data['strings'])==set(reference) and data['help_html'].count('<h2>')==5
 assert 'data:image/svg+xml;base64,' in data['help_html']
 assert 'data:image/png;base64,' in data['help_html']
 assert 'dir="'+('rtl' if data['code']=='ar' else 'ltr')+'"' in data['help_html']
with tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='languages-') as folder:
 config=Path(folder)
 for code,data in packs.items():assert lp.install(config,data)==code
 assert len(lp.installed(config))==10
 for code in packs:
  try:lp.install(config,packs[code])
  except FileExistsError:pass
  else:raise AssertionError('Vorhandene Sprache überschrieben')
 for change in ('identity','traversal','missing','placeholder','script','remote','event','css'):
  bad=copy.deepcopy(packs['fr'])
  if change=='identity':bad['program_id']='other'
  elif change=='traversal':bad['code']='../../other'
  elif change=='missing':bad['strings'].pop('Scan')
  elif change=='placeholder':bad['strings']['Scan']='Scan {unexpected}'
  elif change=='script':bad['help_html']+='<script>alert(1)</script>'
  elif change=='remote':bad['help_html']+='<img src="https://example.com/pixel">'
  elif change=='event':bad['help_html']+='<p onclick="alert(1)">bad</p>'
  elif change=='css':bad['help_html']+='<style>@import "https://example.com";</style>'
  try:lp.validate(bad)
  except ValueError:pass
  else:raise AssertionError('Ungültiges Paket akzeptiert: '+change)
 custom=copy.deepcopy(packs['fr']);custom['code']='it';custom['name']='Lingua di prova'
 assert lp.install(config,custom)=='it'  # Keine Beschränkung auf zehn Standardcodes.
 with patch.object(lp,'github_json',return_value=catalog):assert len(lp.catalog('https://github.com/owner/repo'))==8
 with patch.object(lp,'github_json',side_effect=OSError('offline')):
  try:lp.catalog('https://github.com/owner/repo')
  except OSError:pass
  assert len(lp.installed(config))==11
 for url in ('http://github.com/x','https://example.com/x','https://user:pass@github.com/x','file:///tmp/x'):
  try:lp.github_json(url)
  except ValueError:pass
  else:raise AssertionError('Unzulässige URL akzeptiert')
 with patch.object(Window,'find_devices',return_value=False):
  app=App(config);app.register(None);w=Window(app)
  def pump():
   end=time.monotonic()+.15
   while time.monotonic()<end:
    while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
    time.sleep(.005)
  pump()
  w.pages=[Image.new('RGB',(100,100),'red'),Image.new('RGB',(100,200),'blue')];w.selected=1;w.refresh()
  for code in ('fr','ar','en','zh','de'):
   w.settings['language']=code;w.build();pump()
   assert w.get_direction()==(Gtk.TextDirection.RTL if code=='ar' else Gtk.TextDirection.LTR)
   assert w.t('File')==(packs[code]['strings']['File'] if code in packs else ('Datei' if code=='de' else 'File'))
   assert w.selected==1 and len(w.pages)==2 and w.pages[1].size==(100,200)
   with patch('webbrowser.open') as browser:w.help();assert ('/help/'+code+'/' if code in ('de','en') else '/languages/'+code+'/') in browser.call_args.args[0]
  # Tatsächlichen Einstellungsdialog bedienen: Anwenden und Abbrechen.
  w.preferences();pump();d=next(v for v in Gtk.Window.get_toplevels() if v.get_title()=='Einstellungen')
  def walk(widget):
   yield widget
   child=widget.get_first_child()
   while child:
    yield from walk(child);child=child.get_next_sibling()
  controls=[v for v in walk(d) if isinstance(v,Gtk.DropDown)]
  codes=list(w.language_catalog);controls[0].set_selected(codes.index('ar'))
  next(v for v in walk(d.footer) if isinstance(v,Gtk.Button) and v.get_label()=='Speichern').emit('clicked');pump()
  assert w.settings['language']=='ar' and w.get_direction()==Gtk.TextDirection.RTL and w.selected==1
  w.preferences();pump();d=next(v for v in Gtk.Window.get_toplevels() if v.get_title()==packs['ar']['strings']['Settings'])
  controls=[v for v in walk(d) if isinstance(v,Gtk.DropDown)];controls[0].set_selected(codes.index('de'))
  next(v for v in walk(d.footer) if isinstance(v,Gtk.Button) and v.get_label()==packs['ar']['strings']['Cancel']).emit('clicked');pump()
  assert w.settings['language']=='ar'
  w.store_settings();w.close();pump();w=Window(app);pump();assert w.settings['language']=='ar';w.close();pump()
print('BESTANDEN: 10 Sprachen/Hilfen, vollständige Schlüssel, Sonderzeichen/Prüfsummen, lokaler Import, Eigene Sprache, Überschreibschutz, fehlerhafte Pakete/HTML/Pfade/URLs, Netzfehler, GUI-Wechsel DE/EN/FR/AR/ZH, RTL/LTR, Hilfe, Seitenerhalt, Speichern/Abbrechen/Neustart.')
