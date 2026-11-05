#!/usr/bin/python3
"""Docscan – eigenständiger GTK4-Dokumentenscanner."""
from pathlib import Path
import argparse,io,json,logging,logging.handlers,os,tempfile,threading,webbrowser
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gio,GLib,Gdk
from PIL import Image,ImageDraw
import bausteine as ui
import scanner,document,runtime_paths,language_packs

ROOT=Path(__file__).resolve().parents[1];VERSION=(ROOT/'VERSION').read_text().strip()

class App(Gtk.Application):
    def __init__(self,config=None):
        super().__init__(application_id='eu.dogtruck.docscan',flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.config=Path(config) if config is not None else runtime_paths.default_config(ROOT)
    def do_activate(self):
        if not self.get_active_window():Window(self)
        self.get_active_window().present()

class Window(Gtk.ApplicationWindow):
    def __init__(self,app):
        super().__init__(application=app,title=f'Docscan {VERSION}',default_width=1100,default_height=760)
        Gtk.IconTheme.get_for_display(self.get_display()).add_search_path(str(ROOT/'assets'));self.set_icon_name('docscan')
        runtime_paths.remember_installed_location(ROOT)
        self.config=app.config;self.config.mkdir(parents=True,exist_ok=True)
        self.session=self.config/'session';self.pages=[];self.selected=0;self.devices=[];self.opts={};self.busy=False;self.cancel=threading.Event();self.chooser=None
        self.settings={'language':'de','dpi':300,'folder':GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or str(Path.home()),'device':'','scan_kind':'single','content':'image','language_source':''}
        self.logger=logging.getLogger('docscan.'+str(id(self)));self.logger.setLevel(logging.INFO)
        handler=logging.handlers.RotatingFileHandler(self.config/'docscan.log',maxBytes=500000,backupCount=2)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s',datefmt='%d.%m.%Y %H:%M:%S'));self.logger.addHandler(handler)
        self.logger.info('\n-------------------- Docscan %s --------------------',VERSION)
        self.start_error=None
        try:
            path=self.config/'settings.json'
            if path.exists():
                saved=json.loads(path.read_text())
                if not isinstance(saved,dict):raise ValueError('Ungültige Einstellungsdatei; Standardwerte werden verwendet.')
                for key in self.settings:
                    v=saved.get(key)
                    if key=='dpi' and type(v) is int and 1<=v<=9600:self.settings[key]=v
                    elif key=='language' and language_packs.code_ok(v):self.settings[key]=v
                    elif key=='scan_kind' and v in ('single','feeder','flatbed'):self.settings[key]=v
                    elif key=='content' and v in ('text','image'):self.settings[key]=v
                    elif key in ('folder','device','language_source') and isinstance(v,str):self.settings[key]=v
            self.pages=document.restore(self.session)
        except (ValueError,OSError,Image.UnidentifiedImageError) as exc:self.start_error=str(exc);self.logger.exception('Wiederherstellung fehlgeschlagen')
        self.language_catalog=language_packs.installed(self.config)
        if self.settings['language'] not in self.language_catalog:self.settings['language']='en'
        self.translations=json.loads((ROOT/'lang/de.json').read_text())
        self.english=json.loads((ROOT/'lang/en.json').read_text())
        self.build();self.connect('close-request',self.close_request)
        for key,acc in [('scan','<Control>r'),('open','<Control>o'),('pdf','<Control>s'),('quit','<Control>q'),('help','F1')]:app.set_accels_for_action('win.'+key,[acc])
        self.present()
        if self.start_error:self.error(self.start_error)
        GLib.idle_add(self.find_devices)

    def t(self,key):
        code=self.settings['language']
        strings=self.translations if code=='de' else self.language_catalog.get(code,{}).get('strings',self.english)
        if key not in strings and key not in self.english:self.logger.warning('Missing translation: %s',key)
        return strings.get(key,self.english.get(key,key))

    def build(self):
        direction=Gtk.TextDirection.RTL if self.settings['language'].split('-')[0].split('_')[0] in ('ar','he','fa','ur') else Gtk.TextDirection.LTR
        Gtk.Widget.set_default_direction(direction);self.set_direction(direction)
        if getattr(self,'scan_dialog',None):self.scan_dialog.close()
        for action in self.list_actions():self.remove_action(action)
        self.scan_dialog=None
        layout=ui.box(spacing=0);self.set_child(layout)
        bar,self.actions=ui.menu_bar(self,[(self.t('File'),[(self.t('New document'),'new',self.new),(self.t('Import image / TIFF'),'open',self.open),None,(self.t('Save PDF'),'pdf',lambda:self.save('PDF')),(self.t('Save selected page as PNG'),'png',lambda:self.save('PNG')),(self.t('Save selected page as JPEG'),'jpeg',lambda:self.save('JPEG')),None,(self.t('Settings'),'settings',self.preferences),None,(self.t('Quit'),'quit',self.close)]),(self.t('Scanner'),[(self.t('Find scanners'),'find',self.find_devices),(self.t('Scan'),'scan',self.start_scan),(self.t('Cancel'),'cancel',self.cancel.set)]),(self.t('Page'),[(self.t('Rotate left'),'left',lambda:self.rotate(90)),(self.t('Rotate right'),'right',lambda:self.rotate(-90)),(self.t('Crop'),'crop',self.crop),None,(self.t('Move forward'),'up',lambda:self.move(-1)),(self.t('Move back'),'down',lambda:self.move(1)),(self.t('Delete page'),'delete',self.delete)]),(self.t('Help'),[(self.t('Help'),'help',self.help),(self.t('Log'),'log',self.show_log),(self.t('About'),'about',self.about)])]);layout.append(bar)
        header=Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label=self.t('Document Scanner')+' · '+VERSION))
        self.scan_button=Gtk.Button();self.scan_button.connect('clicked',lambda *_:self.cancel.set() if self.busy else self.start_scan())
        self.scan_button_content=Gtk.Box(spacing=8);self.scan_button_icon=Gtk.Image.new_from_icon_name('scanner-symbolic');self.scan_button_text=Gtk.Label(label=self.t('Scan'))
        self.scan_button_content.append(self.scan_button_icon);self.scan_button_content.append(self.scan_button_text);self.scan_button.set_child(self.scan_button_content);header.pack_start(self.scan_button)
        settings_button=Gtk.Button(icon_name='emblem-system-symbolic',tooltip_text=self.t('Scan settings'));settings_button.set_action_name('win.scan-settings');header.pack_start(settings_button)
        action=Gio.SimpleAction.new('scan-settings',None);action.connect('activate',lambda *_:self.scan_preferences());self.add_action(action);self.actions['scan-settings']=action
        save_button=Gtk.Button(icon_name='document-save-symbolic',tooltip_text=self.t('Save PDF'));save_button.set_action_name('win.pdf');header.pack_end(save_button)
        self.set_titlebar(header)
        # Die Regler leben im Einstellungsdialog, die Vorschau erhält den Hauptbereich.
        self.scan_form=ui.box(margin=16);form=self.scan_form
        self.device=Gtk.DropDown.new_from_strings([name for dev,name in self.devices] or [self.t('No scanner selected')]);ui.form_row(form,self.t('Scanner'),self.device)
        self.mode=Gtk.DropDown.new_from_strings(self.opts.get('modes',[]) or [self.t('Device default')]);ui.form_row(form,self.t('Colour mode'),self.mode)
        self.source=Gtk.DropDown.new_from_strings(self.opts.get('sources',[]) or [self.t('Device default')]);ui.form_row(form,self.t('Paper source'),self.source)
        self.dpi=Gtk.DropDown.new_from_strings([]);self.update_dpi_choices();ui.form_row(form,self.t('Resolution (dpi)'),self.dpi)
        self.scan_kind=Gtk.DropDown.new_from_strings([self.t(k) for k in ('Single page','All pages from feeder','Multiple pages from flatbed')])
        self.scan_kind.set_selected(['single','feeder','flatbed'].index(self.settings['scan_kind']))
        ui.form_row(form,self.t('Scan type'),self.scan_kind)
        self.content=Gtk.DropDown.new_from_strings([self.t('Text'),self.t('Image')])
        self.content.set_selected(0 if self.settings['content']=='text' else 1)
        ui.form_row(form,self.t('Original'),self.content)
        self.content.connect('notify::selected',self.content_changed)
        self.scan_kind.connect('notify::selected',self.scan_kind_changed)
        form.append(ui.label(self.t('Text scans create page images, without text recognition (OCR).')))
        self.option_status=ui.label(self.t('Only device-reported options are sent.'));form.append(self.option_status)
        self.view=Gtk.Stack(vexpand=True,hexpand=True);layout.append(self.view)
        empty=ui.box(spacing=28);empty.set_valign(Gtk.Align.CENTER);empty.set_halign(Gtk.Align.CENTER)
        self.empty_icon=Gtk.Image.new_from_icon_name('scanner-symbolic');self.empty_icon.set_pixel_size(128);self.empty_icon.add_css_class('dim-label');empty.append(self.empty_icon)
        self.empty_title=Gtk.Label(label=self.t('No document yet'));self.empty_title.add_css_class('title-1');self.empty_title.set_wrap(True);self.empty_title.set_justify(Gtk.Justification.CENTER);empty.append(self.empty_title)
        self.empty_detail=Gtk.Label(label=self.t('Scan a page or import an image.'));self.empty_detail.set_wrap(True);self.empty_detail.set_justify(Gtk.Justification.CENTER);empty.append(self.empty_detail)
        device_row=Gtk.Box(spacing=12,halign=Gtk.Align.CENTER)
        self.ready_device=Gtk.DropDown.new_from_strings([name for dev,name in self.devices] or [self.t('No scanner selected')])
        self.ready_device.set_size_request(280,-1);device_row.append(self.ready_device)
        refresh_button=Gtk.Button(icon_name='view-refresh-symbolic',tooltip_text=self.t('Find scanners'))
        refresh_button.set_action_name('win.find');device_row.append(refresh_button);empty.append(device_row)
        self.view.add_named(empty,'empty')
        self.picture=Gtk.Picture(can_shrink=True,hexpand=True,vexpand=True);self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.set_margin_top(20);self.picture.set_margin_bottom(20);self.picture.set_margin_start(20);self.picture.set_margin_end(20)
        content=Gtk.Overlay()
        content.set_child(ui.watermark(Gtk.Box(hexpand=True,vexpand=True),ROOT/'assets/report_watermark.png',opacity=.04))
        content.add_overlay(self.picture);self.view.add_named(content,'document')
        self.scan_progress=Gtk.ProgressBar(show_text=True,visible=False,margin_start=20,margin_end=20,margin_bottom=8)
        layout.append(self.scan_progress)
        layout.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        toolbar=Gtk.Box(spacing=10,margin_top=10,margin_bottom=10,margin_start=16,margin_end=16);layout.append(toolbar)
        new_button=Gtk.Button();new_content=Gtk.Box(spacing=8);new_content.append(Gtk.Image.new_from_icon_name('list-add-symbolic'));new_content.append(Gtk.Label(label=self.t('New document')));new_button.set_child(new_content);new_button.set_action_name('win.new');toolbar.append(new_button)
        spacer=Gtk.Box(hexpand=True);toolbar.append(spacer)
        for icon,title,name in [('object-rotate-left-symbolic','Rotate left','left'),('object-rotate-right-symbolic','Rotate right','right'),('docscan-crop-symbolic','Crop','crop'),('user-trash-symbolic','Delete page','delete')]:
            button=Gtk.Button(icon_name=icon,tooltip_text=self.t(title));button.set_action_name('win.'+name);toolbar.append(button)
        self.page_select=Gtk.DropDown.new_from_strings([]);self.page_select.set_tooltip_text(self.t('Page'));toolbar.append(self.page_select)
        self.page_select.connect('notify::selected',lambda *_:self.select_page(self.page_select.get_selected()))
        self.status=ui.label(self.t('Ready'));self.status.add_css_class('dim-label');self.status.set_margin_start(16);self.status.set_margin_bottom(8);layout.append(self.status)
        if self.devices:
            idx=next((i for i,(dev,n) in enumerate(self.devices) if dev==self.settings['device']),0);self.device.set_selected(idx);self.ready_device.set_selected(idx)
        self.ready_device.connect('notify::selected',lambda *_:self.device.set_selected(self.ready_device.get_selected()))
        self.device.connect('notify::selected',self.device_changed)
        self.refresh();self.sensitivity()

    def update_dpi_choices(self):
        self.dpi_values=[75,150,300,600,1200,2400]
        resolution=self.opts.get('resolution')
        if resolution:
            low,high,values=resolution
            self.dpi_values=[v for v in self.dpi_values if low<=v<=high and (values is None or v in values)]
            # Auch Geräte mit abweichenden, ausschließlich eigenen DPI-Werten bleiben nutzbar.
            if not self.dpi_values:self.dpi_values=sorted(values) if values else [low]
        self.dpi.set_model(Gtk.StringList.new([f'{v} dpi' for v in self.dpi_values]))
        index=min(range(len(self.dpi_values)),key=lambda i:abs(self.dpi_values[i]-self.settings['dpi']))
        self.dpi.set_selected(index)

    def selected_dpi(self):
        index=self.dpi.get_selected()
        return self.dpi_values[index] if index<len(self.dpi_values) else self.settings['dpi']

    def scan_source(self):
        sources=self.opts.get('sources',[])
        kind=self.settings['scan_kind']
        if kind=='single':
            index=self.source.get_selected()
            return sources[index] if index<len(sources) else ''
        words=('feeder','adf','einzug') if kind=='feeder' else ('flatbed','flat bed','flachbett')
        match=next((v for v in sources if any(word in v.lower() for word in words)),None)
        return '' if kind=='flatbed' and not sources else match

    def scan_kind_changed(self,*_):
        self.settings['scan_kind']=['single','feeder','flatbed'][self.scan_kind.get_selected()]
        self.sensitivity()

    def content_changed(self,*_):
        self.settings['content']=['text','image'][self.content.get_selected()]
        modes=self.opts.get('modes',[])
        words=('gray','grey','grayscale','grau','lineart','black','monochrome') if self.settings['content']=='text' else ('color','colour','farbe')
        index=next((i for word in words for i,v in enumerate(modes) if word in v.lower()),None)
        if index is not None:self.mode.set_selected(index)

    def ready_state(self):
        if not self.pages and not self.busy:
            ready=bool(self.devices and self.opts)
            self.empty_title.set_text(self.t('Ready to scan') if ready else self.t('No scanner found'))
            self.empty_detail.set_text(self.t('Scan a page or import an image.'))

    def sensitivity(self):
        for name,a in self.actions.items():a.set_enabled(not self.busy)
        self.actions['cancel'].set_enabled(self.busy)
        self.actions['scan'].set_enabled(not self.busy and bool(self.devices) and bool(self.opts) and self.scan_source() is not None)
        for name in ('pdf','png','jpeg','left','right','crop','up','down','delete'):self.actions[name].set_enabled(not self.busy and bool(self.pages))
        for control in (self.device,self.ready_device,self.mode,self.source,self.dpi,self.scan_kind,self.content):control.set_sensitive(not self.busy)
        if not self.opts.get('resolution'):self.dpi.set_sensitive(False)
        self.source.set_sensitive(not self.busy and self.settings['scan_kind']=='single')
        if self.opts:
            self.option_status.set_text(self.t('This scanner does not offer the selected paper source.') if self.scan_source() is None else self.t('Only device-reported options are sent.'))
        scanning=self.busy and getattr(self,'job_title','')=='Scanning'
        self.scan_button_text.set_text(self.t('Stop') if scanning else self.t('Scan'))
        self.scan_button_icon.set_from_icon_name('process-stop-symbolic' if scanning else 'scanner-symbolic')
        if scanning:self.scan_button.add_css_class('destructive-action')
        else:self.scan_button.remove_css_class('destructive-action')
        self.scan_button.set_sensitive(scanning or self.actions['scan'].get_enabled())
        self.page_select.set_sensitive(not self.busy and bool(self.pages))

    def error(self,detail):
        codes={'scanimage_missing':'SANE scanimage is missing.','timeout':'The scanner did not respond in time.','no_pages':'The document has no pages.','one_image_only':'Select one page for image export.'}
        self.logger.error('%s',detail)
        ui.message(self,self.t('Operation failed'),self.t(codes.get(str(detail),str(detail))),self.t('Close'))

    def job(self,title,work,done,*,cancelable=True):
        if self.busy:return
        self.job_token=object();token=self.job_token
        self.busy=True;self.job_title=title;self.cancel.clear();self.sensitivity()
        self.status.set_text(self.t(title))
        if not self.pages:
            self.empty_title.set_text(self.t(title));self.empty_detail.set_text(self.t('Please wait…'))
        self.actions['cancel'].set_enabled(cancelable)
        scanning=title=='Scanning'
        self.scan_progress.set_visible(scanning)
        self.scan_fraction=None
        if scanning:
            self.scan_progress.set_fraction(0);self.scan_progress.set_text(self.t('Waiting for image data…'))
        def pulse():
            if self.job_token is not token or not self.busy:return False
            if self.scan_fraction is None:self.scan_progress.pulse()
            return True
        timer=GLib.timeout_add(120,pulse) if scanning else None
        def update(n,total):
            def show():
                if self.job_token is token and self.busy and not scanning:
                    self.status.set_text(f'{self.t(title)} · {n} / {total}')
                return False
            GLib.idle_add(show)
        def preview(image,fraction,page,total):
            def show():
                if self.job_token is not token or not self.busy:return False
                self.scan_fraction=fraction
                self.scan_progress.set_fraction(fraction)
                text=f'{self.t("Page")} {page}'+(f' / {total}' if total else '')+f' · {int(fraction*100)} %'
                self.scan_progress.set_text(text);self.status.set_text(text)
                display=image.copy()
                if fraction<1:
                    y=min(display.height-1,int(display.height*fraction))
                    ImageDraw.Draw(display).line((0,y,display.width,y),fill='#ed1b24',width=2)
                self.show_image(display);self.view.set_visible_child_name('document')
                return False
            GLib.idle_add(show)
        update.preview=preview
        def finish(result,err):
            if timer:GLib.source_remove(timer)
            self.scan_progress.set_visible(False)
            self.busy=False;self.sensitivity()
            if scanning:self.refresh()
            if not self.pages:
                self.empty_title.set_text(self.t('No document yet'));self.empty_detail.set_text(self.t('Scan a page or import an image.'))
            if err:
                if getattr(err,'pages',None):self.commit(self.pages+err.pages)
                self.error(err)
            else:done(result)
            self.ready_state()
            return False
        def worker():
            try:result=work(self.cancel,update);err=None
            except scanner.Cancelled:result=None;err=None
            except Exception as exc:self.logger.exception('Auftrag fehlgeschlagen');result=None;err=exc
            GLib.idle_add(finish,result,err)
        threading.Thread(target=worker,daemon=True).start()

    def find_devices(self):
        def done(devices):
            if devices is None:return
            self.devices=sorted(devices,key=lambda item:0 if 'lide 200' in item[1].lower() else 1);self.opts={};self.build()
            if devices:self.device_changed()
            else:
                self.status.set_text(self.t('No scanners found. Check power, connection and SANE driver.'))
                self.empty_title.set_text(self.t('No scanner found'));self.empty_detail.set_text(self.t('Scan a page or import an image.'))
        self.job('Finding scanners',lambda cancel,update:scanner.discover(cancel),done)
        return False

    def device_changed(self,*_):
        if self.busy or not self.devices:return
        self.ready_device.set_selected(self.device.get_selected())
        dev=self.devices[self.device.get_selected()][0];self.settings['device']=dev
        self.opts={};self.update_dpi_choices();self.sensitivity()
        def done(opts):
            if opts is None:return
            self.opts=opts
            self.mode.set_model(Gtk.StringList.new(opts['modes'] or [self.t('Device default')]))
            self.source.set_model(Gtk.StringList.new(opts['sources'] or [self.t('Device default')]))
            if opts['resolution']:
                self.update_dpi_choices()
            self.content_changed();self.sensitivity();self.ready_state();self.status.set_text(self.t('Scanner ready'))
        self.job('Reading scanner options',lambda c,u:scanner.options(dev,c),done)

    def start_scan(self):
        if not self.devices or not self.opts or self.busy:return
        dev=self.devices[self.device.get_selected()][0]
        mode=self.opts['modes'][self.mode.get_selected()] if self.opts['modes'] else ''
        source=self.scan_source()
        if source is None:return
        dpi=self.selected_dpi() if self.opts['resolution'] else None
        if dpi and self.opts['resolution'][2] and dpi not in self.opts['resolution'][2]:return self.error(self.t('Choose a supported resolution: ')+str(self.opts['resolution'][2]))
        kind=self.settings['scan_kind'];count=None if kind=='feeder' else 1
        self.settings['dpi']=dpi or self.settings['dpi']
        def work(c,u):
            with tempfile.TemporaryDirectory(prefix='scan-',dir=self.config) as tmp:return scanner.scan(dev,mode,source,dpi,count,tmp,c,u,preview=u.preview)
        def done(result):
            if result is None:return
            images,cancelled=result
            self.commit(self.pages+images,after=(self.next_flatbed_page if kind=='flatbed' and images and not cancelled else None))
            self.status.set_text(self.t('Scan cancelled; complete pages kept.') if cancelled else self.t('Scan completed.'))
        self.job('Scanning',work,done)

    def next_flatbed_page(self):
        d=ui.Dialog(self,self.t('Next flatbed page'),width=580,height=300)
        d.body.append(ui.label(self.t('Place the next page on the flatbed, then choose Scan next page.')))
        d.button(self.t('Finish document'),d.destroy)
        def again():d.destroy();self.start_scan()
        d.button(self.t('Scan next page'),again);d.present()

    def commit(self,pages,after=None):
        self.pages=pages;self.selected=min(self.selected,max(0,len(pages)-1));self.refresh()
        snapshot=list(pages)
        self.job('Saving recovery copy',lambda c,u:document.save_session(snapshot,self.session),lambda _:after() if after else None,cancelable=False)

    def refresh(self):
        selected=self.selected
        self.page_select.set_model(Gtk.StringList.new([f'{self.t("Page")} {i+1} / {len(self.pages)}' for i in range(len(self.pages))]))
        self.view.set_visible_child_name('document' if self.pages else 'empty')
        if self.pages:
            self.page_select.set_selected(selected);self.select_page(selected)
        else:self.picture.set_paintable(None)
        self.status.set_text(f'{len(self.pages)} {self.t("Page") if len(self.pages)==1 else self.t("pages")}');self.sensitivity()

    def select_page(self,index):
        if not 0<=index<len(self.pages):return
        self.selected=index;image=self.pages[self.selected].copy();image.thumbnail((1600,1600))
        self.show_image(image)

    def show_image(self,image):
        stream=io.BytesIO();image.save(stream,format='PNG');self.picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(stream.getvalue())))

    def rotate(self,angle):
        pages=list(self.pages);pages[self.selected]=pages[self.selected].rotate(angle,expand=True);self.commit(pages)
    def move(self,offset):
        target=self.selected+offset
        if 0<=target<len(self.pages):
            pages=list(self.pages);pages[self.selected],pages[target]=pages[target],pages[self.selected];self.selected=target;self.commit(pages)
    def delete(self):self.commit([p for i,p in enumerate(self.pages) if i!=self.selected])

    def confirm(self,text,callback):
        d=ui.Dialog(self,self.t('Confirm'),height=250);d.body.append(ui.label(self.t(text)));d.button(self.t('Cancel'),d.destroy)
        def yes():d.destroy();callback()
        d.button(self.t('Continue'),yes);d.present()
    def new(self):self.confirm('Clear the current document and its recovery copy?',lambda:self.commit([])) if self.pages else None

    def open(self):
        def chosen(path):
            self.chooser=None
            if path:self.job('Importing pages',lambda c,u:document.load_images(path),lambda pages:self.commit(self.pages+pages) if pages else None,cancelable=False)
        self.chooser=ui.choose_file(self,self.t('Import image / TIFF'),chosen,initial_folder=self.settings['folder'],patterns=[(self.t('Images'),['*.png','*.jpg','*.jpeg','*.tif','*.tiff','*.pnm'])],accept=self.t('Open'),cancel=self.t('Cancel'))

    def save(self,kind):
        pages=list(self.pages) if kind=='PDF' else [self.pages[self.selected]];dpi=self.settings['dpi']
        def chosen(path):
            self.chooser=None
            if not path:return
            if path.exists():return self.error(self.t('The file already exists. Choose a new name.'))
            self.settings['folder']=str(path.parent)
            self.job('Exporting document',lambda c,u:document.export(pages,path,kind,dpi),lambda _:self.status.set_text(self.t('Saved: ')+str(path)),cancelable=False)
        ext={'PDF':'pdf','PNG':'png','JPEG':'jpg'}[kind]
        self.chooser=ui.choose_file(self,self.t('Save '+kind),chosen,save=True,name='scan.'+ext,initial_folder=self.settings['folder'],patterns=[(kind,['*.'+ext])],accept=self.t('Save'),cancel=self.t('Cancel'))

    def crop(self):
        image=self.pages[self.selected];d=ui.Dialog(self,self.t('Crop'),width=650,height=480);fields=[]
        for title,upper,value in [('Left',image.width-1,0),('Top',image.height-1,0),('Right',image.width,image.width),('Bottom',image.height,image.height)]:
            spin=ui.number(0,upper,1,value);ui.form_row(d.body,self.t(title),spin);fields.append(spin)
        def apply():
            l,t,r,b=[int(s.get_value()) for s in fields]
            if r<=l or b<=t:return self.error(self.t('The crop area must have positive width and height.'))
            pages=list(self.pages);pages[self.selected]=image.crop((l,t,r,b));d.destroy();self.commit(pages)
        d.button(self.t('Cancel'),d.destroy);d.button(self.t('Apply'),apply);d.present()

    def preferences(self):
        d=ui.Dialog(self,self.t('Settings'),width=720,height=650)
        language=Gtk.DropDown.new_from_strings([])
        codes=[]
        def refresh(selected=None):
            self.language_catalog=language_packs.installed(self.config)
            codes[:]=list(self.language_catalog)
            language.set_model(Gtk.StringList.new([self.language_catalog[c]['name'] for c in codes]))
            language.set_selected(codes.index(selected or self.settings['language']))
        refresh();ui.form_row(d.body,self.t('Language'),language)
        source=Gtk.Entry(text=self.settings['language_source']);source.set_hexpand(True)
        d.body.append(ui.label(self.t('Install languages'),heading=True))
        ui.form_row(d.body,self.t('GitHub base address'),source)
        message=ui.label(self.t('Additional languages include offline help.'));d.body.append(message)
        def install_result(code):
            if not code:return
            refresh(code);message.set_text(self.t('Language installed. Choose Save to apply.'))
        def failed(exc):message.set_text(self.t(str(exc)) if isinstance(exc,(language_packs.InvalidPack,FileExistsError)) else self.t('Could not load language package.'))
        loading=[False]
        def close_languages(*_):
            if loading[0]:return True
            if d.language_chooser:d.language_chooser.destroy()
            return False
        d.connect('close-request',close_languages)
        def task(work,done):
            loading[0]=True
            for button in buttons:button.set_sensitive(False)
            d.footer.set_sensitive(False);message.set_text(self.t('Please wait…'))
            def run():
                try:result=work();error=None
                except Exception as exc:result=None;error=exc
                def finish():
                    loading[0]=False
                    for button in buttons:button.set_sensitive(True)
                    d.footer.set_sensitive(True)
                    if error:failed(error)
                    else:done(result)
                    return False
                GLib.idle_add(finish)
            threading.Thread(target=run,daemon=True).start()
        d.language_chooser=None
        def import_chosen(path):
            d.language_chooser=None
            if path:task(lambda:language_packs.import_file(self.config,path),install_result)
        def choose_import():
            d.language_chooser=ui.choose_file(d,self.t('Import language package'),import_chosen,initial_folder=self.settings['folder'],patterns=[('JSON',['*.json'])],accept=self.t('Open'),cancel=self.t('Cancel'))
        available=[];download_choice=Gtk.DropDown.new_from_strings([])
        def show_catalog(entries):
            available[:]=[e for e in entries if e['code'] not in self.language_catalog]
            download_choice.set_model(Gtk.StringList.new([e['name'] for e in available]))
            download_choice.set_sensitive(bool(available));download_button.set_sensitive(bool(available))
            message.set_text(self.t('Choose a language to download.') if available else self.t('No additional languages available.'))
        def load_catalog():
            base=source.get_text().strip()
            task(lambda:language_packs.catalog(base),show_catalog)
        def load_pack():
            index=download_choice.get_selected()
            if index<len(available):
                base=source.get_text().strip();code=available[index]['code']
                task(lambda:language_packs.download(self.config,base,code),install_result)
        buttons=[]
        for title,callback in [('Import language package',choose_import),('Load language catalog',load_catalog)]:
            button=Gtk.Button(label=self.t(title));button.connect('clicked',lambda *_,fn=callback:fn());d.body.append(button);buttons.append(button)
        ui.form_row(d.body,self.t('Available languages'),download_choice);download_choice.set_sensitive(False)
        download_button=Gtk.Button(label=self.t('Download language and help'),sensitive=False);download_button.connect('clicked',lambda *_:load_pack());d.body.append(download_button);buttons.append(download_button)
        d.body.append(ui.label(self.t('Recovery copies and preferences are stored inside the project .config folder.')))
        def apply():
            self.settings['dpi']=self.selected_dpi()
            selected_mode=self.mode.get_selected();selected_source=self.source.get_selected()
            self.settings['language']=codes[language.get_selected()];self.settings['language_source']=source.get_text().strip()
            self.store_settings();d.destroy();self.build()
            if self.opts:
                self.mode.set_selected(selected_mode);self.source.set_selected(selected_source)
            self.ready_state()
        d.button(self.t('Cancel'),d.destroy);d.button(self.t('Save'),apply);d.present()

    def scan_preferences(self):
        if self.scan_dialog:
            self.scan_dialog.present();return
        d=ui.Dialog(self,self.t('Scan settings'),width=680,height=570);self.scan_dialog=d
        d.body.append(self.scan_form)
        def closed(*_):
            d.body.remove(self.scan_form);self.scan_dialog=None;d.destroy();return True
        d.connect('close-request',closed);d.button(self.t('Close'),closed);d.present()

    def store_settings(self):
        self.settings['config_version']=1
        temp=self.config/'settings.tmp';temp.write_text(json.dumps(self.settings,ensure_ascii=False));temp.chmod(0o600);os.replace(temp,self.config/'settings.json')
    def help(self):
        code=self.settings['language']
        path=ROOT/'help'/code/'index.html' if code in ('de','en') else self.config/'languages'/code/'index.html'
        if not path.is_file():path=ROOT/'help/en/index.html'
        webbrowser.open(path.resolve().as_uri())
    def show_log(self):
        d=ui.Dialog(self,self.t('Log'),width=850,height=600);d.body.append(ui.label((self.config/'docscan.log').read_text()[-40000:]));d.button(self.t('Close'),d.destroy);d.present()
    def about(self):ui.about(self,'Docscan',VERSION,comments=self.t('Document scanning with GTK4 and SANE. Inspired by GNOME Document Scanner. GPL-3.0-or-later.'),authors=['Josef'],icon_name='docscan')
    def close_request(self,*_):
        if self.busy:
            self.status.set_text(self.t('A task is running. Cancel it or wait before closing.'));return True
        self.settings['dpi']=self.selected_dpi();self.store_settings()
        if self.chooser:self.chooser.destroy()
        for h in list(self.logger.handlers):h.close();self.logger.removeHandler(h)
        return False

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Docscan – GTK4/SANE document scanner')
    parser.add_argument('--version',action='version',version='Docscan '+VERSION)
    parser.add_argument('--config-dir',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args();App(args.config_dir).run([])
