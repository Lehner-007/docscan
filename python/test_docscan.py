"""SANE-Testbackend und GTK verwenden ausschließlich projektinterne Testdateien."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os,threading,time,json
from unittest.mock import patch
from PIL import Image
import scanner,document
from docscan import App,Window,ROOT
from gi.repository import GLib,Gtk

env=dict(os.environ,SANE_CONFIG_DIR=str(ROOT/'tests/sane'))
cancel=threading.Event()
devices=scanner.discover(cancel,env);assert devices[0][0]=='test:0'
opts=scanner.options('test:0',cancel,env);assert 'Color' in opts['modes'];assert opts['resolution']
with TemporaryDirectory(prefix='run-',dir=ROOT/'tests') as temp:
    temp=Path(temp)
    pages,aborted=scanner.scan('test:0','Color','',50,1,temp,cancel,lambda n,t:None,env)
    assert len(pages)==1 and not aborted and pages[0].width>0
    batch=temp/'batch';batch.mkdir()
    multiple,aborted=scanner.scan('test:0','Gray','Automatic Document Feeder',25,12,batch,cancel,lambda n,t:None,env)
    assert len(multiple)==10 and not aborted  # SANE NO_DOCS ist ein reguläres Einzugsende.
    entire=temp/'entire';entire.mkdir()
    all_pages,aborted=scanner.scan('test:0','Gray','Automatic Document Feeder',25,None,entire,cancel,lambda n,t:None,env)
    assert len(all_pages)==10 and not aborted
    cancel.set();assert scanner.scan('test:0','Color','',50,1,temp,cancel,lambda n,t:None,env)==([],True);cancel.clear()
    with patch('scanner.shutil.which',return_value=None):
        try:scanner.discover(cancel)
        except scanner.ScanError as exc:assert str(exc)=='scanimage_missing'
        else:raise AssertionError('Fehlendes scanimage nicht erkannt')
    # Teilbilder messen echte, vollständige Zeilen; binäre Leerzeichen bleiben Pixel.
    partial=temp/'partial.pnm'
    partial.write_bytes(b'P6\n# Test\n4 10\n255\n'+bytes([32,10,0])*4*3)
    state=scanner.pnm_state(partial);assert state[-1]==3
    live=scanner.pnm_preview(partial,state)
    assert live.getpixel((0,0))==(32,10,0) and live.getpixel((0,4))==(255,255,255)
    partial.write_bytes(b'P4\n8 2\n'+b'\xff')
    state=scanner.pnm_state(partial);assert state[-1]==1
    assert scanner.pnm_preview(partial,state).getpixel((0,0))==(0,0,0)
    partial.write_bytes(b'P5\n2 2\n65535\n'+b'\xff\xff\x00\x00')
    state=scanner.pnm_state(partial);assert state[-1]==1
    assert scanner.pnm_preview(partial,state).getpixel((0,0))==(255,255,255)
    # Echter SANE-Datenfluss mit künstlicher Leselatenz, nur im Testprozess.
    slow=temp/'slow';slow.mkdir();(slow/'dll.conf').write_text('test\n')
    conf=Path('/etc/sane.d/test.conf').read_text().replace('read-limit false','read-limit true').replace('read-limit-size 1\n','read-limit-size 4096\n').replace('read-delay false','read-delay true').replace('read-delay-duration 1000\n','read-delay-duration 200000\n')
    (slow/'test.conf').write_text(conf);output=temp/'slow-output';output.mkdir()
    events=[];counts=[]
    result,aborted=scanner.scan('test:0','Color','',200,1,output,cancel,
        lambda n,t:counts.append(n),dict(env,SANE_CONFIG_DIR=str(slow)),
        preview=lambda im,f,p,t:events.append((im,f,p,t)))
    assert len(result)==1 and not aborted and any(0<f<1 for im,f,p,t in events)
    assert events[-1][1]==1 and counts[0]==0 and counts[-1]==1
    assert any(im.getpixel((0,im.height-1))==(255,255,255) for im,f,p,t in events if f<1)
    a=Image.new('RGB',(200,100),'red');b=Image.new('RGB',(100,200),'blue')
    document.save_session([a,b],temp/'session');restored=document.restore(temp/'session');assert [x.size for x in restored]==[a.size,b.size]
    document.export([a,b],temp/'scan.pdf','PDF');assert (temp/'scan.pdf').read_bytes().startswith(b'%PDF')
    document.export([a],temp/'scan.png','PNG');assert document.load_images(temp/'scan.png')[0].size==a.size
    try:document.export([b],temp/'scan.png','PNG')
    except FileExistsError:pass
    else:raise AssertionError('Vorhandenes Exportziel überschrieben')
    assert document.load_images(temp/'scan.png')[0].size==a.size
    with patch.object(Window,'find_devices',return_value=False):
        app=App(temp/'config');app.register(None);w=Window(app)
        def pump():
            until=time.monotonic()+.2
            while time.monotonic()<until:
                while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
                time.sleep(.005)
        def wait():
            end=time.monotonic()+10
            while w.busy and time.monotonic()<end:pump()
            assert not w.busy
        assert w.dpi_values==[75,150,300,600,1200,2400] and w.selected_dpi()==300
        w.opts={'resolution':(75,600,[75,150,300,600])};w.update_dpi_choices()
        assert w.dpi_values==[75,150,300,600]
        w.opts={'resolution':(200,400,[200,400])};w.update_dpi_choices()
        assert w.dpi_values==[200,400]
        w.opts={};w.update_dpi_choices();w.dpi.set_selected(5)
        assert w.selected_dpi()==2400
        w.dpi.set_selected(2)
        w.commit([a,b]);wait();assert len(w.pages)==2
        w.selected=0;w.rotate(90);wait();assert w.pages[0].size==(100,200)
        w.move(1);wait();assert w.selected==1
        w.delete();wait();assert len(w.pages)==1
        assert len(document.restore(w.session))==1
        assert w.view.get_visible_child_name()=='document'
        w.scan_preferences();pump();assert w.scan_dialog.get_mapped()
        assert w.scan_form.get_parent() is w.scan_dialog.body
        w.scan_dialog.close();pump();assert w.scan_dialog is None
        w.devices=[('test:0','SANE Testscanner')];w.opts=opts;w.sensitivity()
        def delayed_scan(*args,**kw):
            cancel_event=args[6]
            kw['preview'](Image.new('RGB',(200,300),'white'),.4,1,1)
            while not cancel_event.wait(.01):pass
            return [],True
        with patch('scanner.scan',side_effect=delayed_scan):
            w.start_scan();pump();assert w.scan_button_text.get_text()=='Stopp'
            assert w.scan_button.has_css_class('destructive-action')
            assert w.scan_progress.get_visible() and w.scan_progress.get_fraction()==.4
            assert '40 %' in w.scan_progress.get_text()
            assert len(w.pages)==1 and w.pages[0].getpixel((0,0))==b.getpixel((0,0))
            w.scan_button.emit('clicked');wait()
            assert not w.scan_button.has_css_class('destructive-action')
            assert not w.scan_progress.get_visible()
            assert len(w.pages)==1
        # Scanarten und Text/Bild werden in echte SANE-Parameter umgesetzt.
        w.mode.set_model(Gtk.StringList.new(opts['modes']))
        w.source.set_model(Gtk.StringList.new(opts['sources']))
        w.content.set_selected(0);assert opts['modes'][w.mode.get_selected()]=='Gray'
        w.content.set_selected(1);assert opts['modes'][w.mode.get_selected()]=='Color'
        w.scan_kind.set_selected(1);assert w.scan_source()=='Automatic Document Feeder'
        captured=[]
        def feeder_scan(*args,**kw):captured.append(args);return [a,b],False
        before=len(w.pages)
        with patch('scanner.scan',side_effect=feeder_scan):w.start_scan();wait()
        assert captured[0][4] is None and captured[0][2]=='Automatic Document Feeder'
        assert len(w.pages)==before+2
        w.scan_kind.set_selected(2);assert w.scan_source()=='Flatbed'
        with patch('scanner.scan',return_value=([a],False)),patch.object(w,'next_flatbed_page') as next_page:
            w.start_scan();wait();next_page.assert_called_once()
        w.next_flatbed_page();pump()
        prompt=next(v for v in Gtk.Window.get_toplevels() if v.get_title()=='Nächste Flachbettseite')
        assert prompt.get_mapped()
        prompt.destroy();pump()
        w.opts=dict(opts,sources=['Flatbed']);w.scan_kind.set_selected(1)
        assert w.scan_source() is None and not w.actions['scan'].get_enabled()
        w.devices=[];w.opts={}
        w.scan_kind.set_selected(0)
        w.pages=[];w.refresh();w.devices=[('test:0','SANE Testscanner')];w.opts=opts;w.ready_state()
        assert w.empty_title.get_text()=='Bereit zum Scannen'
        assert w.ready_device.get_mapped()
        w.devices=[];w.opts={}
        for dark in (False,True):
            Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
            w.set_default_size(720,600);pump();assert w.get_mapped()
        w.settings['language']='en';w.build();pump();assert w.t('File')=='File'
        w.settings['language']='de';w.build();pump();assert w.t('File')=='Datei'
        w.close();pump();assert json.loads((temp/'config/settings.json').read_text())['language']=='de'
print('BESTANDEN: DPI-Auswahl, Bereitschaftsanzeige, Text/Bild-Modus, ADF bis leer, Flachbett-Fortsetzung/Quellensperre, Teilbild-PNM (RGB/Bitmap/16 Bit), echte laufende SANE-Vorschau/Prozentwerte, GTK-Fortschritt/Abbruch, SANE-Erkennung, Optionen, echter Testbackend-Scan, Abbruch, fehlendes Backend, '
      'Mehrseiten-PDF, PNG, Überschreibschutz, Wiederherstellung, GTK-Start/Seiten/DE-EN/Hell-Dunkel/Beenden.')
